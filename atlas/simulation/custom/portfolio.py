# atlas/simulation/custom/portfolio.py
"""Orchestrates custom portfolio lifecycle: create -> backtest -> activate paper trading.

Background execution pattern:
  create_custom_portfolio() saves to DB and returns immediately.
  _trigger_backtest_background() submits run_custom_portfolio_backtest() to
  a ProcessPoolExecutor (max_workers=1). The backtest runs in a separate process,
  writes results to DB, and updates custom_portfolio.backtest_id when done.
  The frontend polls /api/portfolios/custom/{id}/status every 5s.

Why ProcessPoolExecutor not threading:
  vectorbt is CPU-bound (NumPy). Python's GIL means threads don't parallelize
  CPU work. A separate process bypasses the GIL and doesn't block the API event loop.
"""

from __future__ import annotations

import atexit
import gc
import json
from concurrent.futures import Future, ProcessPoolExecutor
from datetime import date, timedelta
from uuid import UUID

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session
from atlas.simulation.backtest.engine import run_backtest
from atlas.simulation.backtest.report import write_backtest_result
from atlas.simulation.core.signal_adapter import (
    SignalMatrix,
    build_buy_and_hold_signal_matrix,
    build_fund_signal_matrix,
    build_stock_etf_signal_matrix,
)
from atlas.simulation.custom.builder import InstrumentWeight, validate_custom_portfolio

log = structlog.get_logger()

_EXECUTOR = ProcessPoolExecutor(max_workers=1)
atexit.register(_EXECUTOR.shutdown, wait=True)
_DEFAULT_LOOKBACK_DAYS = 547  # ~18 months of historical data


def create_custom_portfolio(
    name: str,
    instruments: list[InstrumentWeight],
    engine: Engine,
) -> str:
    """Validate, save, and trigger background backtest. Returns portfolio_id (UUID string).

    Raises ValueError if validation fails — DB is never touched on validation failure.
    """
    validate_custom_portfolio(instruments, engine)
    portfolio_id = _save_portfolio_record(name, instruments, engine)
    _trigger_backtest_background(portfolio_id)
    log.info("custom_portfolio_created", portfolio_id=portfolio_id, name=name)
    return portfolio_id


def _save_portfolio_record(
    name: str,
    instruments: list[InstrumentWeight],
    engine: Engine,
) -> str:
    instruments_json = json.dumps(
        [
            {
                "instrument_id": i.instrument_id,
                "instrument_type": i.instrument_type,
                "weight_pct": i.weight_pct,
            }
            for i in instruments
        ]
    )
    with open_compute_session(engine) as conn:
        row_id: str = conn.execute(
            text("""
                INSERT INTO atlas.strategy_fm_custom_portfolios
                    (name, instruments)
                VALUES (:name, CAST(:instruments AS jsonb))
                RETURNING id::text
            """),
            {"name": name, "instruments": instruments_json},
        ).scalar_one()
        conn.commit()
    return row_id


def _on_backtest_future_done(future: Future[None]) -> None:
    exc = future.exception()
    if exc is not None:
        log.error("custom_portfolio_backtest_executor_error", exc_info=exc)


def _trigger_backtest_background(portfolio_id: str) -> None:
    """Submit the backtest to a background ProcessPoolExecutor."""
    future = _EXECUTOR.submit(_run_backtest_subprocess, portfolio_id)
    future.add_done_callback(_on_backtest_future_done)


def _run_backtest_subprocess(portfolio_id: str) -> None:
    """Entry point for the background process. Creates its own DB engine."""
    from atlas.db import get_engine  # imported here to avoid import at module load

    engine = get_engine()
    try:
        run_custom_portfolio_backtest(UUID(portfolio_id), engine)
    except Exception:
        log.exception("custom_portfolio_backtest_failed", portfolio_id=portfolio_id)
        _mark_backtest_failed(portfolio_id, engine)


def _merge_signal_matrices(matrices: list[SignalMatrix]) -> SignalMatrix:
    """Outer-join signal matrices on date index, filling missing entries with False / NaN."""
    non_empty = [m for m in matrices if len(m.instruments) > 0]
    if not non_empty:
        return SignalMatrix(
            prices=np.empty((0, 0)),
            entries=np.empty((0, 0), dtype=bool),
            exits=np.empty((0, 0), dtype=bool),
            dates=pd.DatetimeIndex([]),
            instruments=[],
        )
    if len(non_empty) == 1:
        return non_empty[0]

    dfs_price, dfs_entry, dfs_exit = [], [], []
    for m in non_empty:
        idx = m.dates
        dfs_price.append(pd.DataFrame(m.prices, index=idx, columns=m.instruments))  # type: ignore[arg-type]
        dfs_entry.append(pd.DataFrame(m.entries, index=idx, columns=m.instruments))  # type: ignore[arg-type]
        dfs_exit.append(pd.DataFrame(m.exits, index=idx, columns=m.instruments))  # type: ignore[arg-type]

    price = pd.concat(dfs_price, axis=1).sort_index()
    entry = pd.concat(dfs_entry, axis=1).sort_index().fillna(False)
    exit_ = pd.concat(dfs_exit, axis=1).sort_index().fillna(False)

    # Forward-fill prices per column (funds/equities have different trading calendars).
    # Then drop any row where at least one instrument still has no price — prevents
    # NaN propagation into vectorbt which returns NaN portfolio values.
    price = price.ffill().bfill().dropna(how="any")
    entry = entry.reindex(price.index).fillna(False)
    exit_ = exit_.reindex(price.index).fillna(False)

    instruments = list(price.columns)
    return SignalMatrix(
        prices=price.values.astype(np.float64),
        entries=entry.values.astype(bool),
        exits=exit_.values.astype(bool),
        dates=pd.DatetimeIndex(price.index),
        instruments=instruments,
    )


