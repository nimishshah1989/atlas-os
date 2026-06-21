"""Canonical technicals for the Atlas data foundation — TA-Lib only.

Locked decision (docs/atlas-data-foundation.md §4): all technicals via TA-Lib,
no hand-rolled formulas. This module is the SINGLE definition used by both:
  - the PoC compute step (writes technicals into staging), and
  - the harness metrics axis (recompute-and-diff vs stored).
Because both call the same functions, "recompute matches stored" is meaningful.

All inputs are adjusted close series ordered ascending by date.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import talib

# Return / RS windows in trading days (docs §4: 1d/1w/1m/3m/6m/12m).
RETURN_WINDOWS: dict[str, int] = {
    "1d": 1,
    "1w": 5,
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "12m": 252,
}

EMA_PERIODS = (21, 50, 200)  # docs §4: breadth uses 21-EMA (not 20), plus 50/200.
RSI_PERIOD = 14


def ema(close: pd.Series, period: int) -> pd.Series:
    """Exponential moving average via TA-Lib."""
    out = talib.EMA(close.to_numpy(dtype="float64"), timeperiod=period)
    return pd.Series(out, index=close.index)


def rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """Wilder RSI via TA-Lib."""
    out = talib.RSI(close.to_numpy(dtype="float64"), timeperiod=period)
    return pd.Series(out, index=close.index)


def trailing_return(close: pd.Series, window: int) -> pd.Series:
    """Simple trailing return over `window` trading days: c[t]/c[t-window]-1."""
    return close / close.shift(window) - 1.0


def compute_price_technicals(close: pd.Series) -> pd.DataFrame:
    """EMA 21/50/200, RSI(14), and trailing returns for one instrument.

    `close` is an ascending, date-indexed adjusted-close series. Returns a frame
    indexed identically with one column per metric (NaN where insufficient lookback).
    """
    out = pd.DataFrame(index=close.index)
    for p in EMA_PERIODS:
        out[f"ema_{p}"] = ema(close, p)
    out[f"rsi_{RSI_PERIOD}"] = rsi(close, RSI_PERIOD)
    for name, w in RETURN_WINDOWS.items():
        out[f"ret_{name}"] = trailing_return(close, w)
    return out


def compute_relative_strength(
    stock_close: pd.Series, bench_close: pd.Series, suffix: str
) -> pd.DataFrame:
    """Relative strength = stock trailing return minus benchmark trailing return.

    Computed for each window; `suffix` labels the benchmark (e.g. 'n50','n500').
    Benchmark series is reindexed onto the stock's dates (forward-fill within span).
    """
    bench = bench_close.reindex(stock_close.index).ffill()
    out = pd.DataFrame(index=stock_close.index)
    for name, w in RETURN_WINDOWS.items():
        s = trailing_return(stock_close, w)
        b = trailing_return(bench, w)
        out[f"rs_{name}_{suffix}"] = s - b
    return out


def above_ema_flags(close: pd.Series, tech: pd.DataFrame) -> pd.DataFrame:
    """Boolean: is close above its 21/50/200 EMA (for breadth counts)."""
    out = pd.DataFrame(index=close.index)
    for p in EMA_PERIODS:
        out[f"above_ema_{p}"] = close > tech[f"ema_{p}"]
    return out


def max_abs_log_jump(close: pd.Series) -> float:
    """Largest absolute 1-day log return — flags split/adjustment errors.

    A clean adjusted series should have no |log return| implying a >~50% 1-day move
    (≈0.4) outside genuine corp-action handling. This is the FMCG +249.8% detector.
    """
    c = close.replace(0, np.nan).dropna()
    if len(c) < 2:
        return 0.0
    lr = np.log(c.to_numpy()[1:] / c.to_numpy()[:-1])
    return float(np.nanmax(np.abs(lr))) if len(lr) else 0.0
