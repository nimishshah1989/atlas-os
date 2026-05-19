"""quality.py — price-based quality proxy (v0.1)."""

from __future__ import annotations

import numpy as np

from atlas.trading.v6.signals.quality import compute_quality_proxy


def test_low_vol_low_dd_high_consistency_ranks_highest():
    """Low vol + low drawdown + high ret consistency → highest quality score."""
    # 3 stocks, 1 time period (column vector shape)
    # Stock 0: best quality (low vol, low DD, high consistency)
    # Stock 1: average
    # Stock 2: worst quality (high vol, high DD, low consistency)
    realized_vol = np.array([[0.05], [0.15], [0.30]])  # low→high
    max_dd = np.array([[0.05], [0.15], [0.35]])  # low→high
    ret_12m = np.array([[0.20], [0.10], [-0.05]])  # high→low
    worst_q_ret = np.array([[-0.02], [-0.05], [-0.15]])  # small loss → large loss

    out = compute_quality_proxy(realized_vol, max_dd, ret_12m, worst_q_ret)

    # Stock 0 should have the highest quality score
    assert out[0, 0] > out[1, 0] > out[2, 0]


def test_quality_returns_correct_shape():
    """Output shape matches input shape."""
    n_stocks, n_days = 5, 10
    vol = np.random.rand(n_stocks, n_days).astype(np.float32) * 0.3
    dd = np.random.rand(n_stocks, n_days).astype(np.float32) * 0.4
    ret = np.random.rand(n_stocks, n_days).astype(np.float32) * 0.2 - 0.05
    worst_q = -(np.random.rand(n_stocks, n_days).astype(np.float32) * 0.1 + 0.01)
    out = compute_quality_proxy(vol, dd, ret, worst_q)
    assert out.shape == (n_stocks, n_days)


def test_quality_handles_zero_worst_quarter():
    """Zero worst_quarter_ret → consistency = 0, no division by zero."""
    vol = np.array([[0.1]])
    dd = np.array([[0.1]])
    ret = np.array([[0.1]])
    worst_q = np.array([[0.0]])  # Zero — should not raise
    out = compute_quality_proxy(vol, dd, ret, worst_q)
    assert np.isfinite(out).all()
