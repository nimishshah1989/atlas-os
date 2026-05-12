"""Backfill CTS signals for the last 2 years.

Runs once on EC2 to bootstrap the IC measurement tables.
Usage:
    python scripts/backfill_cts_signals.py [--days 504]
"""

from __future__ import annotations

import argparse
from datetime import date

import structlog
from sqlalchemy import text

from atlas.compute._session import open_compute_session
from atlas.db import get_engine
from scripts.compute_cts_signals import run

log = structlog.get_logger()


def backfill(total_days: int = 504) -> None:
    engine = get_engine()

    with open_compute_session(engine) as conn:
        rows = conn.execute(
            text("""
                SELECT date FROM public.de_trading_calendar
                WHERE is_trading = TRUE
                  AND exchange = 'NSE'
                  AND date <= CURRENT_DATE
                  AND date >= CURRENT_DATE - :days
                ORDER BY date
            """),
            {"days": total_days * 2},
        ).fetchall()
    trading_dates = [r[0] for r in rows][-total_days:]

    log.info("backfill_start", total_dates=len(trading_dates))
    for i, d in enumerate(trading_dates):
        if not isinstance(d, date):
            d = d if hasattr(d, "year") else date.fromisoformat(str(d))
        try:
            run(d, persist=True)
            log.info("backfill_progress", date=str(d), done=i + 1, total=len(trading_dates))
        except Exception as e:
            log.error("backfill_date_failed", date=str(d), error=str(e))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=504)
    args = parser.parse_args()
    backfill(total_days=args.days)
