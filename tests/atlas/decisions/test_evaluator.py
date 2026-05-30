"""Tests for atlas.decisions.evaluator internals — predicate evaluation.

Missing/NaN data must fail predicates conservatively (never pass on a NULL),
and the scalar/range/quantile operators must evaluate exactly.
"""

from __future__ import annotations

import math
from decimal import Decimal

import pytest

from atlas.decisions.evaluator import _eval_predicate, _eval_scalar_cmp, _to_decimal
from atlas.decisions.rule_dsl import FeaturePredicate

FEAT = "atr_14"


class TestToDecimal:
    def test_none_is_none(self) -> None:
        assert _to_decimal(None) is None

    def test_nan_float_is_none(self) -> None:
        assert _to_decimal(math.nan) is None

    def test_inf_float_is_none(self) -> None:
        assert _to_decimal(math.inf) is None

    def test_int_coerced(self) -> None:
        assert _to_decimal(3) == Decimal("3")

    def test_float_coerced(self) -> None:
        assert _to_decimal(1.5) == Decimal("1.5")

    def test_garbage_string_is_none(self) -> None:
        assert _to_decimal("not-a-number") is None


class TestScalarCmp:
    @pytest.mark.parametrize(
        ("cmp", "a", "b", "expected"),
        [
            (">", Decimal("2"), Decimal("1"), True),
            (">", Decimal("1"), Decimal("1"), False),
            (">=", Decimal("1"), Decimal("1"), True),
            ("<", Decimal("1"), Decimal("2"), True),
            ("<=", Decimal("2"), Decimal("2"), True),
            ("==", Decimal("2"), Decimal("2"), True),
            ("==", Decimal("2"), Decimal("3"), False),
        ],
    )
    def test_operators(self, cmp: str, a: Decimal, b: Decimal, expected: bool) -> None:
        assert _eval_scalar_cmp(a, cmp, b) is expected

    def test_unsupported_operator_raises(self) -> None:
        with pytest.raises(ValueError, match="unsupported cmp"):
            _eval_scalar_cmp(Decimal("1"), "!=", Decimal("1"))


class TestEvalPredicate:
    def test_scalar_pass(self) -> None:
        p = FeaturePredicate(feature=FEAT, cmp=">", value=Decimal("1.0"))
        assert _eval_predicate(p, {FEAT: 2.0}) is True

    def test_scalar_fail(self) -> None:
        p = FeaturePredicate(feature=FEAT, cmp=">", value=Decimal("5.0"))
        assert _eval_predicate(p, {FEAT: 2.0}) is False

    def test_null_feature_fails_conservatively(self) -> None:
        p = FeaturePredicate(feature=FEAT, cmp=">", value=Decimal("1.0"))
        assert _eval_predicate(p, {FEAT: None}) is False
        assert _eval_predicate(p, {}) is False  # feature absent entirely

    def test_nan_feature_fails(self) -> None:
        p = FeaturePredicate(feature=FEAT, cmp=">", value=Decimal("1.0"))
        assert _eval_predicate(p, {FEAT: math.nan}) is False

    def test_in_range_inclusive(self) -> None:
        p = FeaturePredicate(feature=FEAT, cmp="in_range", value=(Decimal("1"), Decimal("3")))
        assert _eval_predicate(p, {FEAT: 2.0}) is True
        assert _eval_predicate(p, {FEAT: 3.0}) is True  # boundary inclusive
        assert _eval_predicate(p, {FEAT: 4.0}) is False

    def test_in_top_quantile_needs_ranks(self) -> None:
        p = FeaturePredicate(
            feature=FEAT, cmp="in_top_quantile", value=Decimal("1"), value_quantile_n=5
        )
        # No rank map supplied → fails conservatively.
        assert _eval_predicate(p, {FEAT: 9.9}) is False

    def test_in_top_quantile_with_ranks(self) -> None:
        p = FeaturePredicate(
            feature=FEAT, cmp="in_top_quantile", value=Decimal("1"), value_quantile_n=5
        )
        ranks = {FEAT: {"iid1": 0.95, "iid2": 0.50}}
        assert (
            _eval_predicate(p, {FEAT: 9.9}, feature_rank_pcts=ranks, instrument_id="iid1")
            is True  # 0.95 > 1 - 1/5 = 0.80
        )
        assert (
            _eval_predicate(p, {FEAT: 9.9}, feature_rank_pcts=ranks, instrument_id="iid2")
            is False  # 0.50 not in top quintile
        )
