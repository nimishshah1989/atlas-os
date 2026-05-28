"""Unit tests for atlas.drift.compute_drift.

Tests cover:
  1. realized_excess calculation (stock return minus bench return)
  2. elapsed_frac clamping to [0.001, 1.0]
  3. Z-score formula: (realized - predicted_today) / sigma_today
  4. Drift event threshold: |Z| > 2 fires, |Z| <= 2 does not

All financial math uses Decimal. No DB, no fixtures — pure math.
"""

from __future__ import annotations

import math
from decimal import Decimal

from atlas.drift.compute_drift import (
    TENURE_DAYS,
    clamp_elapsed_frac,
    compute_realized_excess,
    compute_z_score,
    is_drift_event,
)

# Default drift threshold passed into is_drift_event — mirrors atlas_thresholds default.
# Tests supply this explicitly so no DB is needed in unit tests.
_TEST_Z_THRESHOLD = Decimal("2")


# ---------------------------------------------------------------------------
# Test 1: realized_excess calculation
# ---------------------------------------------------------------------------


class TestRealizedExcess:
    def test_positive_alpha_stock_beats_bench(self) -> None:
        """Stock up 10%, bench up 5% → excess = +5%."""
        price_today = Decimal("110")
        price_at_entry = Decimal("100")
        bench_today = Decimal("105")
        bench_at_entry = Decimal("100")

        excess = compute_realized_excess(price_today, price_at_entry, bench_today, bench_at_entry)
        assert excess == Decimal("0.05")

    def test_negative_alpha_stock_lags_bench(self) -> None:
        """Stock up 5%, bench up 10% → excess = -5%."""
        excess = compute_realized_excess(
            Decimal("105"), Decimal("100"), Decimal("110"), Decimal("100")
        )
        assert excess == Decimal("-0.05")

    def test_zero_excess_when_equal_returns(self) -> None:
        """Stock and bench both up 8% → excess = 0."""
        excess = compute_realized_excess(
            Decimal("108"), Decimal("100"), Decimal("108"), Decimal("100")
        )
        assert excess == Decimal("0")

    def test_negative_returns_handled_correctly(self) -> None:
        """Stock down 5%, bench down 10% → excess = +5% (stock less bad)."""
        excess = compute_realized_excess(
            Decimal("95"), Decimal("100"), Decimal("90"), Decimal("100")
        )
        assert excess == Decimal("0.05")

    def test_result_is_decimal_not_float(self) -> None:
        """Return type must be Decimal, never float."""
        excess = compute_realized_excess(
            Decimal("110"), Decimal("100"), Decimal("105"), Decimal("100")
        )
        assert isinstance(excess, Decimal)


# ---------------------------------------------------------------------------
# Test 2: elapsed_frac clamping
# ---------------------------------------------------------------------------


class TestElapsedFrac:
    def test_normal_midpoint(self) -> None:
        """21 days elapsed out of 63 (3m tenure) → frac = 1/3."""
        frac = clamp_elapsed_frac(days_elapsed=21, tenure_days=63)
        assert abs(frac - (21 / 63)) < 1e-9

    def test_clamp_at_upper_bound_1(self) -> None:
        """Elapsed > tenure → clamped to 1.0."""
        frac = clamp_elapsed_frac(days_elapsed=300, tenure_days=63)
        assert frac == 1.0

    def test_clamp_at_lower_bound_zero_days(self) -> None:
        """0 days elapsed → clamped to 0.001 (never zero)."""
        frac = clamp_elapsed_frac(days_elapsed=0, tenure_days=63)
        assert frac == 0.001

    def test_clamp_at_lower_bound_negative(self) -> None:
        """Negative days (bad data) → clamped to 0.001."""
        frac = clamp_elapsed_frac(days_elapsed=-5, tenure_days=63)
        assert frac == 0.001

    def test_exactly_at_tenure(self) -> None:
        """Elapsed == tenure → frac = 1.0 (not clamped, at boundary)."""
        frac = clamp_elapsed_frac(days_elapsed=63, tenure_days=63)
        assert frac == 1.0


# ---------------------------------------------------------------------------
# Test 3: Z-score formula
# ---------------------------------------------------------------------------


