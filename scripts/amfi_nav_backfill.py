#!/usr/bin/env python3
"""Backfill missing NAV data for funds stuck in JIP (stopped at early April 2026).

Root cause: JIP pipeline marked ~148 funds as 'merged' after losing their
AMFI scheme-code mapping. This script fetches their NAV history directly
from the mfapi.in AMFI mirror and inserts into Supabase de_mf_nav_daily.

Usage:
    python3 scripts/amfi_nav_backfill.py                        # dry-run
    python3 scripts/amfi_nav_backfill.py --write                # actually insert
    python3 scripts/amfi_nav_backfill.py --write --from-date 2026-04-01
    python3 scripts/amfi_nav_backfill.py --fund F000000CBK      # single fund
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests  # noqa: E402
import structlog  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

log = structlog.get_logger()

MFAPI_BASE = "https://api.mfapi.in/mf"
REQUEST_DELAY = 2.0  # seconds between API calls — conservative to avoid rate-limiting
REQUEST_TIMEOUT = 20  # seconds per request

# Default staleness window: flag funds whose latest NAV is >N days old.
# Overridable via --stale-days at runtime.
DEFAULT_STALE_DAYS = 5
MIN_HISTORY_DAYS = 252


def load_env(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k] = v
    return env


def get_stuck_funds(
    supa_engine, single_fund: str | None, stale_cutoff: date
) -> list[tuple[str, date]]:
    """Return (mstar_id, latest_nav_date) for each fund needing backfill."""
    if single_fund:
        with supa_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT mstar_id, MAX(nav_date) as latest_nav "
                    "FROM public.de_mf_nav_daily "
                    "WHERE mstar_id = :mid GROUP BY mstar_id"
                ),
                {"mid": single_fund},
            ).fetchone()
        if not row:
            log.warning("fund_not_found_in_nav", mstar_id=single_fund)
            return []
        return [(row[0], row[1])]

    with supa_engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT n.mstar_id, MAX(n.nav_date) as latest_nav
                FROM public.de_mf_nav_daily n
                JOIN atlas.atlas_universe_funds f
                  ON f.mstar_id = n.mstar_id
                  AND f.effective_to IS NULL
                  AND f.plan_type = 'Regular'
                GROUP BY n.mstar_id
                HAVING COUNT(*) >= :min_days
                  AND MAX(n.nav_date) < :cutoff
                ORDER BY n.mstar_id
            """),
            {"min_days": MIN_HISTORY_DAYS, "cutoff": str(stale_cutoff)},
        ).fetchall()
    return [(r[0], r[1]) for r in rows]


def get_amfi_codes(jip_engine, mstar_ids: list[str]) -> dict[str, int]:
    """Return {mstar_id: amfi_code} from JIP de_mf_master."""
    with jip_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT mstar_id, amfi_code FROM public.de_mf_master "
                "WHERE mstar_id = ANY(:ids) AND amfi_code IS NOT NULL"
            ),
            {"ids": mstar_ids},
        ).fetchall()
    return {r[0]: int(r[1]) for r in rows}


def fetch_nav_from_mfapi(amfi_code: int) -> list[dict]:
    """Fetch NAV history from mfapi.in. Returns list of {date, nav} dicts."""
    url = f"{MFAPI_BASE}/{amfi_code}"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except requests.RequestException as e:
        log.warning("mfapi_fetch_failed", amfi_code=amfi_code, error=str(e))
        return []


def parse_mfapi_date(date_str: str) -> date | None:
    """Parse mfapi.in date format: 'DD-MM-YYYY'."""
    try:
        return datetime.strptime(date_str, "%d-%m-%Y").date()
    except ValueError:
        return None


def insert_nav_rows(supa_engine, rows: list[dict], dry_run: bool) -> int:
    """Bulk-insert NAV rows into de_mf_nav_daily. Skips conflicts."""
    if not rows:
        return 0
    if dry_run:
        log.info("dry_run_would_insert", count=len(rows))
        return 0

    chunk_size = 500
    with supa_engine.begin() as conn:
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i : i + chunk_size]
            conn.execute(
                text(
                    "INSERT INTO public.de_mf_nav_daily "
                    "(nav_date, mstar_id, nav, data_status) "
                    "VALUES (:nav_date, :mstar_id, :nav, 'raw') "
                    "ON CONFLICT (nav_date, mstar_id) DO NOTHING"
                ),
                chunk,
            )

    return len(rows)


