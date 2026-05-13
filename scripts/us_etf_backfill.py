#!/usr/bin/env python3
"""Backfill US Atlas ETF compute pipeline (full history).

Runs the 4-benchmark RS pipeline for all curated US-listed ETFs from
HISTORICAL_START_DATE (default 2008-01-01) through today.

Requires ``us_atlas.stock_ohlcv`` to be populated first via:
    python3 scripts/stooq_backfill_us.py

Usage:
    python3 scripts/us_etf_backfill.py
    python3 scripts/us_etf_backfill.py --start 2020-01-01
    python3 scripts/us_etf_backfill.py --start 2020-01-01 --end 2024-12-31
    python3 scripts/us_etf_backfill.py --dry-run
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

from atlas.compute.global_pipeline import run_us_etf_backfill  # noqa: E402

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
    parser = argparse.ArgumentParser(description="US Atlas ETF full-history backfill")
    parser.add_argument(
        "--start",
        default=None,
        help="Start date YYYY-MM-DD (default: Config.HISTORICAL_START_DATE)",
    )
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD (default: today)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate OHLCV row counts; do not compute or write"
    )
    args = parser.parse_args()

    env = load_env(ROOT / ".env")
    db_url = env.get("ATLAS_DB_URL", "")
    if not db_url:
        log.error("ATLAS_DB_URL_not_set")
        sys.exit(1)

    engine = create_engine(db_url, pool_pre_ping=True)

    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None

    if args.dry_run:
        from datetime import date as dt_date

        from atlas.compute.global_pipeline import _load_ohlcv, _load_universe
        from atlas.config import Config

        universe = _load_universe(engine, schema="us_atlas")
        _start = start or dt_date.fromisoformat(Config.HISTORICAL_START_DATE)
        _end = end or dt_date.today()
        ohlcv = _load_ohlcv(
            engine,
            tickers=universe["ticker"].tolist(),
            start=_start,
            end=_end,
            schema="us_atlas",
        )
        log.info(
            "dry_run_summary",
            etfs=len(universe),
            ohlcv_rows=len(ohlcv),
            date_min=str(ohlcv["date"].min()) if not ohlcv.empty else "n/a",
            date_max=str(ohlcv["date"].max()) if not ohlcv.empty else "n/a",
        )
        return

    result = run_us_etf_backfill(start=start, end=end, engine=engine)
    log.info("us_etf_backfill_done", **result)


if __name__ == "__main__":
    main()
