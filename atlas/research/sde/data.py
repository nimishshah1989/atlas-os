"""SDE Phase 0 data loaders.

Pulls the liquidity-defined universe and an OHLCV panel from
public.de_equity_ohlcv. open/high/low are rescaled by close_adj/close so
all four price columns are corporate-action consistent; close itself
becomes close_adj. Rows with a null/zero close_adj fall back to raw prices.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = structlog.get_logger()

# Liquid universe over the window: instruments whose median daily traded
# value (close * volume) clears the floor. Self-PIT — no index membership.
_UNIVERSE_SQL = """
    SELECT instrument_id::text AS instrument_id
      FROM public.de_equity_ohlcv
     WHERE date BETWEEN :start AND :end
       AND data_status IN ('raw', 'validated')
       AND close > 0 AND volume > 0
     GROUP BY instrument_id
    HAVING PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY close * volume) >= :floor_inr
"""

_OHLCV_SQL = """
    SELECT date,
           instrument_id::text AS instrument_id,
           open, high, low, close, close_adj, volume
      FROM public.de_equity_ohlcv
     WHERE date BETWEEN :start AND :end
       AND instrument_id = ANY(CAST(:ids AS uuid[]))
       AND data_status IN ('raw', 'validated')
     ORDER BY instrument_id, date
"""


def load_liquid_universe(
    engine: Engine, *, start: date, end: date, floor_inr: float = 5e7
) -> list[str]:
    """Return instrument_id strings whose median traded value clears the floor.

    floor_inr default 5e7 = Rs 5 crore.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(_UNIVERSE_SQL),
            {"start": start, "end": end, "floor_inr": floor_inr},
        ).all()
    ids = [r.instrument_id for r in rows]
    log.info("sde_universe", n_instruments=len(ids))
    return ids


def adjust_ohlc(long_df: pd.DataFrame) -> pd.DataFrame:
    """Rescale open/high/low by the close_adj/close ratio and set close=close_adj.

    Where close_adj is null or close is non-positive, ratio falls back to 1.0
    and close falls back to the raw close.
    """
    df = long_df.copy()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["close_adj"] = pd.to_numeric(df["close_adj"], errors="coerce")
    ratio = (df["close_adj"] / df["close"]).where(df["close_adj"].notna() & (df["close"] > 0), 1.0)
    for col in ("open", "high", "low"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df[col] = df[col] * ratio
    df["close"] = df["close_adj"].where(df["close_adj"].notna(), df["close"])
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    out: pd.DataFrame = df[["date", "instrument_id", "open", "high", "low", "close", "volume"]]  # type: ignore[assignment]
    return out


def mask_extreme_moves(panel: pd.DataFrame, *, max_daily_move: float = 0.40) -> pd.DataFrame:
    """Null open/high/low/close on rows whose close-to-close move exceeds
    `max_daily_move`. Volume is kept.

    Validation of public.de_equity_ohlcv (2026-05-20) showed close_adj
    adjustment is ~99.99% sound but leaves a tiny tail of artifacts:
    unadjusted splits, two corrupt tickers, and extreme single-day crashes
    (~443 rows / 0.009% over a 2-year window). Nulling the price columns on
    those rows means every downstream factor and forward return skips them,
    so factor IC is not polluted by price artifacts.
    """
    df = panel.sort_values(["instrument_id", "date"]).copy()
    daily_ret = df.groupby("instrument_id")["close"].pct_change()
    extreme = daily_ret.abs() > max_daily_move
    for col in ("open", "high", "low", "close"):
        df.loc[extreme, col] = float("nan")
    return df


def load_ohlcv_panel(
    engine: Engine, *, instrument_ids: Sequence[str], start: date, end: date
) -> pd.DataFrame:
    """Load a corporate-action-adjusted, artifact-masked OHLCV long DataFrame.

    Returns columns: date, instrument_id, open, high, low, close, volume.
    Applies adjust_ohlc (corporate-action rescaling) then mask_extreme_moves
    (nulls price artifacts).
    """
    with engine.connect() as conn:
        long_df = pd.read_sql(
            text(_OHLCV_SQL),
            conn,
            params={"start": start, "end": end, "ids": list(instrument_ids)},
        )
    if long_df.empty:
        return long_df
    panel = mask_extreme_moves(adjust_ohlc(long_df))
    log.info(
        "sde_ohlcv_panel",
        rows=len(panel),
        instruments=panel["instrument_id"].nunique(),
    )
    return panel
