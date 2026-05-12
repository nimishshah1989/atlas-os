"""Tests for composer — produce conviction_score per (instrument, date)."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from atlas.intelligence.conviction.composer import (
    CONFIDENCE_LABEL_THRESHOLD,
    apply_weights_to_percentile_ranks,
    assign_confidence_label,
    compute_conviction_scores,
)
from atlas.intelligence.conviction.weight_loader import TierWeightSet


@pytest.fixture
def tier_1_weights() -> TierWeightSet:
    return TierWeightSet(
        tier="tier_1_megacap",
        regime="all",
        holdout_ic=Decimal("0.0511"),
        signals=[
            ("ma_30w_slope_4w", Decimal("0.5"), False),
            ("atr_21", Decimal("0.5"), True),
        ],
        weight_set_version="tier_1_megacap@2026-05-12T00:00:00",
    )


@pytest.fixture
def sample_raw_with_ranks() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "instrument_id": ["A", "B", "C", "D"],
            "ma_30w_slope_4w_pct": [0.9, 0.5, 0.1, 0.7],
            "atr_21_pct": [0.1, 0.5, 0.9, 0.3],
        }
    )


class TestAssignConfidenceLabel:
    def test_holdout_ic_above_threshold_is_industry_grade(self) -> None:
        assert assign_confidence_label(Decimal("0.0511")) == "industry_grade"

    def test_holdout_ic_at_threshold_is_industry_grade(self) -> None:
        # >= 0.05 boundary — must round to industry_grade, not baseline.
        assert assign_confidence_label(Decimal("0.05")) == "industry_grade"

    def test_holdout_ic_below_threshold_is_baseline(self) -> None:
        assert assign_confidence_label(Decimal("0.0268")) == "baseline"

    def test_none_holdout_is_descriptive_only(self) -> None:
        assert assign_confidence_label(None) == "descriptive_only"

    def test_negative_ic_magnitude_above_threshold(self) -> None:
        # Anti-predictive signals still pass the magnitude bar.
        assert assign_confidence_label(Decimal("-0.06")) == "industry_grade"

    def test_threshold_constant(self) -> None:
        assert CONFIDENCE_LABEL_THRESHOLD == Decimal("0.05")


class TestApplyWeights:
    def test_perfectly_aligned_signals_give_high_score(
        self,
        tier_1_weights: TierWeightSet,
        sample_raw_with_ranks: pd.DataFrame,
    ) -> None:
        scored = apply_weights_to_percentile_ranks(sample_raw_with_ranks, tier_1_weights)
        # A: ma_30w = 0.9, atr_21 = 0.1 (flipped → 0.9). Score = 0.5*0.9 + 0.5*0.9 = 0.9.
        a_score = scored.loc[scored["instrument_id"] == "A", "conviction_score"].iloc[0]
        assert a_score == pytest.approx(0.9, abs=0.001)

    def test_score_in_unit_interval(
        self,
        tier_1_weights: TierWeightSet,
        sample_raw_with_ranks: pd.DataFrame,
    ) -> None:
        scored = apply_weights_to_percentile_ranks(sample_raw_with_ranks, tier_1_weights)
        assert scored["conviction_score"].between(0.0, 1.0).all()

    def test_missing_signal_column_skips_signal(self, tier_1_weights: TierWeightSet) -> None:
        df = pd.DataFrame(
            {
                "instrument_id": ["A"],
                "ma_30w_slope_4w_pct": [0.5],
                # atr_21_pct entirely missing
            }
        )
        scored = apply_weights_to_percentile_ranks(df, tier_1_weights)
        # Only ma_30w applied: score = (0.5 * 0.5) / 0.5 = 0.5
        assert scored["conviction_score"].iloc[0] == pytest.approx(0.5, abs=0.001)

    def test_neutral_fill_flagged_in_breakdown(self, tier_1_weights: TierWeightSet) -> None:
        df = pd.DataFrame(
            {
                "instrument_id": ["A", "B"],
                "ma_30w_slope_4w_pct": [0.9, None],
                "atr_21_pct": [0.1, 0.5],
            }
        )
        scored = apply_weights_to_percentile_ranks(df, tier_1_weights)
        a_breakdown = json.loads(
            scored.loc[scored["instrument_id"] == "A", "contributing_signals"].iloc[0]
        )
        b_breakdown = json.loads(
            scored.loc[scored["instrument_id"] == "B", "contributing_signals"].iloc[0]
        )
        assert a_breakdown["ma_30w_slope_4w"]["was_neutral_fill"] is False
        assert b_breakdown["ma_30w_slope_4w"]["was_neutral_fill"] is True

    def test_no_signals_applied_returns_neutral(self) -> None:
        # Edge: weight set references signals not present in df.
        empty_weights = TierWeightSet(
            tier="tier_1_megacap",
            regime="all",
            holdout_ic=Decimal("0"),
            signals=[("nonexistent_signal", Decimal("1.0"), False)],
            weight_set_version="empty@test",
        )
        df = pd.DataFrame({"instrument_id": ["A"]})
        scored = apply_weights_to_percentile_ranks(df, empty_weights)
        assert scored["conviction_score"].iloc[0] == pytest.approx(0.5)


@pytest.mark.integration
class TestComputeConvictionScores:
    def test_returns_scores_for_tiered_instruments(self) -> None:
        from atlas.db import get_engine

        engine = get_engine()
        # Anchor to a date where both OHLCV + metrics exist.
        df = compute_conviction_scores(engine, as_of=date(2026, 4, 9))
        if df.empty:
            pytest.skip("no overlapping ohlcv+metrics data for this date")
        assert "conviction_score" in df.columns
        assert "confidence_label" in df.columns
        assert "contributing_signals" in df.columns
        assert 1 <= len(df) <= 1000
        # Score range
        assert df["conviction_score"].between(0.0, 1.0).all()
        # Confidence label set on every row
        assert df["confidence_label"].isin(["industry_grade", "baseline", "descriptive_only"]).all()
