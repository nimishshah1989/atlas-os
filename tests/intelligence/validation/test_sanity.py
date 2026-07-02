"""Three sanity checks from SP01 validation strategy.

(1) IC on a known-strong synthetic signal (12-month return) > 0.06
(2) IC on randomized signal labels ≈ 0
(3) Quantile spread on a strong synthetic signal > 0
"""

import numpy as np
import pandas as pd
import pytest
from atlas.intelligence.validation.ic_engine import (
    compute_ic_over_window,
    compute_quantile_spread,
)


@pytest.fixture
def synthetic_universe():
    """Build a synthetic 100-stock, 1-year universe where forward returns
    have a small but reliable correlation to a 12-month momentum factor.
    """
    np.random.seed(123)
    dates = pd.date_range("2025-01-01", periods=200, freq="B")
    instruments = [f"INST{i:03d}" for i in range(100)]

    # Generate true forward returns
    fwd_data: list[tuple] = []
    factor_data: list[tuple] = []
    # Stable per-instrument trend → produces stable RS ranking AND forward return correlation
    instrument_trends = {inst: np.random.randn() for inst in instruments}

    for d in dates:
        for inst in instruments:
            base = instrument_trends[inst]
            # Factor (12m momentum proxy) — same per instrument, with small noise
            factor_val = base + np.random.randn() * 0.1
            # Forward return correlated with the factor (signal=0.3, noise=0.7)
            ret = 0.3 * base + 0.7 * np.random.randn()
            factor_data.append((d, inst, factor_val))
            fwd_data.append((d, inst, ret))

    factor_df = pd.DataFrame(factor_data, columns=["date", "instrument_id", "factor"])
    factor_df = factor_df.set_index(["date", "instrument_id"])
    fwd_df = pd.DataFrame(fwd_data, columns=["date", "instrument_id", "ret"])
    fwd_wide = fwd_df.pivot(index="date", columns="instrument_id", values="ret")
    return factor_df, fwd_wide


@pytest.fixture
def randomized_factor(synthetic_universe):
    """Take the synthetic universe but shuffle the factor values within each date.
    This destroys the signal-to-return relationship — IC should be near zero.
    """
    factor_df, fwd_wide = synthetic_universe
    rng = np.random.default_rng(456)
    shuffled = factor_df.copy()
    shuffled = shuffled.groupby(level="date", group_keys=False).apply(
        lambda g: g.assign(factor=rng.permutation(g["factor"].values))
    )
    return shuffled, fwd_wide


class TestSP01ValidationStrategy:
    def test_known_strong_signal_ic_above_threshold(self, synthetic_universe):
        """Validation strategy step 1: known-strong synthetic signal IC > 0.06."""
        factor, returns = synthetic_universe
        result = compute_ic_over_window(factor, returns)
        assert result.mean_ic > 0.06, (
            f"Synthetic momentum signal should have IC > 0.06, got {result.mean_ic:.4f}. "
            "If this fails, the IC engine itself is broken (not the signal)."
        )

    def test_randomized_signal_ic_near_zero(self, randomized_factor):
        """Validation strategy step 2: randomized signal labels → IC ≈ 0."""
        factor, returns = randomized_factor
        result = compute_ic_over_window(factor, returns)
        assert abs(result.mean_ic) < 0.03, (
            f"Randomized signal should have |IC| < 0.03, got {result.mean_ic:.4f}. "
            "If this fails, there's a look-ahead bug or alignment error in the engine."
        )

    def test_quantile_spread_positive_on_strong_signal(self, synthetic_universe):
        """Validation strategy step 3: Q_top − Q_bot > 0 on a strong signal."""
        factor, returns = synthetic_universe
        spread = compute_quantile_spread(factor, returns, n_quantiles=5)
        assert spread > 0, (
            f"Synthetic momentum signal should have positive Q5−Q1 spread, got {spread:.4f}"
        )
