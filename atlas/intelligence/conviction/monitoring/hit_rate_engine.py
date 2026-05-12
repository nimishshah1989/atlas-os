"""Per-stock hit-rate primitive.

For each instrument with conviction history, looks back ``lookback_window``
trading days. For each day in that window where the stock's conviction
was at or above the tier-median conviction on that day, check whether
the realized 21-day forward return beat the tier-median forward return.

Output: ``HitRateRow(instrument_id, date, lookback_window,
n_high_conviction_days, n_positive_outcomes, hit_rate)``.

``hit_rate`` is ``None`` when ``n_high_conviction_days < MIN_OBSERVATIONS``
so the UI knows to render '—' rather than an unstable percentage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.validation.forward_returns import (
    compute_forward_returns,
    load_price_matrix,
)

log = structlog.get_logger()

DEFAULT_LOOKBACK_WINDOW: Final[int] = 20
DEFAULT_FORWARD_HORIZON: Final[int] = 21
MIN_OBSERVATIONS: Final[int] = 5


@dataclass(frozen=True)
class HitRateRow:
    instrument_id: str
    date: date
    lookback_window: int
    n_high_conviction_days: int
    n_positive_outcomes: int
    hit_rate: float | None
    tier_at_as_of: str | None


def _load_conviction_window(
    engine: Engine,
    *,
    as_of: date,
    lookback_window: int,
    forward_horizon: int,
) -> pd.DataFrame:
    """Load conviction + tier rows for every instrument over the window."""
    start = as_of - timedelta(days=lookback_window + forward_horizon + 7)
    sql = text("""
        SELECT instrument_id::text AS instrument_id,
               date, tier, conviction_score
        FROM atlas.atlas_stock_conviction_daily
        WHERE date BETWEEN :start AND :end
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"start": start, "end": as_of})
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["conviction_score"] = pd.to_numeric(df["conviction_score"], errors="coerce")
    return df


def _tier_medians_per_date(df: pd.DataFrame) -> pd.DataFrame:
    """Return (date, tier) → median conviction_score across that tier."""
    return (
        df.groupby(["date", "tier"])["conviction_score"]
        .median()
        .reset_index()
        .rename(columns={"conviction_score": "tier_median_conviction"})
    )


def compute_hit_rate_for_stock(
    engine: Engine,
    *,
    instrument_id: str,
    as_of: date,
    lookback_window: int = DEFAULT_LOOKBACK_WINDOW,
    forward_horizon: int = DEFAULT_FORWARD_HORIZON,
) -> HitRateRow | None:
    """Compute one HitRateRow. ``None`` if no conviction data in window."""
    df = _load_conviction_window(
        engine,
        as_of=as_of,
        lookback_window=lookback_window,
        forward_horizon=forward_horizon,
    )
    if df.empty:
        return None
    stock_df = df[df["instrument_id"] == instrument_id]
    if stock_df.empty:
        return None

    medians = _tier_medians_per_date(df)
    joined = stock_df.merge(medians, on=["date", "tier"], how="left")
    joined["is_high_conv"] = joined["conviction_score"] >= joined["tier_median_conviction"]

    # Forward returns for THIS stock — load price matrix once for the window
    start = as_of - timedelta(days=lookback_window + forward_horizon + 7)
    end = as_of + timedelta(days=forward_horizon + 7)
    prices = load_price_matrix(engine, start_date=start, end_date=end)
    if prices.empty or instrument_id not in prices.columns:
        return None
    fwd = compute_forward_returns(prices, periods=[forward_horizon])
    fwd_wide = fwd[f"return_{forward_horizon}d"]
    fwd_series = fwd_wide[instrument_id]
    fwd_series.name = "fwd_ret"
    fwd_series = fwd_series.reset_index()
    fwd_series["date"] = pd.to_datetime(fwd_series["date"])

    joined = joined.merge(fwd_series, on="date", how="left")

    # Tier-median forward returns: median fwd_ret across the tier per date
    tier_fwd = (
        df.merge(
            fwd_wide.stack()
            .rename("fwd_ret")
            .reset_index()
            .rename(columns={"level_1": "instrument_id"}),
            on=["date", "instrument_id"],
            how="left",
        )
        .groupby(["date", "tier"])["fwd_ret"]
        .median()
        .reset_index()
        .rename(columns={"fwd_ret": "tier_median_fwd"})
    )
    tier_fwd["date"] = pd.to_datetime(tier_fwd["date"])
    joined = joined.merge(tier_fwd, on=["date", "tier"], how="left")

    eligible = joined[joined["is_high_conv"] & joined["fwd_ret"].notna()]
    n_high = int(len(eligible))
    n_pos = int((eligible["fwd_ret"] > eligible["tier_median_fwd"]).sum())
    hit_rate = None
    if n_high >= MIN_OBSERVATIONS:
        hit_rate = n_pos / n_high
    tier_at_as_of: str | None = None
    today_rows: pd.DataFrame = stock_df.loc[stock_df["date"] == pd.Timestamp(as_of)]
    if len(today_rows) > 0:
        tier_at_as_of = str(today_rows.iloc[0]["tier"])

    return HitRateRow(
        instrument_id=instrument_id,
        date=as_of,
        lookback_window=lookback_window,
        n_high_conviction_days=n_high,
        n_positive_outcomes=n_pos,
        hit_rate=hit_rate,
        tier_at_as_of=tier_at_as_of,
    )


def compute_hit_rates_batch(
    engine: Engine,
    *,
    as_of: date,
    lookback_window: int = DEFAULT_LOOKBACK_WINDOW,
    forward_horizon: int = DEFAULT_FORWARD_HORIZON,
) -> list[HitRateRow]:
    """Compute hit-rate for every instrument that has conviction in the window."""
    df = _load_conviction_window(
        engine,
        as_of=as_of,
        lookback_window=lookback_window,
        forward_horizon=forward_horizon,
    )
    if df.empty:
        return []
    instrument_ids = df["instrument_id"].unique().tolist()
    out: list[HitRateRow] = []
    for iid in instrument_ids:
        row = compute_hit_rate_for_stock(
            engine,
            instrument_id=iid,
            as_of=as_of,
            lookback_window=lookback_window,
            forward_horizon=forward_horizon,
        )
        if row is not None:
            out.append(row)
    log.info(
        "hit_rate_batch_complete",
        as_of=str(as_of),
        n_instruments=len(out),
        lookback=lookback_window,
    )
    return out
