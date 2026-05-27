"""TDD tests for ETF scorecard 3 new column computations.

Tests are pure unit tests — no DB required.

Functions under test (in atlas.inference.etf_scorecard):
    compute_premium_bps(market_close, nav) -> float | None
        premium = (market_close - nav) / nav * 10000, clamped to [-500, +500] bps.
        Returns None when market_close or nav is None/zero.

    compute_te_60d(etf_returns_60d, underlying_returns_60d) -> float | None
        Annualized tracking error: std(etf - underlying) * sqrt(252).
        Both lists must have matching length >= 2. Returns None on insufficient data.

    compute_adv_20d_inr(volume_20d, close_20d) -> float
        Average daily traded value = sum(v * c for v, c in zip(volume_20d, close_20d)) / len.
        Minimum 1 observation required.
"""

from __future__ import annotations

import math

import pytest

# These imports will FAIL until we add the functions to etf_scorecard.py — TDD red phase.
from atlas.inference.etf_scorecard import (
    compute_adv_20d_inr,
    compute_premium_bps,
    compute_te_60d,
)

# ---------------------------------------------------------------------------
# compute_premium_bps
# ---------------------------------------------------------------------------


class TestComputePremiumBps:
    def test_zero_premium_at_par(self) -> None:
        """When market price == NAV, premium is exactly 0 bps."""
        result = compute_premium_bps(100.0, 100.0)
        assert result == pytest.approx(0.0)

    def test_positive_premium(self) -> None:
        """Market price above NAV: ETF trades at premium."""
        # (102 - 100) / 100 * 10000 = 200 bps
        result = compute_premium_bps(102.0, 100.0)
        assert result == pytest.approx(200.0)

    def test_negative_premium_discount(self) -> None:
        """Market price below NAV: ETF trades at discount → negative bps."""
        # (98 - 100) / 100 * 10000 = -200 bps
        result = compute_premium_bps(98.0, 100.0)
        assert result == pytest.approx(-200.0)

    def test_clamp_positive_to_500_bps(self) -> None:
        """Large premium is clamped to +500 bps."""
        # (115 - 100) / 100 * 10000 = 1500 bps → clamped to 500
        result = compute_premium_bps(115.0, 100.0)
        assert result == pytest.approx(500.0)

    def test_clamp_negative_to_minus_500_bps(self) -> None:
        """Large discount clamped to -500 bps."""
        # (85 - 100) / 100 * 10000 = -1500 bps → clamped to -500
        result = compute_premium_bps(85.0, 100.0)
        assert result == pytest.approx(-500.0)

    def test_none_on_none_market_close(self) -> None:
        result = compute_premium_bps(None, 100.0)
        assert result is None

    def test_none_on_none_nav(self) -> None:
        result = compute_premium_bps(100.0, None)
        assert result is None

    def test_none_on_zero_nav(self) -> None:
        """Division by zero NAV → None (not an exception)."""
        result = compute_premium_bps(100.0, 0.0)
        assert result is None

    def test_typical_etf_small_premium(self) -> None:
        """Typical liquid ETF: NIFTYBEES at 271.00 close vs 270.85 NAV → ~5.5 bps."""
        result = compute_premium_bps(271.00, 270.85)
        assert result is not None
        assert result == pytest.approx((271.00 - 270.85) / 270.85 * 10000, rel=1e-4)

    def test_boundary_exactly_500_bps(self) -> None:
        """Exactly 500 bps is not clamped (boundary inclusive)."""
        # 5% premium = 500 bps
        result = compute_premium_bps(105.0, 100.0)
        assert result == pytest.approx(500.0)


# ---------------------------------------------------------------------------
# compute_te_60d
# ---------------------------------------------------------------------------


