#!/usr/bin/env python3
"""M5 historical backfill — decision engine for stocks, ETFs, and funds.

Deploy to jsl-wealth-server after M4 backfill completes:
    export ATLAS_DB_URL="postgresql+psycopg2://..."
    python3 m5_backfill.py [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--asset stocks|etfs|funds|all]

Runtime estimate (full history from 2020-01-01):
    stocks: ~20-40 min (date-by-date price lookups)
    etfs:   ~15-25 min (same pattern, smaller universe)
    funds:  ~5 min (batch, no per-date price queries)
    all:    ~45-70 min
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from dotenv import load_dotenv

load_dotenv()

from atlas.compute.decisions_etf import backfill_etf_decisions  # noqa: E402
from atlas.compute.decisions_fund import backfill_fund_decisions  # noqa: E402
from atlas.compute.decisions_stock import backfill_stock_decisions  # noqa: E402
from atlas.config import Config  # noqa: E402
from atlas.db import get_engine  # noqa: E402


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    p = argparse.ArgumentParser(description="M5 decision engine historical backfill")
    p.add_argument(
        "--start",
        type=_parse_date,
        default=None,
        help="Start date (default: Config.HISTORICAL_START_DATE)",
    )
    p.add_argument("--end", type=_parse_date, default=None, help="End date (default: today)")
    p.add_argument(
        "--asset",
        choices=["stocks", "etfs", "funds", "all"],
        default="all",
        help="Which asset class to backfill (default: all)",
    )
    args = p.parse_args()

    start = args.start or _parse_date(Config.HISTORICAL_START_DATE)
    end = args.end or date.today()

    print(f"M5 backfill: {start} → {end}  asset={args.asset}")

    engine = get_engine()
    total_rows = 0
    errors: list[str] = []

    if args.asset in ("stocks", "all"):
        print("\n[1/3] Stock decisions…")
        try:
            rows = backfill_stock_decisions(start_date=start, end_date=end, engine=engine)
            print(f"      ✓ {rows:,} rows written to atlas_stock_decisions_daily")
            total_rows += rows
        except Exception as exc:
            msg = f"stock backfill failed: {exc}"
            print(f"      ✗ {msg}")
            errors.append(msg)

    if args.asset in ("etfs", "all"):
        print("\n[2/3] ETF decisions…")
        try:
            rows = backfill_etf_decisions(start_date=start, end_date=end, engine=engine)
            print(f"      ✓ {rows:,} rows written to atlas_etf_decisions_daily")
            total_rows += rows
        except Exception as exc:
            msg = f"ETF backfill failed: {exc}"
            print(f"      ✗ {msg}")
            errors.append(msg)

    if args.asset in ("funds", "all"):
        print("\n[3/3] Fund decisions…")
        try:
            rows = backfill_fund_decisions(start_date=start, end_date=end, engine=engine)
            print(f"      ✓ {rows:,} rows written to atlas_fund_decisions_daily")
            total_rows += rows
        except Exception as exc:
            msg = f"fund backfill failed: {exc}"
            print(f"      ✗ {msg}")
            errors.append(msg)

    print(f"\n{'─' * 55}")
    print(f"Total rows written: {total_rows:,}")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  • {e}")
        sys.exit(1)

    print("Done.")


if __name__ == "__main__":
    main()
