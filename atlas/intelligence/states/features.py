"""Derived metric calculators for the state classifier.

Pure functions of OHLCV (price + volume). No I/O. All return pandas Series
indexed identically to input. NaN where the rolling window isn't full.

All functions are deterministic and side-effect-free. The state classifier
composes these into rule predicates. The threshold optimizer (Phase 2)
treats them as fixed; only the theta in classifier rules are tuned.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple moving average over `window` periods."""
    return series.rolling(window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average.

    NaN for the first `span - 1` rows; first value anchored at row `span - 1`.
    """
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def slope(series: pd.Series, window: int) -> pd.Series:
    """Linear-regression slope over `window` periods, normalized by mean.

    Returns slope per period as a fraction of the rolling mean — i.e.,
    'fractional change per period'. Positive in an uptrend, negative in a
    downtrend. Multiply by `window` for total drift over the window.
    """

    def _fit(arr: np.ndarray) -> float:
        if np.isnan(arr).any():
            return float("nan")
        x = np.arange(len(arr), dtype=float)
        mean = arr.mean()
        if mean == 0:
            return 0.0
        return float(np.polyfit(x, arr, 1)[0]) / mean

    return series.rolling(window, min_periods=window).apply(_fit, raw=True)


def atr_14(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
) -> pd.Series:
    """Average true range over 14 periods.

    TR = max(H - L, |H - prev_close|, |L - prev_close|).
    First 13 rows are NaN (warm-up).
    """
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(14, min_periods=14).mean()


def distribution_days_25d(
    close: pd.Series,
    volume: pd.Series,
) -> pd.Series:
    """Count distribution days in trailing 25 trading days.

    A 'distribution day' = close down >= 0.2% AND volume > previous day's
    volume. Returns an integer Series (Int64 with NA support).
    """
    daily_ret = close.pct_change()
    vol_up = volume > volume.shift(1)
    is_dd = (daily_ret <= -0.002) & vol_up
    return is_dd.rolling(25, min_periods=1).sum().astype("Int64")


def percent_off_52w_high(close: pd.Series) -> pd.Series:
    """(52w_high - close) / 52w_high.

    0 = at the 52-week high; 0.30 = 30% below the 52-week high.
    NaN for the first 251 rows (warm-up).
    """
    high_252 = close.rolling(252, min_periods=252).max()
    return (high_252 - close) / high_252


def percent_off_52w_low(close: pd.Series) -> pd.Series:
    """(close - 52w_low) / 52w_low.

    0 = at the 52-week low; 0.30 = 30% above the 52-week low.
    NaN for the first 251 rows (warm-up).
    """
    low_252 = close.rolling(252, min_periods=252).min()
    return (close - low_252) / low_252


def up_down_volume_ratio_50d(
    close: pd.Series,
    volume: pd.Series,
) -> pd.Series:
    """sum(volume on up-days) / sum(volume on down-days) over trailing 50 days.

    NaN when no down-day volume in window (avoids division by zero / inf).
    Flat days (pct_change == 0) are excluded from both buckets.
    """
    daily_ret = close.pct_change()
    up_vol = volume.where(daily_ret > 0, 0.0)
    down_vol = volume.where(daily_ret < 0, 0.0)
    up_sum = up_vol.rolling(50, min_periods=50).sum()
    down_sum = down_vol.rolling(50, min_periods=50).sum()
    return up_sum / down_sum.replace(0, np.nan)


def base_depth(close: pd.Series, window: int = 60) -> pd.Series:
    """Depth of current base: (high_window - low_window) / high_window.

    Small values (< 0.15) indicate tight consolidation — good Stage 1 base.
    NaN for first `window - 1` rows.
    """
    high_w = close.rolling(window, min_periods=window).max()
    low_w = close.rolling(window, min_periods=window).min()
    return (high_w - low_w) / high_w


def base_length(close: pd.Series, threshold: float = 0.15) -> pd.Series:
    """Trailing days the price has stayed within `threshold` of trailing 60d high.

    Long base = high value. Resets to 0 whenever price breaks below the band.
    Returns an Int64 Series (nullable integer).
    """
    high_60 = close.rolling(60, min_periods=60).max()
    within = (close / high_60) > (1 - threshold)
    # Group resets: each False flips the cumsum group id
    grp = (~within).cumsum()
    return within.groupby(grp).cumsum().astype("Int64")


def rs_rank_12m(
    stock_close: pd.Series,
    universe_returns: pd.DataFrame,
) -> pd.Series:
    """12-month total-return percentile rank vs universe, per date.

    Args:
        stock_close: This stock's close series, indexed by date.
        universe_returns: DataFrame indexed by date with columns=instrument_ids,
            values = 12-month total returns (already computed, e.g. via
            ``close / close.shift(252) - 1``). Universe must be re-rankable
            on each date the stock is alive.

    Returns:
        Series of 0..1 percentiles (1.0 = top performer). NaN before 12 months
        of stock history or for dates the universe is empty (< 10 members).
    """
    stock_12m = stock_close / stock_close.shift(252) - 1
    ranks = pd.Series(index=stock_close.index, dtype=float)
    for dt in stock_close.index:
        if dt not in universe_returns.index:
            ranks.loc[dt] = float("nan")
            continue
        universe_day = universe_returns.loc[dt].dropna()
        stock_ret = stock_12m.loc[dt]
        if len(universe_day) < 10 or pd.isna(stock_ret):
            ranks.loc[dt] = float("nan")
            continue
        ranks.loc[dt] = float((universe_day < stock_ret).sum() / len(universe_day))
    return ranks


def breadth_above_ma(
    universe_closes: pd.DataFrame,
    ma_window: int,
) -> pd.Series:
    """Percentage of universe trading above their `ma_window`-period SMA, per date.

    Args:
        universe_closes: DataFrame indexed by date, columns = instrument_ids,
            values = closing prices.
        ma_window: SMA window (e.g., 50, 200).

    Returns:
        Series indexed by date, values in 0..1. NaN for dates before the
        SMA warm-up window is full for at least one instrument.
    """
    ma = universe_closes.rolling(ma_window, min_periods=ma_window).mean()
    above = (universe_closes > ma).astype(float)
    return above.mean(axis=1, skipna=True)
