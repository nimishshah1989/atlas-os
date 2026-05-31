#!/usr/bin/env python3
"""Backfill full NAV history for universe funds that JIP added recently without history.

These are established funds (going back to 2013) that JIP only started tracking
from April 2026. They have <252 NAV rows in de_mf_nav_daily, so they're excluded
from state computation — but mfapi.in has their complete history.

Unlike amfi_nav_backfill.py (which syncs recent rows), this script fetches the
*entire* history from mfapi.in and inserts everything missing (ON CONFLICT DO NOTHING).

Usage:
    python3 scripts/amfi_history_backfill.py               # dry-run
    python3 scripts/amfi_history_backfill.py --write        # insert
    python3 scripts/amfi_history_backfill.py --write --min-rows 100  # target thinner funds
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests  # noqa: E402
import structlog  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

log = structlog.get_logger()

MFAPI_BASE = "https://api.mfapi.in/mf"
REQUEST_DELAY = 2.0
REQUEST_TIMEOUT = 20
MIN_MFAPI_ROWS = 252  # only backfill if mfapi.in has enough history to be useful


def load_env(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k] = v
    return env


def get_thin_funds(supa_engine, max_rows: int) -> list[str]:
    """Return mstar_ids of active universe funds with fewer than max_rows NAV rows."""
    with supa_engine.connect() as conn:
        conn.execute(text("SET statement_timeout = 120000"))
        rows = conn.execute(
            text("""
                SELECT f.mstar_id
                FROM atlas.atlas_universe_funds f
                WHERE f.effective_to IS NULL AND f.plan_type = 'Regular'
                  AND (
                      SELECT COUNT(*) FROM public.de_mf_nav_daily n WHERE n.mstar_id = f.mstar_id
                  ) < :max_rows
                ORDER BY f.mstar_id
            """),
            {"max_rows": max_rows},
        ).fetchall()
    return [r[0] for r in rows]


def get_amfi_codes(jip_engine, mstar_ids: list[str]) -> dict[str, int]:
    with jip_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT mstar_id, amfi_code FROM public.de_mf_master "
                "WHERE mstar_id = ANY(:ids) AND amfi_code IS NOT NULL"
            ),
            {"ids": mstar_ids},
        ).fetchall()
    return {r[0]: int(r[1]) for r in rows}


def get_existing_nav_dates(supa_engine, mstar_id: str) -> set[str]:
    """Fetch existing nav_dates for a fund so we can skip them."""
    with supa_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT nav_date::text FROM public.de_mf_nav_daily WHERE mstar_id = :mid"),
            {"mid": mstar_id},
        ).fetchall()
    return {r[0] for r in rows}


def fetch_full_history(amfi_code: int) -> list[dict]:
    url = f"{MFAPI_BASE}/{amfi_code}"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", []) if isinstance(data, dict) else []
    except requests.RequestException as e:
        log.warning("mfapi_fetch_failed", amfi_code=amfi_code, error=str(e))
        return []


def insert_rows(supa_engine, rows: list[dict], dry_run: bool) -> int:
    if not rows:
        return 0
    if dry_run:
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
    parser = argparse.ArgumentParser(description="Backfill full NAV history for thin funds")
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--max-rows",
        type=int,
        default=252,
        help="Target funds with fewer than this many NAV rows (default: 252)",
    )
    parser.add_argument("--env", default="/home/ubuntu/atlas-compute/.env")
    args = parser.parse_args()

    dry_run = not args.write
    print(f"AMFI History Backfill — dry_run={dry_run}, max_rows={args.max_rows}")

    env = load_env(Path(args.env))
    supa = create_engine(env["ATLAS_DB_URL"], pool_pre_ping=True, pool_size=2)
    jip_url = env.get("JIP_DB_URL")
    if not jip_url:
        print("ERROR: JIP_DB_URL not set")
        return 1
    jip = create_engine(
        jip_url, pool_pre_ping=True, pool_size=2, connect_args={"connect_timeout": 15}
    )

    thin = get_thin_funds(supa, args.max_rows)
    print(f"Thin funds (<{args.max_rows} rows): {len(thin)}")

    amfi_map = get_amfi_codes(jip, thin)
    print(f"AMFI codes found: {len(amfi_map)}/{len(thin)}")

    total_inserted = 0
    funds_recovered = 0

    for i, mstar_id in enumerate(thin):
        amfi_code = amfi_map.get(mstar_id)
        if not amfi_code:
            continue

        nav_data = fetch_full_history(amfi_code)
        if len(nav_data) < MIN_MFAPI_ROWS:
            print(
                f"  [{i + 1}/{len(thin)}] {mstar_id}: only {len(nav_data)} rows on mfapi.in — skip"
            )
            time.sleep(REQUEST_DELAY)
            continue

        # Build rows from mfapi.in data, skip any already in DB via ON CONFLICT
        rows = []
        for item in nav_data:
            date_str = item.get("date", "")
            nav_val = item.get("nav")
            if not date_str or nav_val is None:
                continue
            try:
                nav_date = datetime.strptime(date_str, "%d-%m-%Y").date()
                nav_float = float(nav_val)
            except (ValueError, TypeError):
                continue
            if nav_float <= 0:
                continue
            rows.append({"nav_date": str(nav_date), "mstar_id": mstar_id, "nav": str(nav_float)})

        inserted = insert_rows(supa, rows, dry_run)
        total_inserted += inserted
        funds_recovered += 1
        print(
            f"  [{i + 1}/{len(thin)}] {mstar_id} (amfi={amfi_code}): {len(rows)} rows from mfapi → {'inserted' if not dry_run else 'would insert'} {len(rows)}"
        )

        time.sleep(REQUEST_DELAY)

    print(f"\nTotal: {total_inserted} rows inserted for {funds_recovered} funds")
    if dry_run and total_inserted == 0:
        print(f"(dry-run — would insert rows for {funds_recovered} funds, re-run with --write)")

    if not dry_run and funds_recovered > 0:
        print("\nNext: run M4 backfill for the full date range:")
        print("  python3 scripts/m4_backfill.py --phase lens1 --start 2013-01-01 --end 2026-05-11")
        print("  python3 scripts/m4_backfill.py --phase states --start 2013-01-01 --end 2026-05-11")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
