#!/usr/bin/env python3
"""Nightly incremental run for US Atlas S&P 500 stocks.

Computes stock metrics + states + RS states for today (or --date) using a
400-day lookback for EMA warm-up. Companion to us_daily.py (which covers ETFs).

Writes to:
  - us_atlas.atlas_stock_metrics_daily
  - us_atlas.atlas_stock_states_daily
  - us_atlas.atlas_stock_rs_states

Usage:
    python3 scripts/us_stocks_daily.py
    python3 scripts/us_stocks_daily.py --date 2026-05-13
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import structlog  # noqa: E402

from atlas.compute.us_stocks import run_us_stocks_daily  # noqa: E402
from atlas.db import get_engine  # noqa: E402

log = structlog.get_logger()


def main() -> None:
    parser = argparse.ArgumentParser(description="US Atlas S&P 500 stocks nightly compute")
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD (default: today UTC)")
    parser.add_argument("--lookback", type=int, default=400, help="Lookback days (default: 400)")
    args = parser.parse_args()

    engine = get_engine()
    target = date.fromisoformat(args.date) if args.date else datetime.now(UTC).date()

    result = run_us_stocks_daily(target, lookback_days=args.lookback, engine=engine)
    log.info("us_stocks_daily_done", target=str(target), **result)


if __name__ == "__main__":
    main()
