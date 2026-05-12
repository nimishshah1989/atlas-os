from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

import numpy as np
import pandas as pd

from atlas.compute.cts.primitives import add_sma_slope


def classify_stage(
    df: pd.DataFrame,
    *,
    thresholds: Mapping[str, Decimal],
    group_col: str = "instrument_id",
) -> pd.DataFrame:
    """Append stage (1–4), is_stage1b, sma_150, sma_150_slope columns.

    Stage rules (Weinstein, adapted for NSE daily bars):
      2 = price > SMA_150 AND close momentum (slope_days diff) > 0  (advancing)
      3 = price > SMA_150 AND close momentum <= 0                    (topping)
      1 = price <= SMA_150 AND SMA slope (rounded 2dp) >= 0          (basing)
      4 = price <= SMA_150 AND SMA slope (rounded 2dp) < 0           (declining)
      1B = stage 1 AND price within <=3% below SMA_150

    Stage 2/3 use close momentum rather than SMA slope so that topping
    (Stage 3) is detectable before the 150-bar SMA itself turns negative.
    Stage 1/4 use SMA slope rounded to 2dp to avoid floating-point noise
    from single-bar changes on an otherwise flat series.

    NaN stage when SMA_150 not yet computable (< 150 bars).
    """
    sma_period = int(thresholds["cts_stage2_sma_period"])
    slope_days = int(thresholds["cts_stage2_slope_min_days"])

    out = add_sma_slope(df, sma_period=sma_period, slope_days=slope_days)
    sma_col = f"sma_{sma_period}"
    slope_col = f"{sma_col}_slope"

    # Close-based momentum for Stage 2/3 (reactive to price reversal)
    close_slope: pd.Series = out.groupby(group_col, observed=True)["close"].transform(
        lambda s: s.diff(slope_days) / slope_days
    )

    above = out["close"] > out[sma_col]
    has_sma = out[sma_col].notna()
    rising = close_slope > 0
    # SMA slope rounded to 2dp avoids single-bar floating-point noise on flat series
    sma_rising = out[slope_col].round(2) >= 0

    conditions = [
        has_sma & above & rising,  # Stage 2
        has_sma & above & ~rising,  # Stage 3
        has_sma & ~above & sma_rising,  # Stage 1
        has_sma & ~above & ~sma_rising,  # Stage 4
    ]
    choices = [2, 3, 1, 4]
    stage_arr = np.select(conditions, choices, default=np.nan)
    out["stage"] = pd.array(
        [None if np.isnan(v) else int(v) for v in stage_arr],
        dtype=object,
    )

    # Stage 1B: price within <=3% below SMA (coiling before breakout)
    prox = (out[sma_col] - out["close"]) / out[sma_col]
    out["is_stage1b"] = (out["stage"] == 1) & (prox <= float(Decimal("0.03")))

    out.rename(columns={sma_col: "sma_150", slope_col: "sma_150_slope"}, inplace=True)
    return out
