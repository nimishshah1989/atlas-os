"""Backfill atlas_factor_returns_daily with MKT/SMB/WML from 2010-01-01 to today.

Usage:
    python scripts/v6_factor_returns_backfill.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]

Defaults: start=2010-01-01, end=today.

Expects DATABASE_URL in environment. Run on EC2 where DB is accessible.

After run, verify with:
    SELECT COUNT(*) n, MIN(date) min_d, MAX(date) max_d,
           COUNT(mkt_excess) mkt_n, COUNT(smb) smb_n, COUNT(wml) wml_n
    FROM atlas.atlas_factor_returns_daily;
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date

import structlog
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Allow running from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from atlas.trading.v6.signals.factor_returns import compute_and_upsert_for_range

log = structlog.get_logger()


def _get_db_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        log.error("backfill.no_database_url")
        print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
        sys.exit(1)
    # Strip SQLAlchemy dialect prefix if needed (psycopg2 fix from wiki)
    if url.startswith("postgresql+psycopg2://"):
        url = url.replace("postgresql+psycopg2://", "postgresql://", 1)
    return url


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill atlas_factor_returns_daily for v6 trading model."
    )
    parser.add_argument(
        "--start",
        default="2010-01-01",
        help="Start date YYYY-MM-DD (default: 2010-01-01)",
    )
    parser.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="End date YYYY-MM-DD (default: today)",
    )
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)

    log.info(
        "backfill.start",
        start=str(start_date),
        end=str(end_date),
    )

    db_url = _get_db_url()
    engine = create_engine(
        db_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    try:
        result = compute_and_upsert_for_range(session, start_date, end_date)
        log.info("backfill.complete", **result)

        lines = [
            "",
            "Backfill complete:",
            f"  Written:    {result['written']:,} rows",
            f"  Skipped:    {result['skipped']:,} days (all factors NULL)",
            f"  Total days: {result['total_days']:,} trading days",
            "",
            "Verify with psql:",
            "  run: psql $DATABASE_URL",
            "  then paste the count query from the atlas_factor_returns_daily table",
        ]
        print("\n".join(lines))
    except Exception:
        session.rollback()
        log.exception("backfill.failed")
        raise
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    main()
