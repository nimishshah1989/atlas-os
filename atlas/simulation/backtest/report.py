# atlas/simulation/backtest/report.py
"""Write BacktestResult to atlas.strategy_backtest_results."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session
from atlas.simulation.backtest.engine import BacktestResult

log = structlog.get_logger()

BacktestType = Literal["full", "walk_forward", "custom", "3y", "5y", "7y"]
_VALID_TYPES: frozenset[str] = frozenset({"full", "walk_forward", "custom", "3y", "5y", "7y"})


def write_backtest_result(
    engine: Engine,
    result: BacktestResult,
    backtest_type: BacktestType,
    strategy_id: UUID | None = None,
    custom_portfolio_id: UUID | None = None,
) -> str:
    """Insert a BacktestResult into atlas.strategy_backtest_results.

    Returns the new row's UUID as a string.
    backtest_type: 'full' | 'walk_forward' | 'custom'

    Raises ValueError if:
    - backtest_type is not a valid value
    - result has no date range (empty signal matrix guard)
    """
    if backtest_type not in _VALID_TYPES:
        raise ValueError(
            f"Invalid backtest_type {backtest_type!r}. Expected one of {sorted(_VALID_TYPES)}."
        )
    if result.start_date is None or result.end_date is None:
        raise ValueError(
            "Cannot persist a BacktestResult with no date range "
            "(start_date/end_date are None — likely an empty signal matrix)."
        )
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