def run_custom_portfolio_backtest(portfolio_id: UUID, engine: Engine) -> None:
    """Run vectorbt backtest for a saved custom portfolio and link the result.

    Called by the background process. Writes to strategy_backtest_results and
    updates strategy_fm_custom_portfolios.backtest_id when done.

    Handles mixed portfolios (stocks + funds) by building separate signal matrices
    per instrument type then merging on the date axis.
    """
    with open_compute_session(engine) as conn:
        row = conn.execute(
            text("""
                SELECT name, instruments
                FROM atlas.strategy_fm_custom_portfolios
                WHERE id = :pid
            """),
            {"pid": str(portfolio_id)},
        ).fetchone()

    if row is None:
        raise ValueError(f"Custom portfolio {portfolio_id} not found.")

    instruments_data = row.instruments
    if isinstance(instruments_data, str):
        instruments_data = json.loads(instruments_data)

    end_date = date.today()
    start_date = end_date - timedelta(days=_DEFAULT_LOOKBACK_DAYS)

    # Split by instrument type so each gets the right price table and decisions table.
    stock_ids = [i["instrument_id"] for i in instruments_data if i["instrument_type"] == "stock"]
    etf_ids = [i["instrument_id"] for i in instruments_data if i["instrument_type"] == "etf"]
    fund_ids = [i["instrument_id"] for i in instruments_data if i["instrument_type"] == "fund"]

    # Build per-type signal matrices to get prices and exit signals.
    # Entry signals from decisions tables are too sparse for historical backtesting
    # (designed for nightly paper-trading deltas). We use buy-and-hold mode: buy
    # all instruments on day 1, exit only when FM risk rules fire.
    matrices: list[SignalMatrix] = []
    if stock_ids:
        matrices.append(
            build_stock_etf_signal_matrix(
                engine, stock_ids, start_date, end_date, "atlas_stock_decisions_daily"
            )
        )
    if etf_ids:
        matrices.append(
            build_stock_etf_signal_matrix(
                engine, etf_ids, start_date, end_date, "atlas_etf_decisions_daily"
            )
        )
    if fund_ids:
        matrices.append(build_fund_signal_matrix(engine, fund_ids, start_date, end_date))

    raw = _merge_signal_matrices(matrices)
    n_instruments = len(raw.instruments)

    if n_instruments == 0:
        signal_matrix = raw
    else:
        # Convert to buy-and-hold: enter all instruments on day 1, keep exit signals.
        price_df = pd.DataFrame(raw.prices, index=raw.dates, columns=raw.instruments)  # type: ignore[arg-type]
        exit_df = pd.DataFrame(raw.exits, index=raw.dates, columns=raw.instruments)  # type: ignore[arg-type]
        signal_matrix = build_buy_and_hold_signal_matrix(price_df, exit_df)

    log.info(
        "custom_portfolio_backtest_matrix",
        portfolio_id=str(portfolio_id),
        stocks=len(stock_ids),
        etfs=len(etf_ids),
        funds=len(fund_ids),
        combined_instruments=n_instruments,
    )

    result = run_backtest(
        signal_matrix,
        init_cash=10_000_000.0,
        fees_pct=0.001,
        max_positions=n_instruments if n_instruments > 0 else 0,
    )

    backtest_id: str = write_backtest_result(
        engine=engine,
        result=result,
        backtest_type="custom",
        custom_portfolio_id=portfolio_id,
    )

    with open_compute_session(engine) as conn:
        conn.execute(
            text("""
                UPDATE atlas.strategy_fm_custom_portfolios
                SET backtest_id = :bid, updated_at = now()
                WHERE id = :pid
            """),
            {"bid": backtest_id, "pid": str(portfolio_id)},
        )
        conn.commit()

    log.info(
        "custom_portfolio_backtest_done",
        portfolio_id=str(portfolio_id),
        backtest_id=backtest_id,
        sharpe=result.sharpe_ratio,
    )
    del signal_matrix
    gc.collect()


def _mark_backtest_failed(portfolio_id: str, engine: Engine) -> None:
    """Touch updated_at to unblock the polling endpoint on backtest failure."""
    with open_compute_session(engine) as conn:
        conn.execute(
            text("""
                UPDATE atlas.strategy_fm_custom_portfolios
                SET updated_at = now()
                WHERE id = :pid
            """),
            {"pid": portfolio_id},
        )
        conn.commit()
