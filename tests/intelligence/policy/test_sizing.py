"""Tests for atlas.intelligence.policy.sizing — position-size formula.

All tests are pure (no DB). Hand-computed golden values per
chunk-decision-engine-T3.2-sizing-approach.md.

Formula under test (C6):
    regime_room = regime_cap - current_invested
    raw         = min(target_gap, max_per_stock, regime_room)
    suggested   = max(raw, Decimal("0"))
    binding     = whichever term was the binding (minimum) constraint

The six required test cases come directly from the chunk spec, each with
manually-derived expected values that do NOT reference the implementation.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas.intelligence.policy.sizing import PositionSizeResult, suggest_position_size

# ---------------------------------------------------------------------------
# Helper: assert result is a frozen PositionSizeResult with exact fields
# ---------------------------------------------------------------------------


def _assert_result(
    result: PositionSizeResult,
    expected_pct: Decimal,
    expected_constraint: str,
) -> None:
    assert isinstance(
        result, PositionSizeResult
    ), f"Expected PositionSizeResult, got {type(result)}"
    assert isinstance(
        result.suggested_pct, Decimal
    ), f"suggested_pct must be Decimal, got {type(result.suggested_pct)}"
    assert isinstance(
        result.binding_constraint, str
    ), f"binding_constraint must be str, got {type(result.binding_constraint)}"
    assert (
        result.suggested_pct == expected_pct
    ), f"suggested_pct: expected {expected_pct}, got {result.suggested_pct}"
    assert (
        result.binding_constraint == expected_constraint
    ), f"binding_constraint: expected '{expected_constraint}', got '{result.binding_constraint}'"


# ---------------------------------------------------------------------------
# Case 1: Gap-bound
#
# target_gap=2.5, max_per_stock=5, regime_cap=40, current_invested=30
# regime_room = 40 - 30 = 10
# min(2.5, 5, 10) = 2.5   → binding = 'target_gap'
# ---------------------------------------------------------------------------


class TestGapBound:
    """target_gap is the smallest term — it binds the suggestion."""

    def test_suggested_pct(self) -> None:
        result = suggest_position_size(
            target_gap=Decimal("2.5"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("30"),
        )
        assert result.suggested_pct == Decimal("2.5")

    def test_binding_constraint(self) -> None:
        result = suggest_position_size(
            target_gap=Decimal("2.5"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("30"),
        )
        assert result.binding_constraint == "target_gap"

    def test_full_result(self) -> None:
        result = suggest_position_size(
            target_gap=Decimal("2.5"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("30"),
        )
        _assert_result(result, Decimal("2.5"), "target_gap")


# ---------------------------------------------------------------------------
# Case 2: Stock-cap-bound
#
# target_gap=8, max_per_stock=5, regime_cap=40, current_invested=20
# regime_room = 40 - 20 = 20
# min(8, 5, 20) = 5   → binding = 'max_per_stock'
# ---------------------------------------------------------------------------


class TestStockCapBound:
    """max_per_stock is the smallest term — concentration cap binds."""

    def test_suggested_pct(self) -> None:
        result = suggest_position_size(
            target_gap=Decimal("8"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("20"),
        )
        assert result.suggested_pct == Decimal("5")

    def test_binding_constraint(self) -> None:
        result = suggest_position_size(
            target_gap=Decimal("8"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("20"),
        )
        assert result.binding_constraint == "max_per_stock"

    def test_full_result(self) -> None:
        result = suggest_position_size(
            target_gap=Decimal("8"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("20"),
        )
        _assert_result(result, Decimal("5"), "max_per_stock")


# ---------------------------------------------------------------------------
# Case 3: Regime-cap-bound
#
# target_gap=8, max_per_stock=5, regime_cap=40, current_invested=37
# regime_room = 40 - 37 = 3
# min(8, 5, 3) = 3   → binding = 'regime_cap'
# ---------------------------------------------------------------------------


class TestRegimeCapBound:
    """regime_room is the smallest term — deployment cap binds."""

    def test_suggested_pct(self) -> None:
        result = suggest_position_size(
            target_gap=Decimal("8"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("37"),
        )
        assert result.suggested_pct == Decimal("3")

    def test_binding_constraint(self) -> None:
        result = suggest_position_size(
            target_gap=Decimal("8"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("37"),
        )
        assert result.binding_constraint == "regime_cap"

    def test_full_result(self) -> None:
        result = suggest_position_size(
            target_gap=Decimal("8"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("37"),
        )
        _assert_result(result, Decimal("3"), "regime_cap")


# ---------------------------------------------------------------------------
# Case 4: Clamped to zero — book exactly at regime cap
#
# target_gap=8, max_per_stock=5, regime_cap=40, current_invested=40
# regime_room = 40 - 40 = 0
# min(8, 5, 0) = 0   → raw = 0 → suggested = 0, binding = 'regime_cap'
# ---------------------------------------------------------------------------


class TestClampedAtRegimeCap:
    """Book is exactly at regime cap — regime_room=0 → suggested=0."""

    def test_suggested_pct_is_zero(self) -> None:
        result = suggest_position_size(
            target_gap=Decimal("8"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("40"),
        )
        assert result.suggested_pct == Decimal("0")

    def test_binding_constraint_is_regime_cap(self) -> None:
        result = suggest_position_size(
            target_gap=Decimal("8"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("40"),
        )
        assert result.binding_constraint == "regime_cap"

    def test_full_result(self) -> None:
        result = suggest_position_size(
            target_gap=Decimal("8"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("40"),
        )
        _assert_result(result, Decimal("0"), "regime_cap")


# ---------------------------------------------------------------------------
# Case 5: Clamped to zero — book over regime cap
#
# target_gap=8, max_per_stock=5, regime_cap=40, current_invested=45
# regime_room = 40 - 45 = -5
# min(8, 5, -5) = -5   → raw < 0 → suggested = 0, binding = 'regime_cap'
# ---------------------------------------------------------------------------


class TestClampedOverRegimeCap:
    """Book is over regime cap — regime_room negative → suggested=0."""

    def test_suggested_pct_is_zero(self) -> None:
        result = suggest_position_size(
            target_gap=Decimal("8"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("45"),
        )
        assert result.suggested_pct == Decimal("0")

    def test_binding_constraint_is_regime_cap(self) -> None:
        result = suggest_position_size(
            target_gap=Decimal("8"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("45"),
        )
        assert result.binding_constraint == "regime_cap"

    def test_full_result(self) -> None:
        result = suggest_position_size(
            target_gap=Decimal("8"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("45"),
        )
        _assert_result(result, Decimal("0"), "regime_cap")


# ---------------------------------------------------------------------------
# Case 6: Negative gap — sector already at/above target
#
# target_gap=-1.0, max_per_stock=5, regime_cap=40, current_invested=30
# regime_room = 40 - 30 = 10
# min(-1, 5, 10) = -1   → raw < 0 → suggested = 0, binding = 'target_gap'
# ---------------------------------------------------------------------------


class TestNegativeGap:
    """target_gap is negative (sector over-allocated) → suggested=0, binding='target_gap'."""

    def test_suggested_pct_is_zero(self) -> None:
        result = suggest_position_size(
            target_gap=Decimal("-1.0"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("30"),
        )
        assert result.suggested_pct == Decimal("0")

    def test_binding_constraint_is_target_gap(self) -> None:
        result = suggest_position_size(
            target_gap=Decimal("-1.0"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("30"),
        )
        assert result.binding_constraint == "target_gap"

    def test_full_result(self) -> None:
        result = suggest_position_size(
            target_gap=Decimal("-1.0"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("30"),
        )
        _assert_result(result, Decimal("0"), "target_gap")

    def test_zero_gap_also_produces_zero(self) -> None:
        """target_gap=0 (exactly at target) → suggested=0, binding='target_gap'."""
        result = suggest_position_size(
            target_gap=Decimal("0"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("30"),
        )
        _assert_result(result, Decimal("0"), "target_gap")


# ---------------------------------------------------------------------------
# Type safety: output fields must always be Decimal (never float)
# ---------------------------------------------------------------------------


class TestOutputTypes:
    """suggested_pct must always be Decimal, binding_constraint always str."""

    @pytest.mark.parametrize(
        "target_gap,max_per_stock,regime_cap,current_invested",
        [
            (Decimal("3"), Decimal("5"), Decimal("40"), Decimal("25")),
            (Decimal("-2"), Decimal("5"), Decimal("40"), Decimal("25")),
            (Decimal("0"), Decimal("5"), Decimal("40"), Decimal("25")),
            (Decimal("10"), Decimal("5"), Decimal("40"), Decimal("40")),
            (Decimal("10"), Decimal("5"), Decimal("40"), Decimal("50")),
        ],
    )
    def test_suggested_pct_is_decimal(
        self,
        target_gap: Decimal,
        max_per_stock: Decimal,
        regime_cap: Decimal,
        current_invested: Decimal,
    ) -> None:
        result = suggest_position_size(
            target_gap=target_gap,
            max_per_stock=max_per_stock,
            regime_cap=regime_cap,
            current_invested=current_invested,
        )
        assert isinstance(
            result.suggested_pct, Decimal
        ), f"suggested_pct is {type(result.suggested_pct)}, expected Decimal"

    @pytest.mark.parametrize(
        "target_gap,max_per_stock,regime_cap,current_invested",
        [
            (Decimal("3"), Decimal("5"), Decimal("40"), Decimal("25")),
            (Decimal("-2"), Decimal("5"), Decimal("40"), Decimal("25")),
            (Decimal("10"), Decimal("5"), Decimal("40"), Decimal("45")),
        ],
    )
    def test_suggested_pct_non_negative(
        self,
        target_gap: Decimal,
        max_per_stock: Decimal,
        regime_cap: Decimal,
        current_invested: Decimal,
    ) -> None:
        """suggested_pct must always be >= 0 regardless of inputs."""
        result = suggest_position_size(
            target_gap=target_gap,
            max_per_stock=max_per_stock,
            regime_cap=regime_cap,
            current_invested=current_invested,
        )
        assert result.suggested_pct >= Decimal(
            "0"
        ), f"suggested_pct {result.suggested_pct} is negative — must be clamped to 0"


# ---------------------------------------------------------------------------
# binding_constraint is always one of the four valid values
# ---------------------------------------------------------------------------


class TestBindingConstraintValues:
    """binding_constraint must always be one of the four documented literals."""

    _VALID_CONSTRAINTS = frozenset({"target_gap", "max_per_stock", "regime_cap", "none"})

    @pytest.mark.parametrize(
        "target_gap,max_per_stock,regime_cap,current_invested",
        [
            (Decimal("2.5"), Decimal("5"), Decimal("40"), Decimal("30")),  # gap-bound
            (Decimal("8"), Decimal("5"), Decimal("40"), Decimal("20")),  # stock-bound
            (Decimal("8"), Decimal("5"), Decimal("40"), Decimal("37")),  # regime-bound
            (Decimal("8"), Decimal("5"), Decimal("40"), Decimal("40")),  # at-cap
            (Decimal("8"), Decimal("5"), Decimal("40"), Decimal("45")),  # over-cap
            (Decimal("-1"), Decimal("5"), Decimal("40"), Decimal("30")),  # negative gap
        ],
    )
    def test_binding_constraint_is_valid_literal(
        self,
        target_gap: Decimal,
        max_per_stock: Decimal,
        regime_cap: Decimal,
        current_invested: Decimal,
    ) -> None:
        result = suggest_position_size(
            target_gap=target_gap,
            max_per_stock=max_per_stock,
            regime_cap=regime_cap,
            current_invested=current_invested,
        )
        assert (
            result.binding_constraint in self._VALID_CONSTRAINTS
        ), f"binding_constraint '{result.binding_constraint}' is not a valid literal"


# ---------------------------------------------------------------------------
# Frozen dataclass: immutability
# ---------------------------------------------------------------------------


class TestImmutability:
    """PositionSizeResult must be frozen — attribute assignment must raise."""

    def test_result_is_frozen(self) -> None:
        result = suggest_position_size(
            target_gap=Decimal("3"),
            max_per_stock=Decimal("5"),
            regime_cap=Decimal("40"),
            current_invested=Decimal("20"),
        )
        with pytest.raises((AttributeError, TypeError)):
            result.suggested_pct = Decimal("99")  # type: ignore[misc]
