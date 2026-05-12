from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_ta as ta


def add_trp(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    avg_window: int = 20,
) -> pd.DataFrame:
    """Append trp, avg_trp, trp_ratio columns.

    TRP = (high - low) / close * 100. Vectorised across all groups.
    avg_trp = 20-bar SMA of TRP per instrument.
    trp_ratio = trp / avg_trp (NaN when avg_trp is 0 or not yet available).
    """
    out = df.copy().sort_values([group_col, "date"])
    out["trp"] = (out["high"] - out["low"]) / out["close"].replace(0, pd.NA) * 100

    out["avg_trp"] = out.groupby(group_col, observed=True)["trp"].transform(
        lambda s: s.rolling(avg_window, min_periods=avg_window).mean()
    )
    out["trp_ratio"] = out["trp"] / out["avg_trp"].replace(0, pd.NA)
    return out


def add_sma_slope(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    sma_period: int = 150,
    slope_days: int = 20,
) -> pd.DataFrame:
    """Append sma_{sma_period} and sma_{sma_period}_slope columns.

    Slope = (sma_t - sma_{t-slope_days}) / slope_days — normalised change
    per bar. Positive = rising SMA (Stage 2 / Stage 3 condition).
    """
    out = df.copy().sort_values([group_col, "date"])
    col = f"sma_{sma_period}"
    out[col] = out.groupby(group_col, observed=True)["close"].transform(
        lambda s: s.rolling(sma_period, min_periods=sma_period).mean()
    )
    out[f"{col}_slope"] = out.groupby(group_col, observed=True)[col].transform(
        lambda s: s.diff(slope_days) / slope_days
    )
    return out


def add_volume_ratio(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    avg_window: int = 20,
) -> pd.DataFrame:
    """Append avg_vol_20 and vol_ratio columns."""
    out = df.copy().sort_values([group_col, "date"])
    out["avg_vol_20"] = out.groupby(group_col, observed=True)["volume"].transform(
        lambda s: s.rolling(avg_window, min_periods=avg_window).mean()
    )
    out["vol_ratio"] = out["volume"] / out["avg_vol_20"].replace(0, pd.NA)
    return out


def add_pocket_pivot_volume(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    window: int = 10,
) -> pd.DataFrame:
    """Append pp_vol_threshold and is_pp_volume (Morales pocket pivot volume).

    Down day = close strictly below prior close (close < close.shift(1)).
    pp_vol_threshold = rolling max of down-day volume over prior `window` bars
    (shift(1) ensures current bar's volume is excluded from its own lookback).
    is_pp_volume = True when volume > pp_vol_threshold AND threshold is not NaN.
    """
    out = df.copy().sort_values([group_col, "date"])
    threshold_series = pd.Series(index=out.index, dtype=float, name="pp_vol_threshold")

    for _, grp in out.groupby(group_col, observed=True):
        grp_sorted = grp.sort_values("date")
        is_down = grp_sorted["close"] < grp_sorted["close"].shift(1)
        down_vol = grp_sorted["volume"].where(is_down, other=np.nan)
        # shift(1): look at prior bars only; min_periods=1 so we get a threshold as soon
        # as the first down day appears in the window
        pp_thresh = down_vol.shift(1).rolling(window, min_periods=1).max()
        threshold_series.loc[grp_sorted.index] = pp_thresh.values

    out["pp_vol_threshold"] = threshold_series
    # Only fire when threshold is non-NaN (at least 1 down day in prior window)
    out["is_pp_volume"] = out["pp_vol_threshold"].notna() & (
        out["volume"] > out["pp_vol_threshold"]
    )
    return out


def add_atr14(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    length: int = 14,
) -> pd.DataFrame:
    """Append atr_14 via pandas-ta Wilder smoothing, and atr_slope.

    atr_slope = raw linear-regression slope of ATR over last 5 bars (absolute
    price units per bar, not normalised). Negative slope = volatility compressing (Contraction cue).
    """
    out = df.copy().sort_values([group_col, "date"])
    col = f"atr_{length}"

    # Per-group loop avoids groupby.apply shape ambiguity: when the applied
    # function returns a same-length Series, pandas may treat the result as a
    # "reduce" (1 row per group, N columns) rather than a "transform" (N rows).
    # A manual loop with index-loc assignment is unambiguous and correct.
    atr_series = pd.Series(index=out.index, dtype=float, name=col)
    for _, grp in out.groupby(group_col, observed=True):
        vals = ta.atr(  # type: ignore[attr-defined]
            grp["high"].squeeze(),  # type: ignore[arg-type]
            grp["low"].squeeze(),  # type: ignore[arg-type]
            grp["close"].squeeze(),  # type: ignore[arg-type]
            length=length,
        )
        # ta.atr returns None when the group has fewer bars than `length`
        if vals is not None:
            atr_series.loc[grp.index] = vals.values  # type: ignore[index]
        # else: leave as NaN (default); downstream consumers guard on NaN
    out[col] = atr_series

    def _lr_slope(s: pd.Series, window: int = 5) -> pd.Series:
        def _slope(arr: np.ndarray) -> float:
            if np.isnan(arr).any():
                return np.nan
            x = np.arange(len(arr), dtype=float)
            return float(np.polyfit(x, arr, 1)[0])

        return s.rolling(window, min_periods=window).apply(_slope, raw=True)  # type: ignore[return-value]

    out["atr_slope"] = out.groupby(group_col, observed=True)[col].transform(_lr_slope)
    return out
