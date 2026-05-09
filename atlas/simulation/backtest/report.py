# atlas/simulation/backtest/report.py
"""Write BacktestResult to atlas.strategy_backtest_results."""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session
from atlas.simulation.backtest.engine import BacktestResult

log = structlog.get_logger()


def write_backtest_result(
    engine: Engine,
    result: BacktestResult,
    backtest_type: str,
    strategy_id: UUID | None = None,
    custom_portfolio_id: UUID | None = None,
) -> str:
    """Insert a BacktestResult into atlas.strategy_backtest_results.

    Returns the new row's UUID as a string.
    backtest_type: 'full' | 'walk_forward' | 'custom'
    """
    with open_compute_session(engine) as conn:
        row_id: str = conn.execute(
            text("""
                INSERT INTO atlas.strategy_backtest_results
                    (strategy_id, custom_portfolio_id, backtest_type,
                     start_date, end_date,
                     sharpe_ratio, max_drawdown, total_return)
                VALUES
                    (:sid, :cpid, :btype,
                     :start_date, :end_date,
                     :sharpe, :drawdown, :total_return)
                RETURNING id::text
            """),
            {
                "sid": str(strategy_id) if strategy_id else None,
                "cpid": str(custom_portfolio_id) if custom_portfolio_id else None,
                "btype": backtest_type,
                "start_date": result.start_date,
                "end_date": result.end_date,
                "sharpe": result.sharpe_ratio,
                "drawdown": result.max_drawdown,
                "total_return": result.total_return,
            },
        ).scalar_one()
        conn.commit()

    log.info(
        "backtest_report_written",
        backtest_id=row_id,
        backtest_type=backtest_type,
        sharpe=result.sharpe_ratio,
    )
    return row_id