class TestComputeTe60d:
    def test_zero_te_when_returns_identical(self) -> None:
        """If ETF perfectly tracks benchmark every day, TE = 0."""
        returns = [0.001, 0.002, -0.001, 0.003] * 20  # 80 obs
        result = compute_te_60d(returns, returns)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-10)

    def test_annualized_from_daily_diff(self) -> None:
        """TE = std(diff_series) * sqrt(252)."""
        import statistics

        etf = [0.01, -0.02, 0.015, 0.005, -0.01] * 15  # 75 obs
        bench = [0.008, -0.018, 0.013, 0.004, -0.009] * 15
        diffs = [e - b for e, b in zip(etf, bench, strict=False)]
        expected = statistics.stdev(diffs) * math.sqrt(252)
        result = compute_te_60d(etf, bench)
        assert result is not None
        assert result == pytest.approx(expected, rel=1e-6)

    def test_none_on_empty_lists(self) -> None:
        result = compute_te_60d([], [])
        assert result is None

    def test_none_on_single_observation(self) -> None:
        """std of 1 element is undefined → None."""
        result = compute_te_60d([0.01], [0.01])
        assert result is None

    def test_none_on_mismatched_lengths_short(self) -> None:
        """If lists are mismatched, use the zip (shorter) — still ok if >= 2."""
        etf = [0.01, 0.02, 0.03]
        bench = [0.01, 0.02]  # shorter
        # zip gives 2 pairs → std is defined with 2 obs (sample std)
        result = compute_te_60d(etf, bench)
        # With 2 identical diffs (0.01-0.01, 0.02-0.02=0), std=0 → TE=0
        assert result is not None

    def test_result_is_positive(self) -> None:
        """TE is always non-negative (std is non-negative)."""
        import random

        random.seed(42)
        etf = [random.gauss(0.001, 0.01) for _ in range(60)]
        bench = [random.gauss(0.001, 0.009) for _ in range(60)]
        result = compute_te_60d(etf, bench)
        assert result is not None
        assert result >= 0.0

    def test_typical_niftybees_like_te(self) -> None:
        """NIFTYBEES vs NIFTY500 should have low TE < 0.005 (0.5%)."""
        import random

        random.seed(7)
        bench = [random.gauss(0.0005, 0.008) for _ in range(60)]
        # ETF has tiny tracking error: add noise of std ~0.0001
        etf = [b + random.gauss(0, 0.0001) for b in bench]
        result = compute_te_60d(etf, bench)
        assert result is not None
        # Annualized TE should be very small: ~0.0001 * sqrt(252) ≈ 0.0016
        assert result < 0.005

    def test_high_te_for_poorly_tracking_etf(self) -> None:
        """ETF with 1% daily tracking error → annualized TE ~15.9%."""
        import random

        random.seed(99)
        bench = [random.gauss(0.0, 0.01) for _ in range(60)]
        # Add 1% noise std per day
        etf = [b + random.gauss(0, 0.01) for b in bench]
        result = compute_te_60d(etf, bench)
        assert result is not None
        # 0.01 * sqrt(252) ≈ 0.1587; with both having same std ~0.01 * sqrt(2)
        assert result > 0.05  # well above 5% annualized


# ---------------------------------------------------------------------------
# compute_adv_20d_inr
# ---------------------------------------------------------------------------


class TestComputeAdv20dInr:
    def test_basic_average(self) -> None:
        """ADV = sum(close_i * volume_i) / n."""
        closes = [100.0, 200.0, 300.0, 400.0]
        volumes = [1000.0, 2000.0, 3000.0, 4000.0]
        # Daily values: 100k, 400k, 900k, 1600k → sum=3000k, avg=750k
        expected = (100_000 + 400_000 + 900_000 + 1_600_000) / 4
        result = compute_adv_20d_inr(volumes, closes)
        assert result == pytest.approx(expected)

    def test_single_observation(self) -> None:
        """One day: ADV = close * volume."""
        result = compute_adv_20d_inr([5000.0], [270.0])
        assert result == pytest.approx(5000.0 * 270.0)

    def test_zero_volume_days_included(self) -> None:
        """Zero-volume days count toward the average (not skipped)."""
        # 2 days: 1000*100 = 100k, 0*100 = 0 → avg = 50k
        result = compute_adv_20d_inr([1000.0, 0.0], [100.0, 100.0])
        assert result == pytest.approx(50_000.0)

    def test_empty_lists_return_zero(self) -> None:
        """Empty input returns 0.0."""
        result = compute_adv_20d_inr([], [])
        assert result == pytest.approx(0.0)

    def test_niftybees_realistic(self) -> None:
        """NIFTYBEES-scale: ~270 close, ~6M volume → ~162 cr per day."""
        closes = [270.83] * 20
        volumes = [6_000_000.0] * 20
        result = compute_adv_20d_inr(volumes, closes)
        # 270.83 * 6M = 1,624,980,000 ≈ 1.625B (₹16.25 cr is wrong; it's INR 162.5 cr)
        assert result == pytest.approx(270.83 * 6_000_000)

    def test_uses_zip_when_mismatched_lengths(self) -> None:
        """Uses zip — shorter list determines denominator."""
        closes = [100.0, 200.0, 300.0]
        volumes = [1000.0, 2000.0]  # shorter
        # 2 pairs: 100k + 400k = 500k / 2 = 250k
        result = compute_adv_20d_inr(volumes, closes)
        assert result == pytest.approx(250_000.0)
