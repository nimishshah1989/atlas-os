"""52WH proximity + FIP smoothness + industry-decomposed RS."""

from __future__ import annotations

import numpy as np

from atlas.trading.v6.signals.price_signals import (
    compute_52wh_proximity,
    compute_fip_smoothness,
    compute_industry_rs,
)


def test_52wh_at_high_returns_1():
    """Stock at its 252d max → proximity = 1.0."""
    close = np.array([[100 + i for i in range(252)]], dtype=np.float32)
    out = compute_52wh_proximity(close, window=252)
    assert out[0, -1] == 1.0


def test_52wh_below_high_returns_fraction():
    """Stock 10% below its 252d max → proximity = 0.9."""
    close = np.array([[100.0] * 251 + [90.0]], dtype=np.float32)
    out = compute_52wh_proximity(close, window=252)
    assert abs(out[0, -1] - 0.9) < 0.001


def test_fip_smoothness_all_up_days():
    """All 252 days up → fip = 1.0."""
    close = np.array([[100 + i * 0.1 for i in range(253)]], dtype=np.float32)
    out = compute_fip_smoothness(close, window=252)
    assert out[0, -1] == 1.0


def test_fip_smoothness_alternating_days():
    """Alternating up/down → fip ≈ 0."""
    close = np.array([[100, 101, 100, 101, 100] * 51], dtype=np.float32)
    out = compute_fip_smoothness(close, window=252)
    assert abs(out[0, -1]) < 0.05


def test_industry_rs_isolates_within_sector():
    """Industry RS = stock 3m return - sector 3m return."""
    stock_3m = np.array([0.10, 0.15, 0.20])
    sector_3m = np.array([0.05, 0.10, 0.10])
    out = compute_industry_rs(stock_3m, sector_3m)
    assert np.allclose(out, [0.05, 0.05, 0.10])
