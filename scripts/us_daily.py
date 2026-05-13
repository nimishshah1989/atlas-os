#!/usr/bin/env python3
"""Nightly incremental run for US Atlas ETFs.

Computes metrics + RS states + regime for today (or --date) using a
400-day lookback for EMA warm-up.  US stocks pipeline is a separate
future milestone (us_stocks_pipeline.py); this script covers ETFs only.

Usage:
    python3 scripts/us_daily.py
    python3 scripts/us_daily.py --date 2026-05-13
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

from atlas.compute.global_pipeline import run_us_etf_daily  # noqa: E402

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
    parser = argparse.ArgumentParser(description="US Atlas ETF nightly incremental run")
    parser.add_argument(
        "--date",
        default=None,
        help="Target date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=400,
        help="Lookback days for EMA warm-up (default: 400)",
    )
    args = parser.parse_args()

    env = load_env(ROOT / ".env")
    db_url = env.get("ATLAS_DB_URL", "")
    if not db_url:
        log.error("ATLAS_DB_URL_not_set")
        sys.exit(1)

    engine = create_engine(db_url, pool_pre_ping=True)
    target = date.fromisoformat(args.date) if args.date else date.today()

    result = run_us_etf_daily(target, lookback_days=args.lookback, engine=engine)
    log.info("us_etf_daily_done", target=str(target), **result)


if __name__ == "__main__":
    main()
