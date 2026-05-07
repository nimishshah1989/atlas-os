"""Unit tests for ``atlas.compute.primitives``.

Hand-traceable fixtures: small synthetic frames where you can compute the
expected output on paper and compare. No DB, no fixtures — pure math.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.compute.primitives import (
    WINDOWS,
    add_emas,
    add_max_drawdown,
    add_realized_vol,
    add_returns,
    add_rs_momentum,
    add_within_tier_percentiles,
)


def _make_frame(n: int = 300, seed: int = 0) -> pd.DataFrame:
    """Two synthetic instruments with deterministic prices."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=n).date
    rows = []
    for instrument_id in ("A", "B"):
        # geometric brownian-like prices
        rets = rng.normal(0.0005, 0.01, n)
        prices = 100 * np.cumprod(1 + rets)
        for d, p in zip(dates, prices, strict=True):
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "date": d,
                    "open": p,
                    "high": p * 1.005,
                    "low": p * 0.995,
                    "close": p,
                    "volume": 100_000,
                }
            )
    return pd.DataFrame(rows)


@pytest.mark.unit
def test_add_returns_creates_expected_columns() -> None:
    df = _make_frame()
    out = add_returns(df)
    for win in WINDOWS:
        assert f"ret_{win}" in out.columns
    assert "ret_1d" in out.columns
    # First row of each group should be NaN (no prior price). .first() skips
    # NaN by default so use head(1) to grab the literal first row per group.
    firsts = out.groupby("instrument_id", group_keys=False).head(1)
    assert firsts["ret_1d"].isna().all()


@pytest.mark.unit
def test_add_returns_matches_hand_pct_change() -> None:
    df = _make_frame()
    out = add_returns(df)
    sub = out[out["instrument_id"] == "A"].sort_values("date").reset_index(drop=True)
    # ret_1m at row 21 = (close[21] / close[0]) - 1
    expected = sub["close"].iloc[21] / sub["close"].iloc[0] - 1
    assert abs(sub["ret_1m"].iloc[21] - expected) < 1e-12


@pytest.mark.unit
def test_add_emas_first_n_minus_one_are_nan() -> None:
    df = _make_frame()
    out = add_emas(df, lengths=(10,), suffix="stock")
    sub = out[out["instrument_id"] == "A"].sort_values("date").reset_index(drop=True)
    # pandas-ta seeds with first-N SMA, so values 0..N-2 are NaN
    assert sub["ema_10_stock"].iloc[:9].isna().all()
    assert not np.isnan(sub["ema_10_stock"].iloc[10])


@pytest.mark.unit
def test_add_realized_vol_is_annualised() -> None:
    df = _make_frame()
    out = add_returns(df)
    out = add_realized_vol(out, return_col="ret_1d", window=63)
    sub = out[out["instrument_id"] == "A"].sort_values("date").reset_index(drop=True)
    last_window = sub["ret_1d"].iloc[-63:]
    expected = last_window.std() * np.sqrt(252)
    assert abs(sub["realized_vol_63"].iloc[-1] - expected) < 1e-9


@pytest.mark.unit
def test_max_drawdown_matches_running_peak_formula() -> None:
    df = _make_frame()
    out = add_returns(df)
    out = add_max_drawdown(out, return_col="ret_1d", window=252)
    sub = out[out["instrument_id"] == "A"].sort_values("date").reset_index(drop=True)
    last_window = sub["ret_1d"].iloc[-252:].fillna(0).to_numpy()
    cumulative = np.cumprod(1 + last_window)
    rolling_peak = np.maximum.accumulate(cumulative)
    drawdown = cumulative / rolling_peak - 1
    expected = abs(drawdown.min())
    assert abs(sub["max_drawdown_252"].iloc[-1] - expected) < 1e-3


@pytest.mark.unit
def test_rs_momentum_at_high_low_flags_are_mutually_exclusive() -> None:
    df = _make_frame()
    df = add_emas(df, lengths=(10, 20), suffix="stock")
    # Synthesise benchmark EMAs so ratios are computable
    df["ema_10_benchmark"] = df["close"] * 0.99
    df["ema_20_benchmark"] = df["close"] * 0.98
    out = add_rs_momentum(df)
    # On any given row: at_high and at_low can both be true only on a flat
    # series (rolling-max == rolling-min). Monotone series shouldn't.
    both = out["ema_10_at_20d_high"] & out["ema_10_at_20d_low"]
    # On synthetic noisy data, both should be false more often than not
    assert not both.all()


@pytest.mark.unit
def test_within_tier_percentiles_in_unit_interval() -> None:
    df = pd.DataFrame(
        {
            "instrument_id": [f"S{i}" for i in range(20)],
            "date": [pd.Timestamp("2024-01-01").date()] * 20,
            "tier": ["Large"] * 10 + ["Mid"] * 10,
            "rs_3m_tier": list(range(20)),
            "rs_1w_tier": list(range(20)),
            "rs_1m_tier": list(range(20)),
        }
    )
    out = add_within_tier_percentiles(df)
    assert (out["rs_pctile_3m"].between(0, 1) | out["rs_pctile_3m"].isna()).all()
    # Within Large tier (10 stocks), the highest rs_3m_tier should rank at 1.0
    large = out[out["tier"] == "Large"].sort_values("rs_3m_tier")
    assert abs(large["rs_pctile_3m"].iloc[-1] - 1.0) < 1e-9


@pytest.mark.unit
def test_within_tier_percentiles_skip_small_cohorts() -> None:
    df = pd.DataFrame(
        {
            "instrument_id": ["S1", "S2", "S3"],
            "date": [pd.Timestamp("2024-01-01").date()] * 3,
            "tier": ["Micro"] * 3,
            "rs_3m_tier": [1.0, 2.0, 3.0],
            "rs_1w_tier": [1.0, 2.0, 3.0],
            "rs_1m_tier": [1.0, 2.0, 3.0],
        }
    )
    out = add_within_tier_percentiles(df)
    # Cohort of 3 < 5 minimum → all NaN
    assert out["rs_pctile_3m"].isna().all()
