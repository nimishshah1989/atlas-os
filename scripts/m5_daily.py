#!/usr/bin/env python3
"""M5 nightly incremental run — decision engine refresh.

Deploy to jsl-wealth-server, add to cron (runs after M4 daily):
    export ATLAS_DB_URL="postgresql+psycopg2://..."
    python3 m5_daily.py [--date YYYY-MM-DD]

Runtime (single day, full universe): ~2-5 min.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from dotenv import load_dotenv

load_dotenv()

from atlas.compute.decisions_etf import run_etf_decisions  # noqa: E402
from atlas.compute.decisions_fund import run_fund_decisions  # noqa: E402
from atlas.compute.decisions_stock import run_stock_decisions  # noqa: E402
from atlas.db import get_engine  # noqa: E402


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    p = argparse.ArgumentParser(description="M5 daily decision engine run")
    p.add_argument("--date", type=_parse_date, default=None, help="Target date (default: today)")
    args = p.parse_args()

    target = args.date or date.today()
    print(f"M5 daily run for {target}")

    engine = get_engine()
    errors: list[str] = []

    print("\n[1/3] Stock decisions…")
    try:
        result = run_stock_decisions(target, target, engine=engine)
        print(f"      ✓ {result['rows_written']:,} rows  run_id={result['run_id']}")
    except Exception as exc:
        msg = f"stock decisions failed: {exc}"
        print(f"      ✗ {msg}")
        errors.append(msg)

    print("\n[2/3] ETF decisions…")
    try:
        result = run_etf_decisions(target, target, engine=engine)
        print(f"      ✓ {result['rows_written']:,} rows  run_id={result['run_id']}")
    except Exception as exc:
        msg = f"ETF decisions failed: {exc}"
        print(f"      ✗ {msg}")
        errors.append(msg)

    print("\n[3/3] Fund decisions…")
    try:
        result = run_fund_decisions(target, target, engine=engine)
        print(f"      ✓ {result['rows_written']:,} rows  run_id={result['run_id']}")
    except Exception as exc:
        msg = f"fund decisions failed: {exc}"
        print(f"      ✗ {msg}")
        errors.append(msg)

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  • {e}")
        sys.exit(1)

    print("\nDone.")


if __name__ == "__main__":
    main()
