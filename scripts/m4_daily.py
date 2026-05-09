#!/usr/bin/env python3
"""M4 nightly incremental run — fund lens refresh.

Deploy to jsl-wealth-server, add to cron (runs after M2/M3 daily):
    export ATLAS_DB_URL="postgresql+psycopg2://..."
    python3 m4_daily.py [--date YYYY-MM-DD]

On most days (no new fund disclosures): ~1-2 min (Lens 1 NAV refresh only).
On disclosure days (typically mid-month): ~3-6 min (Lens 1+2+3 + states).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from dotenv import load_dotenv

load_dotenv()

from atlas.compute.funds import run_m4_daily  # noqa: E402
from atlas.health.runs import safe_finish, safe_record  # noqa: E402


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    p = argparse.ArgumentParser(description="M4 daily fund lens run")
    p.add_argument("--date", type=_parse_date, default=None, help="Target date (default: today)")
    args = p.parse_args()

    target = args.date or date.today()
    print(f"M4 daily run for {target}")

    run_id = safe_record("m4_daily", milestone="M4")
    try:
        result = run_m4_daily(target_date=target)
    except Exception as exc:
        safe_finish(run_id, status="failed", error=exc)
        raise

    if result.get("status") == "no_states":
        safe_finish(run_id, status="failed", error="no fund states assembled")
        print("WARNING: No fund states assembled — check fund universe and NAV data.")
        sys.exit(1)

    safe_finish(run_id, status="success", rows_written=int(result.get("rows_written", 0)))

    lens1 = result.get("lens1", {})
    lens2 = result.get("lens2", {})
    lens3 = result.get("lens3", {})

    print(f"Lens 1 (NAV):         {lens1.get('rows_written', 0):,} rows")
    skipped = lens2.get("skipped", False)
    if skipped:
        print("Lens 2 (Composition): skipped (no new disclosures)")
        print("Lens 3 (Holdings):    skipped (no new disclosures)")
    else:
        print(f"Lens 2 (Composition): {lens2.get('rows_written', 0):,} rows")
        print(f"Lens 3 (Holdings):    {lens3.get('rows_written', 0):,} rows")

    print(f"State rows written:   {result.get('rows_written', 0):,}")
    print(f"Run ID: {result.get('run_id')}")
    print("Done.")


if __name__ == "__main__":
    main()