def process_fund(
    mstar_id: str,
    amfi_code: int,
    latest_nav: date,
    from_date: date,
    supa_engine,
    dry_run: bool,
) -> dict:
    nav_data = fetch_nav_from_mfapi(amfi_code)
    if not nav_data:
        return {"mstar_id": mstar_id, "status": "no_data", "inserted": 0}

    # Filter to dates after last known NAV and on/before from_date cutoff
    rows = []
    for item in nav_data:
        d = parse_mfapi_date(item.get("date", ""))
        nav_val = item.get("nav")
        if d is None or nav_val is None:
            continue
        if d <= latest_nav:
            continue
        if d < from_date:
            continue
        try:
            nav_float = float(nav_val)
        except (ValueError, TypeError):
            continue
        rows.append({"nav_date": str(d), "mstar_id": mstar_id, "nav": str(nav_float)})

    inserted = insert_nav_rows(supa_engine, rows, dry_run)
    return {"mstar_id": mstar_id, "status": "ok", "new_rows": len(rows), "inserted": inserted}


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill AMFI NAVs for stuck funds")
    parser.add_argument("--write", action="store_true", help="Actually insert (default: dry-run)")
    parser.add_argument(
        "--from-date", default=None, help="Fetch NAV from this date (default: stale-days ago)"
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=DEFAULT_STALE_DAYS,
        help="Flag funds whose latest NAV is older than this many days (default: 5)",
    )
    parser.add_argument("--fund", help="Process single mstar_id only")
    parser.add_argument("--env", default="/home/ubuntu/atlas-compute/.env")
    args = parser.parse_args()

    dry_run = not args.write
    stale_cutoff = date.today() - timedelta(days=args.stale_days)
    from_date = (
        datetime.strptime(args.from_date, "%Y-%m-%d").date() if args.from_date else stale_cutoff
    )

    print(f"AMFI NAV Backfill — dry_run={dry_run}, from={from_date}, stale_cutoff={stale_cutoff}")

    env = load_env(Path(args.env))
    supa = create_engine(env["ATLAS_DB_URL"], pool_pre_ping=True, pool_size=2)
    jip_url = env.get("JIP_DB_URL")
    if not jip_url:
        print("ERROR: JIP_DB_URL not set in .env — needed to look up AMFI scheme codes")
        return 1
    jip = create_engine(
        jip_url, pool_pre_ping=True, pool_size=2, connect_args={"connect_timeout": 15}
    )

    stuck = get_stuck_funds(supa, args.fund, stale_cutoff)
    print(f"Stuck funds to process: {len(stuck)}")

    mstar_ids = [mid for mid, _ in stuck]
    amfi_map = get_amfi_codes(jip, mstar_ids)
    print(f"AMFI codes found: {len(amfi_map)}/{len(stuck)}")

    missing_codes = [mid for mid in mstar_ids if mid not in amfi_map]
    if missing_codes:
        print(f"WARNING: No amfi_code for {len(missing_codes)} funds: {missing_codes[:5]}...")

    results = []
    for i, (mstar_id, latest_nav) in enumerate(stuck):
        amfi_code = amfi_map.get(mstar_id)
        if not amfi_code:
            results.append({"mstar_id": mstar_id, "status": "no_amfi_code", "inserted": 0})
            continue

        print(
            f"  [{i+1}/{len(stuck)}] {mstar_id} (amfi={amfi_code}, latest={latest_nav}) ...",
            end="",
            flush=True,
        )
        result = process_fund(mstar_id, amfi_code, latest_nav, from_date, supa, dry_run)
        new_rows = result.get("new_rows", 0)
        print(f" {new_rows} new rows")
        results.append(result)

        time.sleep(REQUEST_DELAY)

    total_new = sum(int(r.get("new_rows") or 0) for r in results)  # type: ignore[call-overload]
    total_inserted = sum(int(r.get("inserted") or 0) for r in results)  # type: ignore[call-overload]
    no_data = [r["mstar_id"] for r in results if r["status"] == "no_data"]
    errors = [
        r["mstar_id"] for r in results if r["status"] not in ("ok", "no_data", "no_amfi_code")
    ]

    print("\n=== SUMMARY ===")
    print(f"Funds processed: {len(results)}")
    print(f"New NAV rows found: {total_new}")
    print(f"Rows inserted: {total_inserted} (0 in dry-run)")
    if no_data:
        print(f"No data from mfapi.in: {len(no_data)} funds")
        for mid in no_data[:10]:
            print(f"  {mid}")
    if errors:
        print(f"Errors: {errors}")

    if dry_run and total_new > 0:
        print("\nRe-run with --write to insert.")
    elif not dry_run and total_inserted > 0:
        print("\nNext step: run M4 backfill for 2026-04-03 to 2026-05-11:")
        print("  python3 scripts/m4_backfill.py --start 2026-04-03 --end 2026-05-11")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
