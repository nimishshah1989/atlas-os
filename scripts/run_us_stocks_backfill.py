#!/usr/bin/env python3
"""Compute US Atlas S&P 500 stock metrics, states, and RS states.

Reads from us_atlas.stock_ohlcv + benchmark cache → writes to:
  - us_atlas.atlas_stock_metrics_daily
  - us_atlas.atlas_stock_states_daily
  - us_atlas.atlas_stock_rs_states

Usage:
    # Full backfill (2008 → today)
    python3 scripts/run_us_stocks_backfill.py

    # Custom date range
    python3 scripts/run_us_stocks_backfill.py --start 2020-01-01 --end 2026-05-13
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import structlog  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

from atlas.compute.us_stocks import run_us_stocks_backfill  # noqa: E402

log = structlog.get_logger()


def load_env(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not env_path.exists():
        return env
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute US Atlas S&P 500 metrics + states")
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD (default: 2008-01-01)")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    env = load_env(ROOT / ".env")
    db_url = env.get("ATLAS_DB_URL", "")
    if not db_url:
        log.error("ATLAS_DB_URL_not_set")
        sys.exit(1)

    engine = create_engine(db_url, pool_pre_ping=True)

    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None

    log.info("starting_us_stocks_backfill", start=str(start), end=str(end))
    result = run_us_stocks_backfill(start=start, end=end, engine=engine)
    log.info("backfill_done", **result)


if __name__ == "__main__":
    main()
