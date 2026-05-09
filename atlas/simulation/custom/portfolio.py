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

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session
from atlas.simulation.backtest.engine import run_backtest
from atlas.simulation.backtest.report import write_backtest_result
from atlas.simulation.core.signal_adapter import build_stock_etf_signal_matrix
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


def run_custom_portfolio_backtest(portfolio_id: UUID, engine: Engine) -> None:
    """Run vectorbt backtest for a saved custom portfolio and link the result.

    Called by the background process. Writes to strategy_backtest_results and
    updates strategy_fm_custom_portfolios.backtest_id when done.
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

    instrument_ids = [i["instrument_id"] for i in instruments_data]

    end_date = date.today()
    start_date = end_date - timedelta(days=_DEFAULT_LOOKBACK_DAYS)

    signal_matrix = build_stock_etf_signal_matrix(
        engine=engine,
        instrument_ids=instrument_ids,
        start_date=start_date,
        end_date=end_date,
        decisions_table="atlas_stock_decisions_daily",
    )

    result = run_backtest(signal_matrix, init_cash=10_000_000.0, fees_pct=0.001)

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


def _fetch_prices(
    instrument_id: str,
    instrument_type: str,
    start_date: date,
    end_date: date,
    engine: Engine,
) -> pd.Series:  # type: ignore[type-arg]
    """Return a date-indexed price Series for a single instrument.

    Branches by instrument_type:
    - 'stock': de_ohlcv_daily.adj_close (or close if adj_close missing)
    - 'etf':   de_etf_ohlcv.close (queries by ticker)
    - 'fund':  de_mf_nav_daily.nav_adj — early date filter enables partition pruning
               (de_mf_nav_daily is year-partitioned; WHERE nav_date >= :sd is required)

    All SQL uses parameterized queries (no f-string interpolation of user input).
    Empty result → empty pd.Series (caller handles missing data).
    """
    if instrument_type == "stock":
        sql = text("""
            SELECT date, adj_close
            FROM public.de_ohlcv_daily
            WHERE instrument_id = :id
              AND date >= :sd
              AND date <= :ed
            ORDER BY date
        """)
        params: dict[str, object] = {
            "id": instrument_id,
            "sd": start_date,
            "ed": end_date,
        }
        date_col = 0
        price_col = 1
    elif instrument_type == "etf":
        sql = text("""
            SELECT date, close
            FROM public.de_etf_ohlcv
            WHERE ticker = :id
              AND date >= :sd
              AND date <= :ed
            ORDER BY date
        """)
        params = {"id": instrument_id, "sd": start_date, "ed": end_date}
        date_col = 0
        price_col = 1
    elif instrument_type == "fund":
        # Partition pruning: early date filter on nav_date so Postgres only
        # scans the year-partitions that overlap the requested range.
        sql = text("""
            SELECT nav_date, nav_adj
            FROM public.de_mf_nav_daily
            WHERE mstar_id = :id
              AND nav_date >= :sd
              AND nav_date <= :ed
            ORDER BY nav_date
        """)
        params = {"id": instrument_id, "sd": start_date, "ed": end_date}
        date_col = 0
        price_col = 1
    else:
        raise ValueError(f"unknown instrument_type: {instrument_type}")

    with engine.connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    if not rows:
        return pd.Series(dtype=float)
    return pd.Series({r[date_col]: float(r[price_col]) for r in rows})
