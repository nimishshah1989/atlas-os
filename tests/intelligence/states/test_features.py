import numpy as np
import pandas as pd
from atlas.intelligence.states.features import (
    atr_14,
    base_depth,
    base_length,
    breadth_above_ma,
    distribution_days_25d,
    ema,
    percent_off_52w_high,
    percent_off_52w_low,
    rs_rank_12m,
    slope,
    sma,
    up_down_volume_ratio_50d,
)


def test_sma_50(trending_up_ohlcv):
    s = sma(trending_up_ohlcv["close"], 50)
    assert s.iloc[:49].isna().all()
    assert not np.isnan(s.iloc[49])
    # SMA should be below current price in an uptrend after 60+ days
    assert s.iloc[60] < trending_up_ohlcv["close"].iloc[60]


def test_ema_21(trending_up_ohlcv):
    e = ema(trending_up_ohlcv["close"], 21)
    assert e.iloc[:20].isna().all()
    assert not np.isnan(e.iloc[20])


def test_slope_positive_in_uptrend(trending_up_ohlcv):
    s = slope(trending_up_ohlcv["close"], 30)
    # After warm-up period, slope should be positive in uptrend most days
    assert (s.iloc[100:].dropna() > 0).mean() > 0.5


def test_atr_14_positive(trending_up_ohlcv):
    a = atr_14(
        trending_up_ohlcv["high"],
        trending_up_ohlcv["low"],
        trending_up_ohlcv["close"],
    )
    assert a.iloc[:13].isna().all()
    assert (a.iloc[14:].dropna() > 0).all()


def test_distribution_days_window_25d(trending_up_ohlcv):
    """Distribution day = close down >= 0.2% AND volume > prev day's volume.
    On a noisy uptrend with random volume, count must be 0..25."""
    dd = distribution_days_25d(trending_up_ohlcv["close"], trending_up_ohlcv["volume"])
    valid = dd.iloc[25:].dropna()
    assert valid.min() >= 0
    assert valid.max() <= 25


def test_percent_off_52w_high_below_25pct(trending_up_ohlcv):
    pct = percent_off_52w_high(trending_up_ohlcv["close"])
    # In an uptrend, % off high should mostly stay within 0-25%
    assert pct.iloc[252:].dropna().mean() < 0.25


def test_percent_off_52w_low_grows_in_uptrend(trending_up_ohlcv):
    pct = percent_off_52w_low(trending_up_ohlcv["close"])
    assert pct.iloc[252:].dropna().mean() > 0.10


def test_up_down_volume_ratio_handles_zero_down():
    """If no down-day volume in window, ratio should be NaN (not inf)."""
    # Force all days up: monotonic close
    close = pd.Series(np.linspace(100, 200, 60))
    volume = pd.Series([100_000] * 60)
    r = up_down_volume_ratio_50d(close, volume)
    # First 50 are NaN; from index 50 onward, no down days so ratio is NaN
    assert r.iloc[50:].isna().all()


def test_base_depth_tight_consolidation():
    """Constant price -> base_depth = 0."""
    close = pd.Series([100.0] * 100)
    bd = base_depth(close, window=60)
    assert bd.iloc[60:].dropna().max() < 1e-6


def test_base_length_increases_while_within_threshold():
    """If price stays near 60d high, base_length should accumulate."""
    close = pd.Series([100.0] * 100)
    bl = base_length(close, threshold=0.15)
    # After 60d warm-up, should accumulate
    assert bl.iloc[80] >= bl.iloc[70]


def test_rs_rank_12m_returns_percentile():
    """rs_rank_12m returns 0..1 percentile rank of stock 12m return vs universe."""
    dates = pd.date_range("2023-01-01", periods=300, freq="B")
    # Stock outperforming
    stock = pd.Series(100.0 * np.cumprod(1 + np.full(300, 0.002)), index=dates)
    # Universe: 100 stocks, this one is in the top
    universe = pd.DataFrame(
        {f"u{i}": np.full(300, 0.05 + i * 0.001) for i in range(100)},
        index=dates,
    )
    ranks = rs_rank_12m(stock, universe)
    # After 252 days, stock 12m return is huge; should rank high
    assert ranks.iloc[260] > 0.5


def test_breadth_above_ma_in_strong_uptrend():
    """In a uniformly-uptrending universe, breadth above 50ma should be ~1."""
    dates = pd.date_range("2023-01-01", periods=300, freq="B")
    universe = pd.DataFrame(
        {f"s{i}": 100.0 * np.cumprod(1 + np.full(300, 0.002 + i * 0.0001)) for i in range(50)},
        index=dates,
    )
    b = breadth_above_ma(universe, 50)
    assert b.iloc[200] > 0.8
