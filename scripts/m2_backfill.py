"""Atlas-M2 historical backfill entry point.

Runs the stock + ETF compute pipelines for the full historical window
(``HISTORICAL_START_DATE`` → today). Designed to be run from EC2 (~50 min P50,
~75 min P95 per ``prds/M2_BUILD_PLAN.md``); local Mac runs hit psycopg2 stalls
on Supabase pooler.

Usage::

    python scripts/m2_backfill.py                # full backfill
    python scripts/m2_backfill.py --stocks-only  # skip ETFs
    python scripts/m2_backfill.py --etfs-only    # skip stocks
    python scripts/m2_backfill.py --start 2024-01-01 --end 2024-12-31
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import structlog

# Ensure repo root is importable when invoked as a script
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.compute.etfs import run_etf_backfill  # noqa: E402
from atlas.compute.stocks import run_stock_backfill  # noqa: E402

log = structlog.get_logger()


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> int:
    parser = argparse.ArgumentParser(description="Atlas-M2 historical backfill")
    parser.add_argument(
        "--start",
        type=_parse_date,
        default=None,
        help="Start date (YYYY-MM-DD). Defaults to HISTORICAL_START_DATE.",
    )
    parser.add_argument(
        "--end", type=_parse_date, default=None, help="End date (YYYY-MM-DD). Defaults to today."
    )
    parser.add_argument("--stocks-only", action="store_true")
    parser.add_argument("--etfs-only", action="store_true")
    args = parser.parse_args()

    if args.stocks_only and args.etfs_only:
        parser.error("--stocks-only and --etfs-only are mutually exclusive")

    overall_start = datetime.now()

    if not args.etfs_only:
        log.info("m2_backfill_stocks_starting")
        result = run_stock_backfill(start=args.start, end=args.end)
        print(f"[stocks] {result}")

    if not args.stocks_only:
        log.info("m2_backfill_etfs_starting")
        result = run_etf_backfill(start=args.start, end=args.end)
        print(f"[etfs] {result}")

    elapsed = (datetime.now() - overall_start).total_seconds() / 60
    print(f"[m2_backfill] complete in {elapsed:.1f} minutes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
