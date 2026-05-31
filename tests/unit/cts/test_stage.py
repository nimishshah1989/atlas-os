# tests/unit/cts/test_stage.py
from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd

from atlas.compute.cts.stage import classify_stage


def _uptrend_df(n: int = 200) -> pd.DataFrame:
    close = np.linspace(80, 120, n)  # clean uptrend, ends above SMA
    return pd.DataFrame(
        {
            "instrument_id": ["AAA"] * n,
            "date": pd.date_range("2025-01-01", periods=n),
            "close": close,
        }
    )


def _downtrend_df(n: int = 200) -> pd.DataFrame:
    close = np.linspace(120, 80, n)  # clean downtrend
    return pd.DataFrame(
        {
            "instrument_id": ["AAA"] * n,
            "date": pd.date_range("2025-01-01", periods=n),
            "close": close,
        }
    )


THRESHOLDS = {
    "cts_stage2_sma_period": Decimal("150"),
    "cts_stage2_slope_min_days": Decimal("20"),
    "cts_stage1b_proximity_pct": Decimal("0.03"),
}


def test_stage2_on_uptrend():
    df = _uptrend_df()
    out = classify_stage(df, thresholds=THRESHOLDS)
    last = out.iloc[-1]
    assert last["stage"] == 2
    assert last["sma_150_slope"] > 0


def test_stage4_on_downtrend():
    df = _downtrend_df()
    out = classify_stage(df, thresholds=THRESHOLDS)
    last = out.iloc[-1]
    assert last["stage"] == 4


def test_stage_null_before_sma_period():
    df = _uptrend_df(200)
    out = classify_stage(df, thresholds=THRESHOLDS)
    # First 149 rows have no SMA → stage should be None
    assert out.iloc[148]["stage"] is None or pd.isna(out.iloc[148]["stage"])


def test_stage1_on_basing_pattern():
    """Stage 1: price below flat SMA."""
    n = 200
    close = np.full(n, 100.0)
    df = pd.DataFrame(
        {
            "instrument_id": ["AAA"] * n,
            "date": pd.date_range("2025-01-01", periods=n),
            "close": close,
        }
    )
    out = classify_stage(df, thresholds=THRESHOLDS)
    last = out.iloc[-1]
    # Flat SMA, price = SMA → close <= SMA, slope >= 0 → Stage 1
    assert last["stage"] == 1, f"expected Stage 1, got {last['stage']}"


def test_stage3_on_topping_pattern():
    """Stage 3: price above SMA but SMA slope turning negative."""
    n = 200
    close = list(np.linspace(80, 130, 160)) + list(np.linspace(130, 115, 40))
    df = pd.DataFrame(
        {
            "instrument_id": ["AAA"] * n,
            "date": pd.date_range("2025-01-01", periods=n),
            "close": close,
        }
    )
    out = classify_stage(df, thresholds=THRESHOLDS)
    stage_at_180 = out.iloc[180]["stage"]
    assert stage_at_180 == 3, f"expected Stage 3 at peak pullback, got {stage_at_180}"


def test_stage1b_boundary_exclusive():
    """Stage 1B: price within <=3% below SMA uses <= not <."""
    n = 200
    close_arr = np.full(n, 100.0)
    close_arr[-1] = 97.0  # exactly 3% below SMA
    df_at_boundary = pd.DataFrame(
        {
            "instrument_id": ["AAA"] * n,
            "date": pd.date_range("2025-01-01", periods=n),
            "close": close_arr,
        }
    )
    out = classify_stage(df_at_boundary, thresholds=THRESHOLDS)
    assert out.iloc[-1]["is_stage1b"], (
        "price at exactly 3% below SMA should trigger Stage 1B (<=, not <)"
    )

    close_arr2 = np.full(n, 100.0)
    close_arr2[-1] = 96.9  # 3.1% below SMA
    df_outside = pd.DataFrame(
        {
            "instrument_id": ["AAA"] * n,
            "date": pd.date_range("2025-01-01", periods=n),
            "close": close_arr2,
        }
    )
    out2 = classify_stage(df_outside, thresholds=THRESHOLDS)
    assert not out2.iloc[-1]["is_stage1b"], "price at 3.1% below SMA should NOT trigger Stage 1B"
