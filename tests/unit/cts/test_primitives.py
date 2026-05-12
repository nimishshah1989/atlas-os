from __future__ import annotations

import numpy as np
import pandas as pd

from atlas.compute.cts.primitives import (
    add_atr14,
    add_pocket_pivot_volume,
    add_sma_slope,
    add_trp,
    add_volume_ratio,
)


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


def test_atr14_is_nonnegative() -> None:
    """ATR is always non-negative; atr_slope is computed on sufficient history."""
    rng = np.random.default_rng(99)
    n = 50
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0.5, 2.0, n)
    low = close - rng.uniform(0.5, 2.0, n)
    df = pd.DataFrame(
        {
            "instrument_id": ["X"] * n,
            "date": pd.date_range("2024-01-01", periods=n),
            "high": high,
            "low": low,
            "close": close,
        }
    )
    out = add_atr14(df)
    atr_vals = out["atr_14"].dropna()
    assert len(atr_vals) > 0
    assert (atr_vals >= 0).all()


def _make_down_day_setup(n: int = 25) -> pd.DataFrame:
    """25 bars: first 20 flat, then 4 down-close days (close < prior close), then 1 spike bar."""
    dates = pd.date_range("2025-01-01", periods=n)
    rows = []
    for i in range(n):
        if i < 20:
            rows.append(
                {
                    "instrument_id": "A",
                    "date": dates[i],
                    "open": 100.0,
                    "close": 100.0,
                    "volume": 200_000.0,
                    "high": 101.0,
                    "low": 99.0,
                }
            )
        elif i < 24:  # 4 down-close days (close drops from 100 to 99.5), moderate volume
            rows.append(
                {
                    "instrument_id": "A",
                    "date": dates[i],
                    "open": 100.0,
                    "close": 99.5,
                    "volume": 300_000.0,
                    "high": 100.5,
                    "low": 99.0,
                }
            )
        else:  # spike bar: volume 400k > max down-day vol (300k), close goes UP
            rows.append(
                {
                    "instrument_id": "A",
                    "date": dates[i],
                    "open": 99.5,
                    "close": 102.0,
                    "volume": 400_000.0,
                    "high": 102.5,
                    "low": 99.0,
                }
            )
    return pd.DataFrame(rows)


def test_pocket_pivot_volume_fires_when_above_down_day_max():
    df = _make_down_day_setup()
    out = add_pocket_pivot_volume(df, window=10)
    assert "is_pp_volume" in out.columns
    assert "pp_vol_threshold" in out.columns
    # Last bar: volume (400k) > max down-day vol (300k)
    last = out.iloc[-1]
    assert bool(
        last["is_pp_volume"]
    ), f"Expected is_pp_volume=True on spike bar, got {last['is_pp_volume']}"


def test_pocket_pivot_volume_does_not_fire_when_below_down_day_max():
    df = _make_down_day_setup()
    # Lower spike bar volume to 250k < max down-day vol (300k)
    df.iloc[-1, df.columns.get_loc("volume")] = 250_000.0
    out = add_pocket_pivot_volume(df, window=10)
    assert not out.iloc[-1]["is_pp_volume"], "volume 250k < down-day max 300k should not fire"


def test_pocket_pivot_volume_no_crash_on_short_history():
    rows = [
        {
            "instrument_id": "A",
            "date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i),
            "open": 100.0,
            "close": 99.0,
            "volume": 100_000.0,
            "high": 101.0,
            "low": 98.0,
        }
        for i in range(5)
    ]
    df = pd.DataFrame(rows)
    out = add_pocket_pivot_volume(df, window=10)
    assert not out["is_pp_volume"].any(), "5-bar series with no prior down-days should not fire"


def test_pocket_pivot_volume_multi_instrument_isolated():
    """Volume threshold is computed independently per instrument.

    Both A and B have genuinely declining closes (each bar closes lower than
    prior bar) so they accumulate real down-day volume history. The final bar
    spikes up in price AND volume, which should fire is_pp_volume for each
    instrument independently.
    """
    dates = pd.date_range("2025-01-01", periods=15)
    # A: closes decline 100.0 -> 98.6 over 14 bars (each bar -0.1), then spike to 102
    rows_a = [
        {
            "instrument_id": "A",
            "date": d,
            "open": 100.0,
            "close": 100.0 - i * 0.1 if i < 14 else 102.0,  # genuine down days
            "volume": 300_000.0 if i < 14 else 400_000.0,
            "high": 101.0,
            "low": 98.0,
        }
        for i, d in enumerate(dates)
    ]
    # B: closes decline 200.0 -> 198.6 over 14 bars (each bar -0.1), then spike to 205
    rows_b = [
        {
            "instrument_id": "B",
            "date": d,
            "open": 200.0,
            "close": 200.0 - i * 0.1 if i < 14 else 205.0,  # genuine down days
            "volume": 100_000.0 if i < 14 else 150_000.0,
            "high": 202.0,
            "low": 197.0,
        }
        for i, d in enumerate(dates)
    ]
    df = pd.DataFrame(rows_a + rows_b)
    out = add_pocket_pivot_volume(df, window=10)
    last_a = out[(out["instrument_id"] == "A") & (out["date"] == dates[-1])].iloc[0]
    last_b = out[(out["instrument_id"] == "B") & (out["date"] == dates[-1])].iloc[0]
    assert last_a["is_pp_volume"], "A: 400k > down-day max 300k should fire"
    assert last_b["is_pp_volume"], "B: 150k > down-day max 100k should fire (isolated)"
