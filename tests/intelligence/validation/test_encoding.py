"""Unit tests for state-to-numeric encoding."""

import pandas as pd
import pytest

from atlas.intelligence.validation.encoding import (
    DIMENSION_WEIGHTS,
    SENTINEL_STATES,
    STATE_ENCODINGS,
    compute_decision_state_score,
    encode_state,
)


class TestEncodeState:
    def test_rs_leader_is_one(self):
        assert encode_state("rs_state", "Leader") == 1.0

    def test_rs_laggard_is_zero(self):
        assert encode_state("rs_state", "Laggard") == 0.0

    def test_momentum_accelerating_is_one(self):
        assert encode_state("momentum_state", "Accelerating") == 1.0

    def test_regime_risk_on_is_one(self):
        assert encode_state("regime_state", "Risk-On") == 1.0

    def test_regime_risk_off_is_zero(self):
        assert encode_state("regime_state", "Risk-Off") == 0.0

    def test_sentinel_returns_none(self):
        assert encode_state("rs_state", "INSUFFICIENT_HISTORY") is None
        assert encode_state("rs_state", "ILLIQUID") is None
        assert encode_state("rs_state", "DISLOCATION_SUSPENDED") is None

    def test_unknown_state_raises(self):
        with pytest.raises(ValueError, match="unknown rs_state"):
            encode_state("rs_state", "Bogus")

    def test_unknown_dimension_raises(self):
        with pytest.raises(KeyError):
            encode_state("nonsense_state", "Leader")


class TestComputeDecisionStateScore:
    def test_all_top_states_give_one(self):
        row = pd.Series(
            {
                "rs_state": "Leader",
                "momentum_state": "Accelerating",
                "risk_state": "Low",
                "volume_state": "Accumulation",
                "sector_state": "Overweight",
                "regime_state": "Risk-On",
            }
        )
        score = compute_decision_state_score(row)
        assert score == pytest.approx(1.0, abs=1e-9)

    def test_all_bottom_states_give_zero(self):
        row = pd.Series(
            {
                "rs_state": "Laggard",
                "momentum_state": "Collapsing",
                "risk_state": "High",
                "volume_state": "Heavy Distribution",
                "sector_state": "Avoid",
                "regime_state": "Risk-Off",
            }
        )
        score = compute_decision_state_score(row)
        assert score == pytest.approx(0.0, abs=1e-9)

    def test_any_sentinel_returns_none(self):
        row = pd.Series(
            {
                "rs_state": "INSUFFICIENT_HISTORY",  # one sentinel
                "momentum_state": "Accelerating",
                "risk_state": "Low",
                "volume_state": "Accumulation",
                "sector_state": "Overweight",
                "regime_state": "Risk-On",
            }
        )
        assert compute_decision_state_score(row) is None

    def test_weights_sum_to_one(self):
        assert sum(DIMENSION_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-9)

    def test_intermediate_blend(self):
        row = pd.Series(
            {
                "rs_state": "Strong",  # 0.85 × 0.35 = 0.2975
                "momentum_state": "Flat",  # 0.5  × 0.25 = 0.125
                "risk_state": "Normal",  # 0.75 × 0.15 = 0.1125
                "volume_state": "Neutral",  # 0.5  × 0.10 = 0.05
                "sector_state": "Neutral",  # 0.5  × 0.10 = 0.05
                "regime_state": "Constructive",  # 0.7  × 0.05 = 0.035
            }
        )
        # Total = 0.67
        score = compute_decision_state_score(row)
        assert score == pytest.approx(0.67, abs=1e-3)

    def test_sentinel_constants_defined(self):
        assert "INSUFFICIENT_HISTORY" in SENTINEL_STATES
        assert "ILLIQUID" in SENTINEL_STATES
        assert "DISLOCATION_SUSPENDED" in SENTINEL_STATES

    def test_all_six_dimensions_have_encodings(self):
        for dim in DIMENSION_WEIGHTS.keys():
            assert dim in STATE_ENCODINGS, f"{dim} missing from STATE_ENCODINGS"
