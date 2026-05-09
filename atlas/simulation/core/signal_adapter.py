# atlas/simulation/core/signal_adapter.py
"""Bridges JIP prices and Atlas signals into a SignalMatrix for vectorbt.

Joins de_equity_ohlcv (JIP equity) + atlas_*_decisions_daily (Atlas) on (instrument_id, date).
Funds join de_mf_nav_history on mstar_id. Instruments with no price data are excluded with
a structlog warning (never silent).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session

log = structlog.get_logger()

# Allowlist guards the f-string table interpolation below.
# Parameterized table names are not supported in SQL — allowlist is the correct defence.
_ALLOWED_DECISIONS_TABLES = frozenset(
    {
        "atlas_stock_decisions_daily",
        "atlas_etf_decisions_daily",
    }
)


class StaleJIPDataError(RuntimeError):
    pass


@dataclass
class SignalMatrix:
    prices: np.ndarray  # shape (n_dates, n_instruments), float64
    entries: np.ndarray  # shape (n_dates, n_instruments), bool
    exits: np.ndarray  # shape (n_dates, n_instruments), bool
    dates: pd.DatetimeIndex
    instruments: list[str]

    def to_vectorbt(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return self.prices, self.entries, self.exits


def check_jip_staleness(engine: Engine, today: date) -> None:
    """Raise StaleJIPDataError if JIP data hasn't landed for today."""
    with open_compute_session(engine) as conn:
        jip_max = conn.execute(text("SELECT MAX(date) FROM de_ohlcv_daily")).scalar()
    if jip_max is None or jip_max < today:
        msg = f"JIP data last updated {jip_max}, expected {today}. Aborting; will retry tomorrow."
        raise StaleJIPDataError(msg)


def build_stock_etf_signal_matrix(
    engine: Engine,
    instrument_ids: list[str],
    start_date: date,
    end_date: date,
    decisions_table: str,
) -> SignalMatrix:
    """Load stock or ETF signals + JIP prices into a SignalMatrix.

    Args:
        decisions_table: 'atlas_stock_decisions_daily' for stocks,
                         'atlas_etf_decisions_daily' for ETFs.
    """
    if decisions_table not in _ALLOWED_DECISIONS_TABLES:
        raise ValueError(
            f"Invalid decisions_table {decisions_table!r}. "
            f"Allowed: {sorted(_ALLOWED_DECISIONS_TABLES)}"
        )

    query = text(f"""
        SELECT
            d.date,
            d.instrument_id,
            p.close                                              AS price,
            (d.transition_trigger OR d.breakout_trigger)        AS entry_signal,
            (
                d.exit_market_riskoff OR d.exit_rs_deteriorate
                OR d.exit_momentum_collapse OR d.exit_volume_distrib
                OR d.exit_sector_avoid OR d.exit_stop_loss
            )                                                    AS exit_signal
        FROM atlas.{decisions_table} d
        JOIN de_equity_ohlcv p
            ON p.instrument_id = d.instrument_id AND p.date = d.date
        WHERE d.instrument_id = ANY(:ids)
          AND d.date BETWEEN :start_date AND :end_date
        ORDER BY d.date, d.instrument_id
    """)

    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            query,
            conn,
            params={"ids": instrument_ids, "start_date": start_date, "end_date": end_date},
        )

    if df.empty:
        log.warning(
            "signal_adapter_empty",
            decisions_table=decisions_table,
            instruments=len(instrument_ids),
            start_date=str(start_date),
            end_date=str(end_date),
        )
        return SignalMatrix(
            prices=np.empty((0, 0)),
            entries=np.empty((0, 0), dtype=bool),
            exits=np.empty((0, 0), dtype=bool),
            dates=pd.DatetimeIndex([]),
            instruments=[],
        )

    missing_price = df.loc[df["price"].isna(), "instrument_id"].unique()
    if len(missing_price) > 0:
        log.warning(
            "signal_adapter_missing_prices",
            instruments=list(missing_price),
            count=len(missing_price),
        )
    df = df.dropna(subset=["price"])

    pivot_price = df.pivot(index="date", columns="instrument_id", values="price").sort_index()
    pivot_entry = (
        df.pivot(index="date", columns="instrument_id", values="entry_signal")
        .sort_index()
        .fillna(False)
    )
    pivot_exit = (
        df.pivot(index="date", columns="instrument_id", values="exit_signal")
        .sort_index()
        .fillna(False)
    )

    instruments = list(pivot_price.columns)
    dates = pd.DatetimeIndex(pivot_price.index)

    return SignalMatrix(
        prices=pivot_price.values.astype(np.float64),
        entries=pivot_entry.values.astype(bool),
        exits=pivot_exit.values.astype(bool),
        dates=dates,
        instruments=instruments,
    )


def build_fund_signal_matrix(
    engine: Engine,
    instrument_ids: list[str],
    start_date: date,
    end_date: date,
) -> SignalMatrix:
    """Load fund signals + NAV prices into a SignalMatrix."""
    query = text("""
        SELECT
            d.date,
            d.mstar_id             AS instrument_id,
            n.nav                  AS price,
            d.entry_trigger        AS entry_signal,
            (
                d.exit_market_riskoff OR d.exit_composition_misaligned
                OR d.exit_holdings_weak OR d.exit_nav_deteriorate
            )                      AS exit_signal
        FROM atlas.atlas_fund_decisions_daily d
        JOIN de_mf_nav_history n
            ON n.mstar_id = d.mstar_id AND n.date = d.date
        WHERE d.mstar_id = ANY(:ids)
          AND d.date BETWEEN :start_date AND :end_date
        ORDER BY d.date, d.instrument_id
    """)

    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            query,
            conn,
            params={"ids": instrument_ids, "start_date": start_date, "end_date": end_date},
        )

    if df.empty:
        return SignalMatrix(
            prices=np.empty((0, 0)),
            entries=np.empty((0, 0), dtype=bool),
            exits=np.empty((0, 0), dtype=bool),
            dates=pd.DatetimeIndex([]),
            instruments=[],
        )

    missing_nav = df.loc[df["price"].isna(), "instrument_id"].unique()
    if len(missing_nav) > 0:
        log.warning("signal_adapter_missing_nav", instruments=list(missing_nav))
    df = df.dropna(subset=["price"])

    pivot_price = df.pivot(index="date", columns="instrument_id", values="price").sort_index()
    pivot_entry = (
        df.pivot(index="date", columns="instrument_id", values="entry_signal")
        .sort_index()
        .fillna(False)
    )
    pivot_exit = (
        df.pivot(index="date", columns="instrument_id", values="exit_signal")
        .sort_index()
        .fillna(False)
    )

    return SignalMatrix(
        prices=pivot_price.values.astype(np.float64),
        entries=pivot_entry.values.astype(bool),
        exits=pivot_exit.values.astype(bool),
        dates=pd.DatetimeIndex(pivot_price.index),
        instruments=list(pivot_price.columns),
    )
