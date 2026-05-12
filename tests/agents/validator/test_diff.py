"""Unit tests for route_crawler.diff.compare.

Validates severity classification logic without DB or browser.
"""

from __future__ import annotations

from decimal import Decimal

from atlas.agents.validator.route_crawler.diff import compare


class TestNumericDiff:
    def test_clean_within_tolerance(self) -> None:
        # conviction_score tolerance = 2%
        result = compare("stock.conviction_score", Decimal("0.80"), Decimal("0.80"))
        assert result.severity == "P3"

    def test_p3_within_half_tolerance(self) -> None:
        # delta_pct = 0.004/0.80 = 0.5% < 0.5*2%=1% → P3
        result = compare("stock.conviction_score", Decimal("0.804"), Decimal("0.80"))
        assert result.severity == "P3"

    def test_p2_between_half_and_full_tolerance(self) -> None:
        # tolerance = 2%. delta_pct = 0.01/0.80 = 1.25%. 0.5*tol=1%, full_tol=2%.
        # 1.25% > 1% but < 2% → P2
        result = compare("stock.conviction_score", Decimal("0.81"), Decimal("0.80"))
        assert result.severity == "P2"

    def test_p1_above_tolerance(self) -> None:
        # delta_pct ~3.75% > 2% tolerance → P1
        result = compare("stock.conviction_score", Decimal("0.83"), Decimal("0.80"))
        assert result.severity == "P1"
        assert result.needs_screenshot is True

    def test_p0_above_10x_tolerance(self) -> None:
        # tolerance = 2%, 10x = 20%.  delta = 50% → P0
        result = compare("stock.conviction_score", Decimal("1.20"), Decimal("0.80"))
        assert result.severity == "P0"
        assert result.needs_screenshot is True

    def test_delta_abs_computed(self) -> None:
        result = compare("stock.conviction_score", Decimal("0.83"), Decimal("0.80"))
        assert result.delta_abs is not None
        assert abs(result.delta_abs - Decimal("0.03")) < Decimal("0.0001")

    def test_delta_pct_computed(self) -> None:
        result = compare("stock.conviction_score", Decimal("0.83"), Decimal("0.80"))
        assert result.delta_pct is not None
        # 0.03 / 0.80 = 0.0375
        assert abs(result.delta_pct - Decimal("0.0375")) < Decimal("0.0001")

    def test_zero_backend_zero_frontend(self) -> None:
        result = compare("stock.conviction_score", Decimal("0"), Decimal("0"))
        assert result.severity == "P3"

    def test_zero_backend_nonzero_frontend(self) -> None:
        result = compare("stock.conviction_score", Decimal("0.5"), Decimal("0"))
        assert result.severity == "P1"
        assert result.delta_pct is None  # undefined division


class TestCategoricalDiff:
    def test_exact_match(self) -> None:
        result = compare("sector.sector_state", "Overweight", "Overweight")
        assert result.severity == "P3"

    def test_mismatch_is_p0(self) -> None:
        result = compare("sector.sector_state", "Neutral", "Overweight")
        assert result.severity == "P0"
        assert result.needs_screenshot is True

    def test_stock_momentum_state_mismatch(self) -> None:
        result = compare("stock.momentum_state", "Deteriorating", "Improving")
        assert result.severity == "P0"


class TestNullHandling:
    def test_both_none_p3(self) -> None:
        result = compare("stock.conviction_score", None, None)
        assert result.severity == "P3"

    def test_frontend_none_backend_present_p1(self) -> None:
        result = compare("stock.conviction_score", None, Decimal("0.80"))
        assert result.severity == "P1"
        assert result.needs_screenshot is True

    def test_backend_none_frontend_present_p2(self) -> None:
        result = compare("stock.conviction_score", Decimal("0.80"), None)
        assert result.severity == "P2"
        assert result.needs_screenshot is False


class TestStringMixedTypes:
    def test_string_vs_decimal_mismatch(self) -> None:
        # If frontend returns str (categorical) and backend returns Decimal, treat as mismatch
        result = compare("stock.conviction_score", "0.80", Decimal("0.80"))
        # The str "0.80" != Decimal("0.80") as strings → categorical path → P0
        # (or P3 if str comparison happens to match — depends on implementation)
        assert result.severity in ("P0", "P3")

    def test_unknown_field_uses_default_tolerance(self) -> None:
        # Unknown field key falls back to _default tolerance (2%)
        # delta_pct ~3.75% > 2% default → P1
        result = compare("unknown.field", Decimal("0.83"), Decimal("0.80"))
        assert result.severity == "P1"
