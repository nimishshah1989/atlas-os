from __future__ import annotations

import numpy as np
import pandas as pd

from atlas.compute.cts.primitives import add_sma_slope, add_trp, add_volume_ratio


def _make_ohlcv(n: int = 30) -> pd.DataFrame:
    """Synthetic OHLCV for one instrument."""
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0.5, 2.0, n)
    low = close - rng.uniform(0.5, 2.0, n)
    vol = rng.integers(100_000, 500_000, n).astype(float)
    return pd.DataFrame(
        {
            "instrument_id": ["AAA"] * n,
            "date": pd.date_range("2025-01-01", periods=n),
            "open": close - rng.uniform(0.1, 0.5, n),
            "high": high,
            "low": low,
            "close": close,
            "volume": vol,
        }
    )


def test_add_trp_computes_correct_formula():
    df = _make_ohlcv(30)
    out = add_trp(df)
    expected_trp = (df["high"] - df["low"]) / df["close"] * 100
    pd.testing.assert_series_equal(out["trp"], expected_trp, check_names=False, rtol=1e-6)


def test_add_trp_avg_trp_is_20bar_rolling_mean():
    df = _make_ohlcv(30)
    out = add_trp(df)
    trp_series = (df["high"] - df["low"]) / df["close"] * 100
    expected_avg = trp_series.rolling(20).mean()
    pd.testing.assert_series_equal(out["avg_trp"], expected_avg, check_names=False, rtol=1e-6)


def test_add_trp_ratio_is_trp_over_avg():
    df = _make_ohlcv(30)
    out = add_trp(df)
    mask = out["avg_trp"].notna() & (out["avg_trp"] > 0)
    ratios = out.loc[mask, "trp"] / out.loc[mask, "avg_trp"]
    pd.testing.assert_series_equal(out.loc[mask, "trp_ratio"], ratios, check_names=False, rtol=1e-6)


def test_add_sma_slope_positive_on_uptrend():
    n = 200
    df = pd.DataFrame(
        {
            "instrument_id": ["AAA"] * n,
            "date": pd.date_range("2025-01-01", periods=n),
            "close": np.linspace(100, 200, n),  # clean uptrend
        }
    )
    out = add_sma_slope(df, sma_period=150, slope_days=20)
    # Last row: SMA is rising -> slope positive
    assert out["sma_150_slope"].iloc[-1] > 0


def test_add_volume_ratio_equals_vol_over_20bar_mean():
    df = _make_ohlcv(30)
    out = add_volume_ratio(df)
    expected_avg_vol = df["volume"].rolling(20).mean()
    expected_ratio = df["volume"] / expected_avg_vol
    pd.testing.assert_series_equal(out["vol_ratio"], expected_ratio, check_names=False, rtol=1e-6)
