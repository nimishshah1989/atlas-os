"""Per-stock hit-rate primitive.

For each instrument with conviction history, looks back ``lookback_window``
trading days. For each day in that window where the stock's conviction
was at or above the tier-median conviction on that day, check whether
the realized 21-day forward return beat the tier-median forward return.

Output: ``HitRateRow(instrument_id, date, lookback_window,
n_high_conviction_days, n_positive_outcomes, hit_rate)``.

``hit_rate`` is ``None`` when ``n_high_conviction_days < MIN_OBSERVATIONS``
so the UI knows to render '—' rather than an unstable percentage.

Batch implementation is vectorized: load conviction window + price matrix
+ forward returns ONCE, then groupby per instrument. Single-stock helper
delegates to the batch when called individually (kept for test ergonomics).
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


def compute_hit_rates_batch(
    engine: Engine,
    *,
    as_of: date,
    lookback_window: int = DEFAULT_LOOKBACK_WINDOW,
    forward_horizon: int = DEFAULT_FORWARD_HORIZON,
) -> list[HitRateRow]:
    """Compute hit-rate for every instrument with conviction in the window.

    Vectorized: loads conviction + prices + forward returns once, then
    groups by instrument_id for the per-stock aggregation. ~30 seconds
    for ~700 instruments vs ~15 minutes for the per-stock loop.
    """
    df = _load_conviction_window(
        engine,
        as_of=as_of,
        lookback_window=lookback_window,
        forward_horizon=forward_horizon,
    )
    if df.empty:
        return []

    # 1. tier-median conviction per date — for is_high_conv flag.
    medians = _tier_medians_per_date(df)
    df = df.merge(medians, on=["date", "tier"], how="left")
    df["is_high_conv"] = df["conviction_score"] >= df["tier_median_conviction"]

    # 2. Load price matrix once for all instruments in scope.
    start = as_of - timedelta(days=lookback_window + forward_horizon + 7)
    end = as_of + timedelta(days=forward_horizon + 7)
    prices = load_price_matrix(engine, start_date=start, end_date=end)
    if prices.empty:
        log.warning("hit_rate_batch_no_prices", as_of=str(as_of))
        return []

    # 3. Forward returns per (date, instrument) — single compute, then long.
    fwd_multi = compute_forward_returns(prices, periods=[forward_horizon])
    fwd_wide = fwd_multi[f"return_{forward_horizon}d"]
    fwd_long = (
        fwd_wide.stack()
        .rename("fwd_ret")
        .reset_index()
        .rename(columns={"level_1": "instrument_id"})
    )
    fwd_long["date"] = pd.to_datetime(fwd_long["date"])

    # 4. tier-median forward return per date — needed for the
    #    "did this stock beat tier median?" comparison.
    df_with_fwd = df.merge(fwd_long, on=["date", "instrument_id"], how="left")
    tier_fwd = (
        df_with_fwd.groupby(["date", "tier"])["fwd_ret"]
        .median()
        .reset_index()
        .rename(columns={"fwd_ret": "tier_median_fwd"})
    )
    df_with_fwd = df_with_fwd.merge(tier_fwd, on=["date", "tier"], how="left")
    df_with_fwd["beat_tier"] = df_with_fwd["fwd_ret"] > df_with_fwd["tier_median_fwd"]

    # 5. Restrict to high-conviction rows with a realized forward return,
    #    then groupby instrument to count n_high / n_pos.
    eligible = df_with_fwd[df_with_fwd["is_high_conv"] & df_with_fwd["fwd_ret"].notna()]
    if eligible.empty:
        log.info("hit_rate_batch_no_eligible_rows", as_of=str(as_of))
        return []
    grouped = eligible.groupby("instrument_id").agg(
        n_high=("is_high_conv", "size"),
        n_pos=("beat_tier", "sum"),
    )

    # 6. Today's tier per instrument (for tier_at_as_of audit field).
    today_rows = df[df["date"] == pd.Timestamp(as_of)]
    tier_today: dict[str, str] = {}
    if not today_rows.empty:
        for _, r in today_rows.iterrows():
            tier_today[str(r["instrument_id"])] = str(r["tier"])

    # 7. Materialize as HitRateRow list — keep contract identical to the
    #    per-stock helper so callers don't change.
    out: list[HitRateRow] = []
    for iid, row in grouped.iterrows():
        n_high = int(row["n_high"])
        n_pos = int(row["n_pos"])
        hit_rate = n_pos / n_high if n_high >= MIN_OBSERVATIONS else None
        out.append(
            HitRateRow(
                instrument_id=str(iid),
                date=as_of,
                lookback_window=lookback_window,
                n_high_conviction_days=n_high,
                n_positive_outcomes=n_pos,
                hit_rate=hit_rate,
                tier_at_as_of=tier_today.get(str(iid)),
            )
        )

    log.info(
        "hit_rate_batch_complete",
        as_of=str(as_of),
        n_instruments=len(out),
        lookback=lookback_window,
    )
    return out


def compute_hit_rate_for_stock(
    engine: Engine,
    *,
    instrument_id: str,
    as_of: date,
    lookback_window: int = DEFAULT_LOOKBACK_WINDOW,
    forward_horizon: int = DEFAULT_FORWARD_HORIZON,
) -> HitRateRow | None:
    """Compute one HitRateRow for a specific instrument.

    Delegates to ``compute_hit_rates_batch`` and filters. Kept as a
    convenience for tests and ad-hoc queries; production code should use
    the batch path.
    """
    rows = compute_hit_rates_batch(
        engine,
        as_of=as_of,
        lookback_window=lookback_window,
        forward_horizon=forward_horizon,
    )
    for r in rows:
        if r.instrument_id == instrument_id:
            return r
    return None
