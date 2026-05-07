"""Pre-classification gates and the Weinstein absolute-trend gate.

Per methodology §3.3 (gates) and §7.1 (Weinstein). All vectorised; no Python
row loops.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

LIQUIDITY_FLOOR_INR = 5_00_00_000
"""₹5 crore trailing 60-day median traded value, methodology §3.3."""


def add_history_gate(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    min_days: int = 252,
) -> pd.DataFrame:
    """``history_gate_pass`` is True once the instrument has ≥``min_days`` of OHLCV.

    Computed as ``cumcount() >= min_days`` per group — no rolling-window cost.
    """
    out = df.copy().sort_values([group_col, "date"])
    out["history_gate_pass"] = out.groupby(group_col, observed=True).cumcount() >= min_days
    return out


def add_liquidity_gate(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    floor_inr: int = LIQUIDITY_FLOOR_INR,
) -> pd.DataFrame:
    """``liquidity_gate_pass`` = trailing 60-day median traded value ≥ ₹5 cr.

    ``traded_value = close × volume``. Median is robust to single-day spikes,
    per methodology §3.3.
    """
    out = df.copy().sort_values([group_col, "date"])
    out["traded_value"] = out["close"] * out["volume"]
    out["median_traded_value_60d"] = out.groupby(group_col, group_keys=False, observed=True)[
        "traded_value"
    ].transform(lambda s: s.rolling(60, min_periods=40).median())
    out["liquidity_gate_pass"] = out["median_traded_value_60d"] >= floor_inr
    return out


def add_weinstein_gate(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    price_col: str = "close",
    ma_window: int = 150,
    slope_window: int = 20,
    sigma_window: int = 252,
    sigma_threshold: float = -0.5,
) -> pd.DataFrame:
    """Weinstein gate per methodology §7.1.

    Two conditions ANDed:

    1. ``close > MA(150)`` — price above 30-week MA.
    2. ``MA(150) slope over last 20 days >= -0.5σ`` — flat or rising, where σ
       is the 252-day rolling stdev of the same slope series.
    """
    out = df.copy().sort_values([group_col, "date"])
    grouped = out.groupby(group_col, group_keys=False, observed=True)[price_col]

    out["ma_30w"] = grouped.transform(
        lambda s: s.rolling(ma_window, min_periods=int(ma_window * 2 // 3)).mean()
    )

    out["above_30w_ma"] = out[price_col] > out["ma_30w"]

    ma_grouped = out.groupby(group_col, group_keys=False, observed=True)["ma_30w"]
    out["ma_30w_shift"] = ma_grouped.shift(slope_window)
    out["ma_30w_slope_4w"] = (out["ma_30w"] - out["ma_30w_shift"]) / out["ma_30w_shift"]

    slope_std = out.groupby(group_col, group_keys=False, observed=True)[
        "ma_30w_slope_4w"
    ].transform(lambda s: s.rolling(sigma_window, min_periods=int(sigma_window * 2 // 3)).std())
    out["ma_30w_slope_4w_sigma"] = out["ma_30w_slope_4w"] / slope_std

    # Degenerate case: a perfectly constant slope yields slope_std == 0 / NaN,
    # so sigma is undefined. Fall back to the raw slope sign — non-negative
    # slopes count as flat-or-rising regardless of sigma.
    sigma_pass = out["ma_30w_slope_4w_sigma"] >= sigma_threshold
    sigma_undef = out["ma_30w_slope_4w_sigma"].isna() | ~np.isfinite(out["ma_30w_slope_4w_sigma"])
    out["ma_flat_or_rising"] = np.where(
        sigma_undef, out["ma_30w_slope_4w"].fillna(0) >= 0, sigma_pass
    )
    out["weinstein_gate_pass"] = out["above_30w_ma"].fillna(False) & out[
        "ma_flat_or_rising"
    ].fillna(False)

    out = out.drop(columns=["ma_30w_shift"])
    return out


def add_stage1_base(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    state_col: str = "rs_state",
    weak_states: tuple[str, ...] = ("Average", "Weak", "Laggard"),
    bootstrap_window: int = 50,
) -> pd.DataFrame:
    """Stage-1 base detection per methodology §7.1.

    A stock qualifies when:

    * Was classified in {Average, Weak, Laggard} for ≥8 of last 10 weekly closes
      (approx. ≥40 of last 50 trading days).
    * 30-week MA flat (``|slope_sigma| ≤ 0.5``).

    Bootstrap (per ``prds/00_INFRA_DECISIONS.md`` §4): during the first
    ``bootstrap_window`` trading days, only the MA-flat condition is required —
    the historical-states check would always fail on insufficient data.
    """
    out = df.copy().sort_values([group_col, "date"])

    is_weak = out[state_col].isin(weak_states)
    weak_count_50d = out.groupby(group_col, group_keys=False, observed=True)[state_col].transform(
        lambda s, w=is_weak: w.loc[s.index].rolling(50, min_periods=10).sum()
    )
    base_history_qualifies = weak_count_50d >= 40  # ~8 of 10 weekly closes

    ma_flat = out.get("ma_30w_slope_4w_sigma", pd.Series(np.nan, index=out.index))
    ma_flat_pass = ma_flat.abs() <= 0.5

    days_seen = out.groupby(group_col, observed=True).cumcount()
    in_bootstrap = days_seen < bootstrap_window

    out["stage1_base_qualifies"] = np.where(
        in_bootstrap,
        ma_flat_pass.fillna(False),
        (base_history_qualifies.fillna(False) & ma_flat_pass.fillna(False)),
    )
    return out
