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
    out["trp"] = (out["high"] - out["low"]) / out["close"] * 100

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


def add_atr14(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    length: int = 14,
) -> pd.DataFrame:
    """Append atr_14 via pandas-ta Wilder smoothing, and atr_slope.

    atr_slope = linear-regression slope of ATR over last 5 bars (normalised
    by current ATR). Negative slope = volatility compressing (Contraction cue).
    """
    out = df.copy().sort_values([group_col, "date"])
    col = f"atr_{length}"

    def _atr(g: pd.DataFrame) -> pd.Series:
        result = ta.atr(  # type: ignore[attr-defined]
            g["high"].squeeze(),  # type: ignore[arg-type]
            g["low"].squeeze(),  # type: ignore[arg-type]
            g["close"].squeeze(),  # type: ignore[arg-type]
            length=length,
        )
        return pd.Series(result, index=g.index)  # type: ignore[return-value]

    out[col] = (
        out.groupby(group_col, group_keys=False, observed=True)
        .apply(_atr)
        .reset_index(level=0, drop=True)
    )

    def _lr_slope(s: pd.Series, window: int = 5) -> pd.Series:
        def _slope(arr: np.ndarray) -> float:
            if np.isnan(arr).any():
                return np.nan
            x = np.arange(len(arr), dtype=float)
            return float(np.polyfit(x, arr, 1)[0])

        return s.rolling(window, min_periods=window).apply(_slope, raw=True)  # type: ignore[return-value]

    out["atr_slope"] = out.groupby(group_col, observed=True)[col].transform(_lr_slope)
    return out