class TestZScore:
    def test_z_score_formula_positive(self) -> None:
        """Z = (realized - predicted_today) / sigma_today.

        With elapsed_frac=0.25 (one quarter through 1m tenure):
          predicted_today = predicted_full * 0.25
          sigma_today     = sigma_full * sqrt(0.25) = sigma_full * 0.5
        """
        realized = Decimal("0.10")
        predicted_full = Decimal("0.04")
        sigma_full = Decimal("0.02")
        elapsed_frac = 0.25

        z = compute_z_score(realized, predicted_full, sigma_full, elapsed_frac)

        predicted_today = Decimal(str(float(predicted_full) * elapsed_frac))
        sigma_today = Decimal(str(float(sigma_full) * math.sqrt(elapsed_frac)))
        expected_z = (realized - predicted_today) / sigma_today

        assert abs(z - expected_z) < Decimal("0.0001")

    def test_z_score_sigma_scales_with_sqrt_elapsed(self) -> None:
        """σ scales with sqrt(elapsed_frac), not linearly.

        At elapsed_frac=1.0, sigma_today == sigma_full.
        At elapsed_frac=0.25, sigma_today == sigma_full * 0.5 (not 0.25).
        """
        sigma_full = Decimal("0.04")
        elapsed_frac_full = 1.0
        elapsed_frac_quarter = 0.25

        # realized == predicted for both cases so Z=0; we only test sigma ratio
        z_full = compute_z_score(Decimal("0.04"), Decimal("0.04"), sigma_full, elapsed_frac_full)
        # sigma at full should be sigma_full; Z=0 confirms formula works
        assert abs(z_full) < Decimal("0.001")

        # At quarter elapsed, sigma_today = 0.04 * sqrt(0.25) = 0.04 * 0.5 = 0.02
        # realized = 0.03 (slightly above predicted_today = 0.01)
        # Z = (0.03 - 0.01) / 0.02 = 1.0
        z_quarter = compute_z_score(
            Decimal("0.03"), Decimal("0.04"), sigma_full, elapsed_frac_quarter
        )
        expected = Decimal("1.0")
        assert abs(z_quarter - expected) < Decimal("0.001")

    def test_z_score_is_decimal(self) -> None:
        """Z-score return type must be Decimal."""
        z = compute_z_score(Decimal("0.05"), Decimal("0.03"), Decimal("0.01"), 0.5)
        assert isinstance(z, Decimal)

    def test_z_score_negative(self) -> None:
        """Stock underperforms prediction → negative Z."""
        z = compute_z_score(Decimal("-0.05"), Decimal("0.03"), Decimal("0.02"), 1.0)
        assert z < Decimal("0")


# ---------------------------------------------------------------------------
# Test 4: drift event threshold |Z| > 2
# ---------------------------------------------------------------------------


class TestDriftEvent:
    def test_large_positive_z_is_drift(self) -> None:
        """Z = +3.0 → drift event (|Z| > threshold)."""
        assert is_drift_event(Decimal("3.0"), _TEST_Z_THRESHOLD) is True

    def test_large_negative_z_is_drift(self) -> None:
        """Z = -2.5 → drift event (|Z| > threshold)."""
        assert is_drift_event(Decimal("-2.5"), _TEST_Z_THRESHOLD) is True

    def test_exactly_at_threshold_is_not_drift(self) -> None:
        """Z == threshold → NOT a drift event (strict >)."""
        assert is_drift_event(Decimal("2.0"), _TEST_Z_THRESHOLD) is False

    def test_small_z_not_drift(self) -> None:
        """Z = 1.5 → well within band, not drift."""
        assert is_drift_event(Decimal("1.5"), _TEST_Z_THRESHOLD) is False

    def test_zero_z_not_drift(self) -> None:
        """Z = 0 → no drift."""
        assert is_drift_event(Decimal("0"), _TEST_Z_THRESHOLD) is False

    def test_negative_threshold_boundary(self) -> None:
        """Z = -threshold → NOT a drift event (strict >)."""
        assert is_drift_event(Decimal("-2.0"), _TEST_Z_THRESHOLD) is False

    def test_custom_threshold_honored(self) -> None:
        """Threshold is parameterized — caller supplies from atlas_thresholds."""
        high_threshold = Decimal("3")
        assert is_drift_event(Decimal("2.5"), high_threshold) is False
        assert is_drift_event(Decimal("3.1"), high_threshold) is True


# ---------------------------------------------------------------------------
# Test 5: TENURE_DAYS constants
# ---------------------------------------------------------------------------


class TestTenureConstants:
    def test_tenure_days_map_is_complete(self) -> None:
        """All four tenure codes must be present."""
        assert set(TENURE_DAYS.keys()) == {"1m", "3m", "6m", "12m"}

    def test_tenure_days_values(self) -> None:
        """Standard trading-day counts per tenure."""
        assert TENURE_DAYS["1m"] == 21
        assert TENURE_DAYS["3m"] == 63
        assert TENURE_DAYS["6m"] == 126
        assert TENURE_DAYS["12m"] == 252
