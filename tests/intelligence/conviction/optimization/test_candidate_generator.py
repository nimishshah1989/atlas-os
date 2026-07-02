"""Tests for the candidate weight-set generator (unit + integration)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from atlas.intelligence.conviction.optimization.candidate_generator import (
    MATERIAL_CHANGE_THRESHOLD,
    _build_rationale,
    _max_abs_delta,
    _renormalize,
    generate_candidates,
)


class TestRenormalize:
    def test_zero_sum_is_pass_through(self) -> None:
        weights = {"a": Decimal("0"), "b": Decimal("0")}
        assert _renormalize(weights) == weights

    def test_sums_to_one(self) -> None:
        weights = {"a": Decimal("3"), "b": Decimal("1"), "c": Decimal("1")}
        result = _renormalize(weights)
        total = sum(result.values())
        assert total == pytest.approx(Decimal("1"), abs=Decimal("1e-9"))
        assert result["a"] == pytest.approx(Decimal("0.6"), abs=Decimal("1e-9"))


class TestMaxAbsDelta:
    def test_empty_returns_zero(self) -> None:
        assert _max_abs_delta({}, {}) == Decimal("0")

    def test_difference_uses_zero_default(self) -> None:
        a = {"x": Decimal("0.5")}
        b = {"y": Decimal("0.4")}
        # missing key treated as 0.0 → max delta = 0.5
        assert _max_abs_delta(a, b) == Decimal("0.5")

    def test_picks_largest_delta(self) -> None:
        a = {"x": Decimal("0.3"), "y": Decimal("0.7")}
        b = {"x": Decimal("0.5"), "y": Decimal("0.5")}
        assert _max_abs_delta(a, b) == Decimal("0.2")


class TestBuildRationale:
    def test_includes_top_3_movers(self) -> None:
        current = {
            "ret_6m": Decimal("0.5"),
            "atr_21": Decimal("0.3"),
            "rs_pctile_3m": Decimal("0.2"),
        }
        proposed = {
            "ret_6m": Decimal("0.1"),
            "atr_21": Decimal("0.7"),
            "rs_pctile_3m": Decimal("0.2"),
        }
        rationale = _build_rationale("tier_1_megacap", current=current, proposed=proposed)
        assert "atr_21" in rationale
        assert "ret_6m" in rationale
        assert rationale.startswith("Stage 4a re-weight")


def test_material_change_threshold_constant() -> None:
    """A change has to move at least 5% on the biggest element to count."""
    assert MATERIAL_CHANGE_THRESHOLD == Decimal("0.05")


@pytest.mark.integration
def test_generate_candidates_returns_list() -> None:
    """End-to-end: should not crash even when atlas_signal_ic_rolling has no data."""
    from atlas.db import get_engine

    eng = get_engine()
    candidates = generate_candidates(eng, as_of=date(2026, 5, 12))
    assert isinstance(candidates, list)
    # With no IC measurements present yet, result is empty — that is fine.
