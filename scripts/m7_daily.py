#!/usr/bin/env python3
# scripts/m7_daily.py
"""Nightly M7 paper trading entry point.

Run after Atlas compute finishes (e.g., cron: 0 22 * * 1-5).
Usage: python scripts/m7_daily.py [--date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

import structlog

log = structlog.get_logger()


def main() -> int:
    parser = argparse.ArgumentParser(description="M7 nightly paper trading runner")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Trading date YYYY-MM-DD (default: today)",
    )
    args = parser.parse_args()

    today = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()

    log.info("m7_daily_start", date=str(today))

    # Import here to avoid import-time DB connection
    from atlas.simulation.core.metrics import backfill_daily_returns
    from atlas.simulation.strategies.runner import run_nightly

    from atlas.db import get_engine

    engine = get_engine()

    try:
        results = run_nightly(engine, today)
        log.info("m7_daily_runner_done", strategies=len(results), date=str(today))
    except Exception:
        log.exception("m7_daily_runner_failed", date=str(today))
        return 1

    try:
        updated = backfill_daily_returns(engine, today)
        log.info("m7_daily_metrics_done", updated=updated, date=str(today))
    except Exception:
        log.exception("m7_daily_metrics_failed", date=str(today))
        return 1

    log.info("m7_daily_complete", date=str(today))
    return 0


if __name__ == "__main__":
    sys.exit(main())
