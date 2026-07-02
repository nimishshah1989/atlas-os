"""Tests for the IC engine — pure pandas, no DB."""

import numpy as np
import pandas as pd
import pytest
from atlas.intelligence.validation.ic_engine import (
    ICResult,
    compute_ic_over_window,
    compute_quantile_spread,
    compute_rolling_ic,
    compute_turnover,
)


@pytest.fixture
def perfect_signal():
    """Factor exactly equal to forward return — IC should be 1.0."""
    dates = pd.date_range("2025-01-01", periods=60, freq="B")
    instruments = [f"INST{i:03d}" for i in range(50)]
    np.random.seed(42)
    factor_data = []
    return_data = []
    for d in dates:
        for inst in instruments:
            x = np.random.randn()
            factor_data.append((d, inst, x))
            return_data.append((d, inst, x))
    factor_df = pd.DataFrame(factor_data, columns=["date", "instrument_id", "factor"])
    factor_df = factor_df.set_index(["date", "instrument_id"])
    returns_df = pd.DataFrame(return_data, columns=["date", "instrument_id", "ret"])
    returns_wide = returns_df.pivot(index="date", columns="instrument_id", values="ret")
    return factor_df, returns_wide


@pytest.fixture
def noise_signal():
    """Factor uncorrelated with returns — IC should be ≈ 0."""
    dates = pd.date_range("2025-01-01", periods=60, freq="B")
    instruments = [f"INST{i:03d}" for i in range(50)]
    np.random.seed(42)
    factor_data = []
    return_data = []
    for d in dates:
        for inst in instruments:
            factor_data.append((d, inst, np.random.randn()))
            return_data.append((d, inst, np.random.randn()))
    factor_df = pd.DataFrame(factor_data, columns=["date", "instrument_id", "factor"])
    factor_df = factor_df.set_index(["date", "instrument_id"])
    returns_df = pd.DataFrame(return_data, columns=["date", "instrument_id", "ret"])
    returns_wide = returns_df.pivot(index="date", columns="instrument_id", values="ret")
    return factor_df, returns_wide


class TestComputeICOverWindow:
    def test_perfect_signal_gives_ic_one(self, perfect_signal):
        factor, returns = perfect_signal
        result = compute_ic_over_window(factor, returns)
        assert result.mean_ic == pytest.approx(1.0, abs=1e-6)

    def test_noise_signal_gives_ic_near_zero(self, noise_signal):
        factor, returns = noise_signal
        result = compute_ic_over_window(factor, returns)
        assert abs(result.mean_ic) < 0.1  # noise — should be near zero

    def test_returns_icresult_dataclass(self, noise_signal):
        factor, returns = noise_signal
        result = compute_ic_over_window(factor, returns)
        assert isinstance(result, ICResult)
        assert hasattr(result, "mean_ic")
        assert hasattr(result, "ic_std")
        assert hasattr(result, "ic_t_stat")
        assert hasattr(result, "n_observations")


class TestComputeRollingIC:
    def test_returns_one_row_per_window(self, noise_signal):
        factor, returns = noise_signal
        results = compute_rolling_ic(factor, returns, window_days=20, step_days=5)
        # 60 days, window 20, step 5 → roughly (60-20)/5+1 = 9 windows
        assert len(results) >= 7


class TestComputeQuantileSpread:
    def test_perfect_signal_has_positive_spread(self, perfect_signal):
        factor, returns = perfect_signal
        spread = compute_quantile_spread(factor, returns, n_quantiles=5)
        assert spread > 0.0


class TestComputeTurnover:
    def test_stable_signal_has_low_turnover(self):
        """If quintile membership doesn't change, turnover is 0."""
        dates = pd.date_range("2025-01-01", periods=30, freq="B")
        factor_data = []
        for d in dates:
            for i in range(10):
                # Same scores every day → same quintiles
                factor_data.append((d, f"INST{i:02d}", float(i)))
        factor = pd.DataFrame(factor_data, columns=["date", "instrument_id", "factor"]).set_index(
            ["date", "instrument_id"]
        )
        turnover = compute_turnover(factor, n_quantiles=5)
        assert turnover < 0.05  # essentially zero
