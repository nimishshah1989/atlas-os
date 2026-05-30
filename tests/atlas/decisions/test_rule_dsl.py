"""Tests for atlas.decisions.rule_dsl — cell-rule DSL validation.

The DSL is the contract between methodology and the daily signal engine; a bad
predicate must fail loudly at validation, never silently as a NaN at inference.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from atlas.decisions.rule_dsl import FeaturePredicate, validate_rule_dsl

# Two known-good feature names from atlas.features.FEATURES.
FEAT = "atr_14"
FEAT2 = "beta_60d"


def _base_rule(**overrides: object) -> dict:
    rule: dict[str, object] = {
        "rule_type": "pullback",
        "tier": "Large",
        "action": "POSITIVE",
        "tenure": "6m",
        "methodology_lock_ref": "methodology-lock-2026-05-23",
        "eligibility": [],
        "entry": [{"feature": FEAT, "cmp": ">", "value": Decimal("1.5")}],
    }
    rule.update(overrides)
    return rule


class TestFeaturePredicate:
    def test_valid_scalar_predicate(self) -> None:
        p = FeaturePredicate(feature=FEAT, cmp=">", value=Decimal("1.0"))
        assert p.feature == FEAT and p.cmp == ">"

    def test_unknown_feature_rejected(self) -> None:
        with pytest.raises(ValidationError, match="allowlist"):
            FeaturePredicate(feature="not_a_real_feature", cmp=">", value=Decimal("1"))

    def test_in_range_requires_ordered_tuple(self) -> None:
        ok = FeaturePredicate(feature=FEAT, cmp="in_range", value=(Decimal("1"), Decimal("2")))
        assert ok.cmp == "in_range"
        with pytest.raises(ValidationError, match="low must be <= high"):
            FeaturePredicate(feature=FEAT, cmp="in_range", value=(Decimal("2"), Decimal("1")))

    def test_in_range_rejects_scalar_value(self) -> None:
        with pytest.raises(ValidationError, match="tuple"):
            FeaturePredicate(feature=FEAT, cmp="in_range", value=Decimal("1"))

    def test_scalar_cmp_rejects_tuple_value(self) -> None:
        with pytest.raises(ValidationError, match="scalar"):
            FeaturePredicate(feature=FEAT, cmp=">", value=(Decimal("1"), Decimal("2")))

    def test_in_top_quantile_requires_n_ge_2(self) -> None:
        with pytest.raises(ValidationError, match="value_quantile_n"):
            FeaturePredicate(feature=FEAT, cmp="in_top_quantile", value=Decimal("1"))
        ok = FeaturePredicate(
            feature=FEAT, cmp="in_top_quantile", value=Decimal("1"), value_quantile_n=5
        )
        assert ok.value_quantile_n == 5


class TestValidateRuleDsl:
    def test_full_rule_round_trips(self) -> None:
        rule = validate_rule_dsl(_base_rule())
        assert rule.rule_type == "pullback"
        assert rule.tier == "Large"
        assert len(rule.entry) == 1

    def test_bad_rule_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_rule_dsl(_base_rule(rule_type="not_an_archetype"))

    def test_entry_predicate_with_bad_feature_rejected(self) -> None:
        bad = _base_rule(entry=[{"feature": "bogus", "cmp": ">", "value": Decimal("1")}])
        with pytest.raises(ValidationError, match="allowlist"):
            validate_rule_dsl(bad)
