"""Unit tests for enrich_fund_decision_outcomes outcome quality derivation.

Tests the _derive_outcome_quality pure function — all cases from the spec
outcome quality definition. No DB required.
"""

from __future__ import annotations

from scripts.enrich_fund_decision_outcomes import _derive_outcome_quality


class TestDeriveOutcomeQuality:
    def test_entry_into_leader_is_good(self):
        assert _derive_outcome_quality("entry", "Leader") == "good"

    def test_entry_into_strong_is_good(self):
        assert _derive_outcome_quality("entry", "Strong") == "good"

    def test_entry_into_emerging_is_good(self):
        assert _derive_outcome_quality("entry", "Emerging") == "good"

    def test_entry_into_weak_is_bad(self):
        assert _derive_outcome_quality("entry", "Weak") == "bad"

    def test_entry_into_laggard_is_bad(self):
        assert _derive_outcome_quality("entry", "Laggard") == "bad"

    def test_exit_from_weak_is_good(self):
        assert _derive_outcome_quality("exit", "Weak") == "good"

    def test_exit_from_laggard_is_good(self):
        assert _derive_outcome_quality("exit", "Laggard") == "good"

    def test_exit_from_leader_is_bad(self):
        assert _derive_outcome_quality("exit", "Leader") == "bad"

    def test_exit_from_strong_is_bad(self):
        assert _derive_outcome_quality("exit", "Strong") == "bad"

    def test_increase_is_always_neutral(self):
        assert _derive_outcome_quality("increase", "Leader") == "neutral"

    def test_decrease_is_always_neutral(self):
        assert _derive_outcome_quality("decrease", "Laggard") == "neutral"

    def test_none_rs_state_is_neutral(self):
        assert _derive_outcome_quality("entry", None) == "neutral"

    def test_unknown_rs_state_is_neutral(self):
        assert _derive_outcome_quality("entry", "Unknown") == "neutral"

    def test_entry_neutral_rs_is_neutral(self):
        assert _derive_outcome_quality("entry", "Neutral") == "neutral"
