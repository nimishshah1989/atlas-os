"""Tests for ``atlas.decisions.rule_dsl`` — Pydantic v2 CellRule schema."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from atlas.decisions.rule_dsl import CellRule, FeaturePredicate, validate_rule_dsl
from atlas.features import FEATURES

# ---------------------------------------------------------------------------
# FeaturePredicate — allowlist + cmp + value shape
# ---------------------------------------------------------------------------


def test_feature_predicate_rejects_unknown_feature() -> None:
    """A feature name absent from FEATURES must raise ValidationError."""
    with pytest.raises(ValidationError) as excinfo:
        FeaturePredicate(
            feature="totally_not_a_real_feature",
            cmp=">",
            value=Decimal("0.5"),
        )
    assert "not in atlas.features.FEATURES allowlist" in str(excinfo.value)


def test_feature_predicate_accepts_every_locked_feature() -> None:
    """Every name in FEATURES must validate cleanly."""
    for feature in FEATURES:
        p = FeaturePredicate(feature=feature, cmp=">=", value=Decimal("0"))
        assert p.feature == feature


@pytest.mark.parametrize("cmp", [">", ">=", "<", "<=", "=="])
def test_feature_predicate_scalar_cmp_with_decimal(cmp: str) -> None:
    """All 5 scalar cmps accept a Decimal value."""
    p = FeaturePredicate(
        feature="rs_residual_6m",
        cmp=cmp,  # type: ignore[arg-type]
        value=Decimal("0.05"),
    )
    assert p.cmp == cmp
    assert p.value == Decimal("0.05")


def test_feature_predicate_scalar_cmp_rejects_tuple_value() -> None:
    """A 2-tuple value with a scalar cmp must fail validation."""
    with pytest.raises(ValidationError):
        FeaturePredicate(
            feature="rs_residual_6m",
            cmp=">",
            value=(Decimal("0"), Decimal("1")),
        )


def test_feature_predicate_in_range_requires_tuple() -> None:
    """``in_range`` requires a 2-tuple, not a scalar."""
    with pytest.raises(ValidationError):
        FeaturePredicate(
            feature="rs_residual_6m",
            cmp="in_range",
            value=Decimal("0.05"),
        )


def test_feature_predicate_in_range_accepts_valid_tuple() -> None:
    """``in_range`` with ``low <= high`` validates."""
    p = FeaturePredicate(
        feature="realized_vol_60d",
        cmp="in_range",
        value=(Decimal("0.10"), Decimal("0.40")),
    )
    assert p.value == (Decimal("0.10"), Decimal("0.40"))


def test_feature_predicate_in_range_rejects_inverted_tuple() -> None:
    """``in_range`` with ``low > high`` raises ValidationError."""
    with pytest.raises(ValidationError) as excinfo:
        FeaturePredicate(
            feature="realized_vol_60d",
            cmp="in_range",
            value=(Decimal("0.50"), Decimal("0.10")),
        )
    assert "low must be <= high" in str(excinfo.value)


def test_feature_predicate_in_top_quantile_requires_quantile_n() -> None:
    """``in_top_quantile`` without value_quantile_n is rejected."""
    with pytest.raises(ValidationError) as excinfo:
        FeaturePredicate(
            feature="rs_residual_6m",
            cmp="in_top_quantile",
            value=Decimal("1"),
        )
    assert "value_quantile_n" in str(excinfo.value)


def test_feature_predicate_in_top_quantile_rejects_quantile_below_2() -> None:
    """value_quantile_n must be >= 2 (top-1-of-1 makes no sense)."""
    with pytest.raises(ValidationError):
        FeaturePredicate(
            feature="rs_residual_6m",
            cmp="in_top_quantile",
            value=Decimal("1"),
            value_quantile_n=1,
        )


def test_feature_predicate_in_top_quantile_with_quintile() -> None:
    """Quintile (n=5) is the canonical top-1/5 form."""
    p = FeaturePredicate(
        feature="rs_residual_6m",
        cmp="in_top_quantile",
        value=Decimal("1"),
        value_quantile_n=5,
    )
    assert p.value_quantile_n == 5


# ---------------------------------------------------------------------------
# CellRule — rule_type enum, action enum, tier, tenure
# ---------------------------------------------------------------------------


def _minimal_cell_rule_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "rule_type": "pullback",
        "tier": "Mid",
        "action": "POSITIVE",
        "tenure": "6m",
        "methodology_lock_ref": "TEST_LOCK_2026-05-24",
    }
    base.update(overrides)
    return base


def test_cell_rule_minimal_validates() -> None:
    rule = CellRule(**_minimal_cell_rule_kwargs())  # type: ignore[arg-type]
    assert rule.rule_type == "pullback"
    assert rule.tier == "Mid"
    assert rule.action == "POSITIVE"
    assert rule.tenure == "6m"
    assert rule.rule_version == 1
    assert rule.eligibility == []
    assert rule.entry == []


@pytest.mark.parametrize(
    "rule_type",
    [
        "pullback",
        "severely_broken",
        "emerging",
        "topping",
        "accumulate",
        "trim",
        "watch",
        "hold",
        "placeholder",
    ],
)
def test_cell_rule_accepts_every_rule_type(rule_type: str) -> None:
    rule = CellRule(**_minimal_cell_rule_kwargs(rule_type=rule_type))  # type: ignore[arg-type]
    assert rule.rule_type == rule_type


def test_cell_rule_rejects_unknown_rule_type() -> None:
    with pytest.raises(ValidationError):
        CellRule(**_minimal_cell_rule_kwargs(rule_type="unknown_archetype"))  # type: ignore[arg-type]


@pytest.mark.parametrize("action", ["POSITIVE", "NEUTRAL", "NEGATIVE"])
def test_cell_rule_accepts_canonical_action(action: str) -> None:
    rule = CellRule(**_minimal_cell_rule_kwargs(action=action))  # type: ignore[arg-type]
    assert rule.action == action


@pytest.mark.parametrize("forbidden", ["BUY", "SELL", "ACCUMULATE", "HOLD", "WATCH", "AVOID"])
def test_cell_rule_rejects_display_label_action(forbidden: str) -> None:
    """Display labels are forbidden — they are rendered at the API layer."""
    with pytest.raises(ValidationError):
        CellRule(**_minimal_cell_rule_kwargs(action=forbidden))  # type: ignore[arg-type]


@pytest.mark.parametrize("tier", ["Small", "Mid", "Large"])
def test_cell_rule_accepts_canonical_tier(tier: str) -> None:
    rule = CellRule(**_minimal_cell_rule_kwargs(tier=tier))  # type: ignore[arg-type]
    assert rule.tier == tier


def test_cell_rule_rejects_unknown_tier() -> None:
    with pytest.raises(ValidationError):
        CellRule(**_minimal_cell_rule_kwargs(tier="Micro"))  # type: ignore[arg-type]


@pytest.mark.parametrize("tenure", ["1m", "3m", "6m", "12m"])
def test_cell_rule_accepts_canonical_tenure(tenure: str) -> None:
    rule = CellRule(**_minimal_cell_rule_kwargs(tenure=tenure))  # type: ignore[arg-type]
    assert rule.tenure == tenure


def test_cell_rule_rejects_unknown_tenure() -> None:
    with pytest.raises(ValidationError):
        CellRule(**_minimal_cell_rule_kwargs(tenure="24m"))  # type: ignore[arg-type]


def test_cell_rule_with_eligibility_and_entry_predicates() -> None:
    """Realistic Pullback-style rule with both predicate lists."""
    rule = CellRule(
        **_minimal_cell_rule_kwargs(
            rule_type="pullback",
            eligibility=[
                {
                    "feature": "log_med_tv_60d",
                    "cmp": ">=",
                    "value": Decimal("15"),
                }
            ],
            entry=[
                {
                    "feature": "rs_residual_6m",
                    "cmp": ">",
                    "value": Decimal("0.05"),
                },
                {
                    "feature": "formation_max_dd",
                    "cmp": "<",
                    "value": Decimal("0.25"),
                },
            ],
        )
    )  # type: ignore[arg-type]
    assert len(rule.eligibility) == 1
    assert len(rule.entry) == 2
    assert rule.entry[0].feature == "rs_residual_6m"


# ---------------------------------------------------------------------------
# validate_rule_dsl — the JSONB-blob entry point
# ---------------------------------------------------------------------------


def test_validate_rule_dsl_placeholder_blob_from_migration_089() -> None:
    """The placeholder blob shape seeded by migration 089 must validate."""
    blob = {
        "rule_type": "placeholder",
        "eligibility": [],
        "entry": [],
        "tier": "Mid",
        "action": "POSITIVE",
        "tenure": "6m",
        "rule_version": 0,
        "methodology_lock_ref": "PLACEHOLDER_2026-05-24",
        "notes": "placeholder — real rule_dsl shipped by Phase 0.5g",
    }
    rule = validate_rule_dsl(blob)
    assert rule.rule_type == "placeholder"
    assert rule.tier == "Mid"
    assert rule.action == "POSITIVE"
    assert rule.tenure == "6m"


def test_validate_rule_dsl_rejects_predicate_with_unknown_feature() -> None:
    blob = {
        "rule_type": "pullback",
        "eligibility": [],
        "entry": [
            {
                "feature": "ghost_feature",
                "cmp": ">",
                "value": "0.5",
            }
        ],
        "tier": "Mid",
        "action": "POSITIVE",
        "tenure": "6m",
        "methodology_lock_ref": "TEST_LOCK",
    }
    with pytest.raises(ValidationError) as excinfo:
        validate_rule_dsl(blob)
    assert "not in atlas.features.FEATURES allowlist" in str(excinfo.value)


def test_validate_rule_dsl_methodology_lock_ref_required() -> None:
    blob = {
        "rule_type": "pullback",
        "tier": "Mid",
        "action": "POSITIVE",
        "tenure": "6m",
    }
    with pytest.raises(ValidationError):
        validate_rule_dsl(blob)
