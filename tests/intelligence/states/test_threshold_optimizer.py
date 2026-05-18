"""Tests for threshold_optimizer.py — IC-validation grid-sweep harness.

Naming: test_<function>_<scenario>_<expected>
All tests use synthetic data only (no DB, no real signals).
"""

from datetime import date

import numpy as np
import pandas as pd

from atlas.intelligence.states.threshold_optimizer import (
    ThresholdTuningResult,
    tune_single_threshold,
)


def _synthetic_factor_returns():
    """Build factor series + forward returns where one threshold clearly wins.

    Pattern: stocks ranked top-30% by some metric have +5% forward returns;
    bottom-70% have +0%. The optimal θ to discriminate is around the 70th
    percentile cutoff.
    """
    n_stocks = 100
    n_days = 60
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    instruments = [f"s{i:03d}" for i in range(n_stocks)]
    # Metric: per-stock fixed score
    scores = np.linspace(0, 1, n_stocks)  # 0..1, evenly spaced
    # Forward returns: top-30% earn +5%, bottom-70% earn 0%
    fwd_rets = np.where(scores > 0.70, 0.05, 0.0)
    factor = (
        pd.DataFrame(
            {iid: [scores[i]] * n_days for i, iid in enumerate(instruments)},
            index=dates,
        )
        .stack()
        .to_frame("factor")
    )
    factor.index = factor.index.set_names(["date", "instrument_id"])
    returns_wide = pd.DataFrame(
        {iid: [fwd_rets[i]] * n_days for i, iid in enumerate(instruments)},
        index=dates,
    )
    return factor, returns_wide


def test_tune_single_threshold_picks_best_cutoff():
    """When evidence is clear (top-30% outperform), optimizer picks θ near 0.70."""
    factor, returns_wide = _synthetic_factor_returns()
    candidates = [0.30, 0.50, 0.70, 0.80, 0.90]
    result = tune_single_threshold(
        threshold_name="theta_test",
        state="stage_test",
        factor=factor,
        returns_wide=returns_wide,
        candidates=candidates,
        as_of=date(2024, 2, 28),
    )
    assert isinstance(result, ThresholdTuningResult)
    # Optimal should be near the true cutoff (0.70). 0.80 may also work.
    assert result.optimal_value in (0.70, 0.80)
    # IC at optimal should be non-trivial
    assert result.ic_ir > 0.0


def test_tune_single_threshold_returns_ic_metrics():
    factor, returns_wide = _synthetic_factor_returns()
    result = tune_single_threshold(
        threshold_name="theta_test",
        state="stage_test",
        factor=factor,
        returns_wide=returns_wide,
        candidates=[0.5, 0.7, 0.9],
        as_of=date(2024, 2, 28),
    )
    # All per-candidate IC values should be populated
    assert len(result.per_candidate_ic) == 3
    for _candidate, ic in result.per_candidate_ic.items():
        assert "mean_ic" in ic
        assert "ic_ir" in ic
        assert "q5_q1_spread" in ic


def test_tune_single_threshold_empty_factor():
    """Empty factor → no optimal threshold found, returns None or sentinel."""
    factor = pd.DataFrame(columns=["factor"])
    factor.index = pd.MultiIndex.from_tuples([], names=["date", "instrument_id"])
    returns_wide = pd.DataFrame(index=pd.DatetimeIndex([]))
    result = tune_single_threshold(
        threshold_name="theta_test",
        state="stage_test",
        factor=factor,
        returns_wide=returns_wide,
        candidates=[0.5, 0.7],
        as_of=date(2024, 1, 1),
    )
    assert result.optimal_value is None or np.isnan(result.optimal_value) is True


def test_tune_single_threshold_no_passing_candidate():
    """If no candidate achieves IR > 0.4 AND |q5_q1| > 0.005, optimal is the highest-IR fallback."""
    # All candidates equally non-predictive (constant returns)
    n_stocks = 50
    n_days = 30
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    instruments = [f"s{i:02d}" for i in range(n_stocks)]
    scores = np.linspace(0, 1, n_stocks)
    factor = (
        pd.DataFrame(
            {iid: [scores[i]] * n_days for i, iid in enumerate(instruments)},
            index=dates,
        )
        .stack()
        .to_frame("factor")
    )
    factor.index = factor.index.set_names(["date", "instrument_id"])
    # All returns identical → IC undefined / zero
    returns_wide = pd.DataFrame(0.01, index=dates, columns=instruments)
    result = tune_single_threshold(
        threshold_name="theta_test",
        state="stage_test",
        factor=factor,
        returns_wide=returns_wide,
        candidates=[0.3, 0.5, 0.7],
        as_of=date(2024, 1, 30),
    )
    # Should still return a result but with a flag/note that nothing passed gates
    assert result is not None
    assert hasattr(result, "passed_gates")
