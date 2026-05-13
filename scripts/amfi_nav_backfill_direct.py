#!/usr/bin/env python3
"""Backfill missing NAV using AMFI's official consolidated history file.

Fallback for funds that failed via mfapi.in (rate-limited). Downloads one
consolidated AMFI NAVAll history file for the full date range, parses it,
and inserts rows for our stuck funds.

Usage:
    python3 scripts/amfi_nav_backfill_direct.py --write
    python3 scripts/amfi_nav_backfill_direct.py --write --from-date 2026-04-01
"""

from __future__ import annotations

import argparse
import io
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests  # noqa: E402
import structlog  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

log = structlog.get_logger()

# AMFI's official consolidated NAV history endpoint
# Returns pipe-delimited text: SchemeCode|ISIN|ISIN2|SchemeName|NAV|Date
AMFI_HISTORY_URL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx"
REQUEST_TIMEOUT = 120  # consolidated file can be large

JIP_DB_URL_ENV = "JIP_DB_URL"
STALE_CUTOFF = "2026-05-01"
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


def get_stuck_funds_with_amfi_codes(supa_engine, jip_engine) -> list[tuple[str, date, int]]:
    """Return (mstar_id, latest_nav_date, amfi_code) for each fund needing backfill."""
    with supa_engine.connect() as conn:
        conn.execute(text("SET statement_timeout = 120000"))
        stuck = conn.execute(
            text("""
                SELECT n.mstar_id, MAX(n.nav_date) as latest_nav
                FROM public.de_mf_nav_daily n
                JOIN atlas.atlas_universe_funds f
                  ON f.mstar_id = n.mstar_id
                  AND f.effective_to IS NULL
                  AND f.plan_type = 'Regular'
                WHERE n.nav_date <= '2026-05-11'
                GROUP BY n.mstar_id
                HAVING COUNT(*) >= :min_days
                  AND MAX(n.nav_date) < :cutoff
                ORDER BY n.mstar_id
            """),
            {"min_days": MIN_HISTORY_DAYS, "cutoff": STALE_CUTOFF},
        ).fetchall()

    mstar_ids = [r[0] for r in stuck]
    latest_map = {r[0]: r[1] for r in stuck}

    with jip_engine.connect() as conn:
        amfi_rows = conn.execute(
            text(
                "SELECT mstar_id, amfi_code FROM public.de_mf_master "
                "WHERE mstar_id = ANY(:ids) AND amfi_code IS NOT NULL"
            ),
            {"ids": mstar_ids},
        ).fetchall()

    amfi_map = {r[0]: int(r[1]) for r in amfi_rows}
    return [(mid, latest_map[mid], amfi_map[mid]) for mid in mstar_ids if mid in amfi_map]


def fetch_amfi_consolidated(from_date: date, to_date: date) -> bytes:
    """Download AMFI consolidated NAV history for the date range."""
    fmt = "%d-%b-%Y"
    params = {
        "frmdt": from_date.strftime(fmt),
        "todt": to_date.strftime(fmt),
        "mf": "0",  # 0 = all AMCs
    }
    log.info("fetching_amfi_consolidated", from_date=str(from_date), to_date=str(to_date))
    resp = requests.get(AMFI_HISTORY_URL, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    log.info("amfi_response", size_kb=len(resp.content) // 1024)
    return resp.content


def parse_amfi_file(
    content: bytes, target_amfi_codes: set[int]
) -> dict[int, list[tuple[date, float]]]:
    """Parse AMFI pipe-delimited NAV file. Returns {amfi_code: [(date, nav), ...]}."""
    result: dict[int, list[tuple[date, float]]] = {code: [] for code in target_amfi_codes}
    text_content = content.decode("utf-8", errors="replace")

    for line in io.StringIO(text_content):
        line = line.strip()
        if not line or line.startswith("Scheme Code"):
            continue
        parts = line.split("|")
        if len(parts) < 6:
            continue
        try:
            scheme_code = int(parts[0].strip())
        except ValueError:
            continue
        if scheme_code not in target_amfi_codes:
            continue
        nav_str = parts[4].strip()
        date_str = parts[5].strip()
        try:
            nav_val = float(nav_str)
            nav_date = datetime.strptime(date_str, "%d-%b-%Y").date()
        except (ValueError, IndexError):
            continue
        result[scheme_code].append((nav_date, nav_val))

    return result


def insert_nav_rows(supa_engine, rows: list[dict], dry_run: bool) -> int:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="AMFI direct NAV backfill")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--from-date", default="2026-04-01")
    parser.add_argument("--to-date", default="2026-05-11")
    parser.add_argument("--env", default="/home/ubuntu/atlas-compute/.env")
    args = parser.parse_args()

    dry_run = not args.write
    from_date = datetime.strptime(args.from_date, "%Y-%m-%d").date()
    to_date = datetime.strptime(args.to_date, "%Y-%m-%d").date()

    print(f"AMFI Direct Backfill — dry_run={dry_run}, from={from_date}, to={to_date}")

    env = load_env(Path(args.env))
    supa = create_engine(env["ATLAS_DB_URL"], pool_pre_ping=True, pool_size=2)
    jip_url = env.get("JIP_DB_URL")
    if not jip_url:
        print("ERROR: JIP_DB_URL not set in .env")
        return 1
    jip = create_engine(
        jip_url, pool_pre_ping=True, pool_size=2, connect_args={"connect_timeout": 15}
    )

    stuck = get_stuck_funds_with_amfi_codes(supa, jip)
    print(f"Stuck funds: {len(stuck)}")

    target_amfi_codes = {amfi_code for _, _, amfi_code in stuck}
    amfi_to_mstar: dict[int, str] = {amfi_code: mstar_id for mstar_id, _, amfi_code in stuck}
    latest_by_mstar: dict[str, date] = {mstar_id: latest for mstar_id, latest, _ in stuck}

    print(f"Fetching AMFI consolidated NAV history for {len(target_amfi_codes)} amfi_codes...")
    try:
        content = fetch_amfi_consolidated(from_date, to_date)
    except requests.RequestException as e:
        print(f"ERROR fetching AMFI data: {e}")
        return 1

    parsed = parse_amfi_file(content, target_amfi_codes)

    all_rows: list[dict] = []
    funds_with_data = 0
    for amfi_code, nav_history in parsed.items():
        mstar_id = amfi_to_mstar.get(amfi_code)
        if not mstar_id:
            continue
        latest_nav = latest_by_mstar.get(mstar_id)
        new_rows = [
            {"nav_date": str(d), "mstar_id": mstar_id, "nav": str(nav)}
            for d, nav in nav_history
            if latest_nav is None or d > latest_nav
        ]
        if new_rows:
            funds_with_data += 1
            all_rows.extend(new_rows)
        print(f"  {mstar_id} (amfi={amfi_code}): {len(new_rows)} new rows")

    print(f"\nTotal: {len(all_rows)} rows for {funds_with_data} funds")

    inserted = insert_nav_rows(supa, all_rows, dry_run)
    print(f"Inserted: {inserted} (0 in dry-run)")

    if dry_run and all_rows:
        print("\nRe-run with --write to insert.")
    elif not dry_run and inserted > 0:
        print("\nNext: run M4 backfill for the affected date range:")
        print(f"  python3 scripts/m4_backfill.py --phase lens1 --start {from_date} --end {to_date}")
        print(
            f"  python3 scripts/m4_backfill.py --phase states --start {from_date} --end {to_date}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
