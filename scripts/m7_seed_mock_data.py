#!/usr/bin/env python3
# scripts/m7_seed_mock_data.py
"""Seed mock data for M7 frontend development.

Inserts sentinel rows (positions_count=-999) so the frontend can render
strategy cards, performance charts, and overlap matrices before the first
real nightly run. PURGE BEFORE PRODUCTION with --purge flag.

Usage:
  python scripts/m7_seed_mock_data.py          # seed mock data
  python scripts/m7_seed_mock_data.py --purge  # remove all mock rows
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, timedelta

import structlog
from sqlalchemy import text

log = structlog.get_logger()

_SENTINEL = -999  # positions_count sentinel identifies mock rows


def _purge_mock_data(engine) -> int:  # type: ignore[no-untyped-def]
    """Delete all rows with positions_count = -999."""
    with engine.connect() as conn:
        result = conn.execute(
            text("DELETE FROM atlas.strategy_paper_performance WHERE positions_count = :sentinel"),
            {"sentinel": _SENTINEL},
        )
        conn.commit()
    return result.rowcount or 0


def _seed_mock_data(engine) -> int:  # type: ignore[no-untyped-def]
    """Seed 30 days of mock performance rows for all active strategies."""
    with engine.connect() as conn:
        strategy_rows = conn.execute(
            text("SELECT id, name FROM atlas.strategy_configs WHERE is_active = TRUE")
        ).fetchall()

    if not strategy_rows:
        log.warning("seed_no_strategies_found")
        return 0

    today = date.today()
    base_value = 10_000_000.0
    inserted = 0

    with engine.connect() as conn:
        for strat in strategy_rows:
            value = base_value
            for i in range(30, 0, -1):
                d = today - timedelta(days=i)
                if d.weekday() >= 5:  # skip weekends
                    continue
                daily_return = random.uniform(-0.02, 0.025)  # noqa: S311
                value *= 1 + daily_return
                conn.execute(
                    text("""
                        INSERT INTO atlas.strategy_paper_performance
                            (strategy_id, date, total_value, daily_return,
                             regime, positions_count)
                        VALUES
                            (:sid, :date, :val, :ret, :regime, :sentinel)
                        ON CONFLICT (strategy_id, date) DO NOTHING
                    """),
                    {
                        "sid": str(strat.id),
                        "date": d,
                        "val": round(value, 4),
                        "ret": round(daily_return, 6),
                        "regime": random.choice(  # noqa: S311
                            ["Risk-On", "Constructive", "Cautious", "Risk-Off"]
                        ),
                        "sentinel": _SENTINEL,
                    },
                )
                inserted += 1
        conn.commit()

    log.info("seed_mock_data_done", rows=inserted, strategies=len(strategy_rows))
    return inserted


def main() -> int:
    parser = argparse.ArgumentParser(description="M7 mock data seeder")
    parser.add_argument(
        "--purge",
        action="store_true",
        help="Remove all mock rows (positions_count=-999)",
    )
    args = parser.parse_args()

    from atlas.db import get_engine

    engine = get_engine()

    if args.purge:
        deleted = _purge_mock_data(engine)
        log.info("seed_purged", deleted=deleted)
        print(f"Purged {deleted} mock rows")
        return 0

    inserted = _seed_mock_data(engine)
    print(f"Seeded {inserted} mock performance rows (sentinel positions_count={_SENTINEL})")
    print("Run with --purge before first production nightly run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
