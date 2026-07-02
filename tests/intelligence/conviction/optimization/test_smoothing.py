"""Tests for the Bayesian smoothing primitive."""

from __future__ import annotations

from decimal import Decimal

import pytest
from atlas.intelligence.conviction.optimization.smoothing import (
    DEFAULT_LAMBDA,
    blend_weights,
)


def _to_d(d: dict[str, float]) -> dict[str, Decimal]:
    return {k: Decimal(str(v)) for k, v in d.items()}


class TestBlendWeights:
    def test_lambda_zero_returns_current(self) -> None:
        current = _to_d({"a": 0.6, "b": 0.4})
        proposed = _to_d({"a": 0.1, "b": 0.9})
        result = blend_weights(current, proposed, lambda_=Decimal("0"))
        # Renormalized after blending — but lambda=0 means proposed has no
        # weight, so result must equal current.
        assert result["a"] == pytest.approx(Decimal("0.6"), abs=Decimal("1e-9"))
        assert result["b"] == pytest.approx(Decimal("0.4"), abs=Decimal("1e-9"))

    def test_lambda_one_returns_proposed(self) -> None:
        current = _to_d({"a": 0.6, "b": 0.4})
        proposed = _to_d({"a": 0.1, "b": 0.9})
        result = blend_weights(current, proposed, lambda_=Decimal("1"))
        assert result["a"] == pytest.approx(Decimal("0.1"), abs=Decimal("1e-9"))
        assert result["b"] == pytest.approx(Decimal("0.9"), abs=Decimal("1e-9"))

    def test_lambda_default_produces_85_15_blend(self) -> None:
        current = _to_d({"a": 1.0, "b": 0.0})
        proposed = _to_d({"a": 0.0, "b": 1.0})
        result = blend_weights(current, proposed)
        assert DEFAULT_LAMBDA == Decimal("0.15")
        # 0.85*1.0 + 0.15*0.0 = 0.85 → renormalize-of-1.0 sum is 0.85
        # but total is 0.85 + 0.15 = 1.0 → unchanged after renormalize.
        assert result["a"] == pytest.approx(Decimal("0.85"), abs=Decimal("1e-9"))
        assert result["b"] == pytest.approx(Decimal("0.15"), abs=Decimal("1e-9"))

    def test_result_sums_to_one(self) -> None:
        current = _to_d({"a": 0.5, "b": 0.3, "c": 0.2})
        proposed = _to_d({"a": 0.1, "b": 0.5, "c": 0.4})
        result = blend_weights(current, proposed, lambda_=Decimal("0.3"))
        total = sum(result.values())
        assert total == pytest.approx(Decimal("1.0"), abs=Decimal("1e-9"))

    def test_signal_only_in_proposed_appears_in_blend(self) -> None:
        current = _to_d({"a": 1.0})
        proposed = _to_d({"a": 0.5, "b": 0.5})
        result = blend_weights(current, proposed, lambda_=Decimal("0.5"))
        # Pre-renormalize: a=0.75, b=0.25 → already sums to 1.0.
        assert "b" in result
        assert result["b"] == pytest.approx(Decimal("0.25"), abs=Decimal("1e-9"))

    def test_invalid_lambda_raises(self) -> None:
        current = _to_d({"a": 1.0})
        proposed = _to_d({"a": 1.0})
        with pytest.raises(ValueError, match="lambda_"):
            blend_weights(current, proposed, lambda_=Decimal("1.5"))
        with pytest.raises(ValueError, match="lambda_"):
            blend_weights(current, proposed, lambda_=Decimal("-0.1"))
