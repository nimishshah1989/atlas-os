"""Tests for weight_loader — loads currently-active weight sets per tier."""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas.db import get_engine
from atlas.intelligence.conviction.weight_loader import (
    TierWeightSet,
    load_active_weights,
)


@pytest.mark.integration
class TestLoadActiveWeights:
    def test_returns_one_set_per_tier(self) -> None:
        engine = get_engine()
        result = load_active_weights(engine)
        assert set(result.keys()) == {
            "tier_1_megacap",
            "tier_2_largecap",
            "tier_3_uppermid",
            "tier_4_lowermid",
            "tier_5_smallcap",
        }

    def test_weights_are_decimals(self) -> None:
        engine = get_engine()
        result = load_active_weights(engine)
        tier_1 = result["tier_1_megacap"]
        assert isinstance(tier_1, TierWeightSet)
        assert all(isinstance(w, Decimal) for _, w, _ in tier_1.signals)

    def test_atr_21_flipped_for_tier_1(self) -> None:
        engine = get_engine()
        result = load_active_weights(engine)
        tier_1 = result["tier_1_megacap"]
        atr_entries = [(s, w, f) for s, w, f in tier_1.signals if s == "atr_21"]
        assert len(atr_entries) == 1
        assert atr_entries[0][2] is True

    def test_holdout_ic_present_per_tier(self) -> None:
        engine = get_engine()
        result = load_active_weights(engine)
        for tier_name, weight_set in result.items():
            assert weight_set.holdout_ic is not None, f"{tier_name} missing holdout_ic"
            assert weight_set.holdout_ic >= Decimal("0")

    def test_unknown_regime_returns_empty(self) -> None:
        engine = get_engine()
        result = load_active_weights(engine, regime="Risk-Off")
        assert result == {}
