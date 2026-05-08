# atlas/simulation/core/metrics.py
"""Daily return backfill for strategy_paper_performance.

Called by m7_daily.py after run_nightly() to compute and write the actual
daily_return = (today_value / yesterday_value) - 1 for each strategy.
"""

from __future__ import annotations

from datetime import date

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session

log = structlog.get_logger()


def backfill_daily_returns(engine: Engine, today: date) -> int:
    """Compute and update daily_return for all strategies on today.

    Uses the previous trading day's total_value from strategy_paper_performance.
    Returns: count of rows updated.
    """
    sql = text("""
        WITH yesterday AS (
            SELECT strategy_id, total_value AS prev_value
            FROM atlas.strategy_paper_performance
            WHERE date = (
                SELECT MAX(date) FROM atlas.strategy_paper_performance
                WHERE date < :today
            )
        )
        UPDATE atlas.strategy_paper_performance p
        SET daily_return = (p.total_value / y.prev_value) - 1
        FROM yesterday y
        WHERE p.strategy_id = y.strategy_id
          AND p.date = :today
          AND y.prev_value > 0
    """)
    with open_compute_session(engine) as conn:
        result = conn.execute(sql, {"today": today})
        conn.commit()
    updated = result.rowcount if result.rowcount is not None else 0
    log.info("metrics_daily_returns_backfilled", date=str(today), updated=updated)
    return updated
