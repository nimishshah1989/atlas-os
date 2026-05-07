"""Unit tests for ``atlas.compute.gates``."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.compute.gates import (
    LIQUIDITY_FLOOR_INR,
    add_history_gate,
    add_liquidity_gate,
    add_weinstein_gate,
)


def _series(prices: list[float], volume: float = 1e6) -> pd.DataFrame:
    """Single-instrument frame with the given closing prices."""
    n = len(prices)
    dates = pd.date_range("2024-01-01", periods=n).date
    return pd.DataFrame(
        {
            "instrument_id": ["A"] * n,
            "date": dates,
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [volume] * n,
        }
    )


@pytest.mark.unit
def test_history_gate_flips_at_min_days() -> None:
    df = _series([100] * 300)
    out = add_history_gate(df, min_days=252)
    assert not out["history_gate_pass"].iloc[251]
    assert out["history_gate_pass"].iloc[252]
    assert out["history_gate_pass"].iloc[-1]


@pytest.mark.unit
def test_liquidity_gate_passes_when_above_floor() -> None:
    # ₹1 cr × 1e6 = ₹1e10, well above ₹5cr floor
    df = _series([100] * 100, volume=1e6)
    out = add_liquidity_gate(df)
    # First 40 rows: insufficient history for rolling-60 median
    assert out["liquidity_gate_pass"].iloc[60:].all()


@pytest.mark.unit
def test_liquidity_gate_fails_when_below_floor() -> None:
    # ₹10 × 100 = ₹1k traded value, far below ₹5cr
    df = _series([10] * 100, volume=100)
    out = add_liquidity_gate(df)
    assert not out["liquidity_gate_pass"].iloc[60:].any()


@pytest.mark.unit
def test_weinstein_gate_passes_on_uptrend() -> None:
    # Steadily rising prices → MA rising → weinstein pass
    n = 300
    prices = list(np.linspace(100, 200, n))
    df = _series(prices)
    out = add_weinstein_gate(df)
    # By day 280 the MA has settled and slope is firmly positive
    assert out["weinstein_gate_pass"].iloc[280]


@pytest.mark.unit
def test_weinstein_gate_fails_on_downtrend() -> None:
    n = 300
    prices = list(np.linspace(200, 100, n))
    df = _series(prices)
    out = add_weinstein_gate(df)
    assert not out["weinstein_gate_pass"].iloc[-1]


@pytest.mark.unit
def test_liquidity_floor_is_5_crore() -> None:
    """Sanity check: methodology says ₹5 crore = 5,00,00,000."""
    assert LIQUIDITY_FLOOR_INR == 50_000_000  # 5 cr in paise-free integer form
