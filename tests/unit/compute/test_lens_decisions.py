"""Unit tests for atlas.compute.lens_decisions — pure-Python, no DB required.

Covers:
  - compute_holdings_diff: entry, exit, increase, decrease, neutral filter
  - compute_holdings_diff: signal quality classification
  - compute_holdings_diff: first-disclosure (empty from_df)
  - compute_holdings_diff: empty to_df
  - compute_decision_score: both, one, no quality pcts
  - compute_decision_score: Sharp / Average / Poor states
  - compute_decision_score: empty diff (all counts zero)
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from atlas.compute.lens_decisions import (
    _HIGH_QUALITY_STATES,
    _LOW_QUALITY_STATES,
    compute_decision_score,
    compute_holdings_diff,
)

# --------------------------------------------------------------------------- #
# Fixtures / helpers                                                           #
# --------------------------------------------------------------------------- #


def _snapshot(*rows: tuple[str, str, float]) -> pd.DataFrame:
    """Build a minimal holdings snapshot DataFrame.

    Each row is (instrument_id, symbol, weight_pct).
    """
    return pd.DataFrame(rows, columns=["instrument_id", "symbol", "weight_pct"])  # type: ignore[call-overload]


_DEFAULT_THRESHOLDS: dict = {
    "decision_score_sharp_threshold": 65.0,
    "decision_score_poor_threshold": 40.0,
    "holdings_weight_change_min_pct": 0.25,
    "decision_score_min_decisions": 3,
}

# Thresholds without the min-decisions floor, for tests that use small diff sets.
_THRESHOLDS_NO_MIN: dict = {**_DEFAULT_THRESHOLDS, "decision_score_min_decisions": 1}

_MSTAR_ID = "F00000WXYZ"
_TO_DATE = date(2024, 4, 30)
_FROM_DATE = date(2024, 3, 31)


# --------------------------------------------------------------------------- #
# compute_holdings_diff                                                        #
# --------------------------------------------------------------------------- #


class TestComputeHoldingsDiff:
    def test_entry_classified_when_not_in_prior_snapshot(self) -> None:
        to_df = _snapshot(("IID001", "RELIANCE", 5.0))
        from_df = _snapshot()  # empty
        result = compute_holdings_diff(to_df, from_df, {}, min_weight_delta_pct=0.25)
        assert len(result) == 1
        assert result.iloc[0]["action"] == "entry"

    def test_exit_classified_when_not_in_current_snapshot(self) -> None:
        to_df = _snapshot()  # stock exited
        from_df = _snapshot(("IID001", "RELIANCE", 5.0))
        result = compute_holdings_diff(to_df, from_df, {}, min_weight_delta_pct=0.25)
        assert len(result) == 1
        assert result.iloc[0]["action"] == "exit"

    def test_increase_classified_for_large_positive_delta(self) -> None:
        to_df = _snapshot(("IID001", "TCS", 6.0))
        from_df = _snapshot(("IID001", "TCS", 5.0))
        result = compute_holdings_diff(to_df, from_df, {}, min_weight_delta_pct=0.25)
        assert len(result) == 1
        assert result.iloc[0]["action"] == "increase"
        assert abs(result.iloc[0]["weight_delta"] - 1.0) < 1e-9

    def test_decrease_classified_for_large_negative_delta(self) -> None:
        to_df = _snapshot(("IID001", "TCS", 4.0))
        from_df = _snapshot(("IID001", "TCS", 5.0))
        result = compute_holdings_diff(to_df, from_df, {}, min_weight_delta_pct=0.25)
        assert len(result) == 1
        assert result.iloc[0]["action"] == "decrease"
        assert abs(result.iloc[0]["weight_delta"] - (-1.0)) < 1e-9

    def test_neutral_changes_filtered_out(self) -> None:
        """Delta smaller than min_weight_delta_pct should produce no rows."""
        to_df = _snapshot(("IID001", "TCS", 5.1))
        from_df = _snapshot(("IID001", "TCS", 5.0))
        result = compute_holdings_diff(to_df, from_df, {}, min_weight_delta_pct=0.25)
        assert result.empty

    def test_first_disclosure_all_entries(self) -> None:
        """When from_df is empty, every holding should be an entry."""
        to_df = _snapshot(("IID001", "A", 3.0), ("IID002", "B", 2.0))
        from_df = pd.DataFrame(columns=["instrument_id", "symbol", "weight_pct"])  # type: ignore[call-overload]
        result = compute_holdings_diff(to_df, from_df, {}, min_weight_delta_pct=0.25)
        assert len(result) == 2
        assert set(result["action"]) == {"entry"}

    def test_empty_to_df_with_nonempty_from_df_produces_exits(self) -> None:
        """Empty current snapshot means all prior holdings were exited."""
        to_df = pd.DataFrame(columns=["instrument_id", "symbol", "weight_pct"])  # type: ignore[call-overload]
        from_df = _snapshot(("IID001", "A", 3.0))
        result = compute_holdings_diff(to_df, from_df, {}, min_weight_delta_pct=0.25)
        assert len(result) == 1
        assert result.iloc[0]["action"] == "exit"

    def test_both_empty_returns_empty_result(self) -> None:
        """Both snapshots empty — nothing to diff."""
        to_df = pd.DataFrame(columns=["instrument_id", "symbol", "weight_pct"])  # type: ignore[call-overload]
        from_df = pd.DataFrame(columns=["instrument_id", "symbol", "weight_pct"])  # type: ignore[call-overload]
        result = compute_holdings_diff(to_df, from_df, {}, min_weight_delta_pct=0.25)
        assert result.empty

    def test_weight_columns_populated_correctly(self) -> None:
        to_df = _snapshot(("IID001", "HDFC", 7.0))
        from_df = _snapshot(("IID001", "HDFC", 5.0))
        result = compute_holdings_diff(to_df, from_df, {}, min_weight_delta_pct=0.25)
        row = result.iloc[0]
        assert row["weight_before"] == 5.0
        assert row["weight_after"] == 7.0
        assert abs(row["weight_delta"] - 2.0) < 1e-9

    def test_entry_into_high_quality_state_gets_high_signal(self) -> None:
        for state in _HIGH_QUALITY_STATES:
            to_df = _snapshot(("IID001", "X", 5.0))
            from_df = pd.DataFrame(columns=["instrument_id", "symbol", "weight_pct"])  # type: ignore[call-overload]
            state_map = {"IID001": (state, "Accelerating")}
            result = compute_holdings_diff(to_df, from_df, state_map, min_weight_delta_pct=0.25)
            assert result.iloc[0]["signal_quality"] == "high", (
                f"Expected high for entry into {state}"
            )

    def test_entry_into_low_quality_state_gets_low_signal(self) -> None:
        for state in _LOW_QUALITY_STATES:
            to_df = _snapshot(("IID001", "X", 5.0))
            from_df = pd.DataFrame(columns=["instrument_id", "symbol", "weight_pct"])  # type: ignore[call-overload]
            state_map = {"IID001": (state, "Declining")}
            result = compute_holdings_diff(to_df, from_df, state_map, min_weight_delta_pct=0.25)
            assert result.iloc[0]["signal_quality"] == "low", f"Expected low for entry into {state}"

    def test_exit_from_low_quality_state_gets_high_signal(self) -> None:
        for state in _LOW_QUALITY_STATES:
            to_df = pd.DataFrame(columns=["instrument_id", "symbol", "weight_pct"])  # type: ignore[call-overload]
            from_df = _snapshot(("IID001", "X", 5.0))
            state_map = {"IID001": (state, "Declining")}
            result = compute_holdings_diff(to_df, from_df, state_map, min_weight_delta_pct=0.25)
            assert result.iloc[0]["signal_quality"] == "high", (
                f"Expected high for exit from {state}"
            )

    def test_exit_from_high_quality_state_gets_low_signal(self) -> None:
        for state in _HIGH_QUALITY_STATES:
            to_df = pd.DataFrame(columns=["instrument_id", "symbol", "weight_pct"])  # type: ignore[call-overload]
            from_df = _snapshot(("IID001", "X", 5.0))
            state_map = {"IID001": (state, "Accelerating")}
            result = compute_holdings_diff(to_df, from_df, state_map, min_weight_delta_pct=0.25)
            assert result.iloc[0]["signal_quality"] == "low", f"Expected low for exit from {state}"

    def test_unknown_rs_state_gets_neutral_signal(self) -> None:
        to_df = _snapshot(("IID001", "X", 5.0))
        from_df = pd.DataFrame(columns=["instrument_id", "symbol", "weight_pct"])  # type: ignore[call-overload]
        # No state_map entry => rs_state is NaN => neutral
        result = compute_holdings_diff(to_df, from_df, {}, min_weight_delta_pct=0.25)
        assert result.iloc[0]["signal_quality"] == "neutral"

    def test_result_has_all_expected_columns(self) -> None:
        to_df = _snapshot(("IID001", "A", 5.0))
        from_df = pd.DataFrame(columns=["instrument_id", "symbol", "weight_pct"])  # type: ignore[call-overload]
        result = compute_holdings_diff(to_df, from_df, {}, min_weight_delta_pct=0.25)
        expected_cols = {
            "instrument_id",
            "symbol",
            "action",
            "weight_before",
            "weight_after",
            "weight_delta",
            "rs_state_at_action",
            "momentum_state_at_action",
            "signal_quality",
        }
        assert expected_cols.issubset(set(result.columns))

    def test_mixed_changes_in_one_diff(self) -> None:
        """Snapshot with entry, exit, increase, decrease, and neutral all at once."""
        to_df = _snapshot(
            ("IID001", "NEW", 3.0),  # entry
            ("IID003", "INC", 8.0),  # increase (+3.0)
            ("IID004", "DEC", 2.0),  # decrease (-3.0)
            ("IID005", "FLAT", 5.1),  # neutral (delta < 0.25)
        )
        from_df = _snapshot(
            ("IID002", "EXIT", 4.0),  # exit
            ("IID003", "INC", 5.0),
            ("IID004", "DEC", 5.0),
            ("IID005", "FLAT", 5.0),
        )
        result = compute_holdings_diff(to_df, from_df, {}, min_weight_delta_pct=0.25)
        actions = set(result["action"])
        assert "entry" in actions
        assert "exit" in actions
        assert "increase" in actions
        assert "decrease" in actions
        # FLAT should be filtered out
        assert len(result) == 4


# --------------------------------------------------------------------------- #
# compute_decision_score                                                       #
# --------------------------------------------------------------------------- #


class TestComputeDecisionScore:
    def _make_diff(self, rows: list[dict]) -> pd.DataFrame:
        return pd.DataFrame(rows)

    def test_sharp_state_when_score_above_threshold(self) -> None:
        # net_quality=2, total=2 → (2/2)*50+50=100.  Use no-min variant (2 < default floor of 3).
        diff = self._make_diff(
            [
                {"action": "entry", "signal_quality": "high"},
                {"action": "exit", "signal_quality": "high"},
            ]
        )
        score = compute_decision_score(diff, _MSTAR_ID, _TO_DATE, _FROM_DATE, _THRESHOLDS_NO_MIN)
        assert score["decision_state"] == "Sharp"
        assert score["signal_score"] == 100.0

    def test_poor_state_when_score_below_threshold(self) -> None:
        # net_quality=-2, total=2 → (-2/2)*50+50=0.  Use no-min variant.
        diff = self._make_diff(
            [
                {"action": "entry", "signal_quality": "low"},
                {"action": "exit", "signal_quality": "low"},
            ]
        )
        score = compute_decision_score(diff, _MSTAR_ID, _TO_DATE, _FROM_DATE, _THRESHOLDS_NO_MIN)
        assert score["decision_state"] == "Poor"
        assert score["signal_score"] == 0.0

    def test_average_state_between_thresholds(self) -> None:
        # 50% quality entries, 50% quality exits → signal_score = 50.0 (Average)
        diff = self._make_diff(
            [
                {"action": "entry", "signal_quality": "high"},
                {"action": "entry", "signal_quality": "low"},
                {"action": "exit", "signal_quality": "high"},
                {"action": "exit", "signal_quality": "low"},
            ]
        )
        score = compute_decision_score(diff, _MSTAR_ID, _TO_DATE, _FROM_DATE, _DEFAULT_THRESHOLDS)
        assert score["decision_state"] == "Average"
        assert score["signal_score"] == 50.0

    def test_only_entries_no_exits(self) -> None:
        """When only entries exist signal_score comes from entries only.  Use no-min variant."""
        diff = self._make_diff(
            [
                {"action": "entry", "signal_quality": "high"},
                {"action": "entry", "signal_quality": "high"},
            ]
        )
        score = compute_decision_score(diff, _MSTAR_ID, _TO_DATE, _FROM_DATE, _THRESHOLDS_NO_MIN)
        assert score["quality_entries_pct"] == 100.0
        assert score["quality_exits_pct"] is None
        assert score["signal_score"] == 100.0

    def test_only_exits_no_entries(self) -> None:
        # 1 low exit: net_quality=-1, total=1 → (-1/1)*50+50=0.  Use no-min variant.
        diff = self._make_diff(
            [
                {"action": "exit", "signal_quality": "low"},
            ]
        )
        score = compute_decision_score(diff, _MSTAR_ID, _TO_DATE, _FROM_DATE, _THRESHOLDS_NO_MIN)
        assert score["quality_entries_pct"] is None
        assert score["quality_exits_pct"] == 0.0
        assert score["signal_score"] == 0.0

    def test_only_increases_decreases_no_entries_exits(self) -> None:
        """Increases/decreases don't contribute to quality pcts → signal_score is None."""
        diff = self._make_diff(
            [
                {"action": "increase", "signal_quality": "neutral"},
                {"action": "decrease", "signal_quality": "neutral"},
            ]
        )
        score = compute_decision_score(diff, _MSTAR_ID, _TO_DATE, _FROM_DATE, _DEFAULT_THRESHOLDS)
        assert score["quality_entries_pct"] is None
        assert score["quality_exits_pct"] is None
        assert score["signal_score"] is None
        assert score["decision_state"] is None

    def test_empty_diff_all_counts_zero(self) -> None:
        diff = pd.DataFrame(columns=["action", "signal_quality"])  # type: ignore[call-overload]
        score = compute_decision_score(diff, _MSTAR_ID, _TO_DATE, _FROM_DATE, _DEFAULT_THRESHOLDS)
        assert score["entries_count"] == 0
        assert score["exits_count"] == 0
        assert score["increases_count"] == 0
        assert score["decreases_count"] == 0
        assert score["signal_score"] is None
        assert score["decision_state"] is None

    def test_counts_correct(self) -> None:
        diff = self._make_diff(
            [
                {"action": "entry", "signal_quality": "high"},
                {"action": "entry", "signal_quality": "low"},
                {"action": "exit", "signal_quality": "high"},
                {"action": "increase", "signal_quality": "neutral"},
                {"action": "decrease", "signal_quality": "neutral"},
                {"action": "decrease", "signal_quality": "neutral"},
            ]
        )
        score = compute_decision_score(diff, _MSTAR_ID, _TO_DATE, _FROM_DATE, _DEFAULT_THRESHOLDS)
        assert score["entries_count"] == 2
        assert score["exits_count"] == 1
        assert score["increases_count"] == 1
        assert score["decreases_count"] == 2

    def test_period_date_and_mstar_id_in_result(self) -> None:
        diff = pd.DataFrame(columns=["action", "signal_quality"])  # type: ignore[call-overload]
        score = compute_decision_score(diff, _MSTAR_ID, _TO_DATE, _FROM_DATE, _DEFAULT_THRESHOLDS)
        assert score["mstar_id"] == _MSTAR_ID
        assert score["period_date"] == _TO_DATE

    def test_no_from_date_accepted(self) -> None:
        """First-ever disclosure has no from_date — should not raise."""
        diff = pd.DataFrame(columns=["action", "signal_quality"])  # type: ignore[call-overload]
        score = compute_decision_score(diff, _MSTAR_ID, _TO_DATE, None, _DEFAULT_THRESHOLDS)
        assert score["mstar_id"] == _MSTAR_ID
        assert score["signal_score"] is None

    def test_custom_thresholds_respected(self) -> None:
        """Sharp threshold at 80 — net-quality score of 75 should be Average.

        4 entries: 3 high, 1 low → net_quality = 3-1 = 2
        signal_score = (2/4)*50 + 50 = 75.0  → Average with sharp@80
        """
        custom = {
            "decision_score_sharp_threshold": 80.0,
            "decision_score_poor_threshold": 30.0,
            "decision_score_min_decisions": 1,
        }
        diff = self._make_diff(
            [
                {"action": "entry", "signal_quality": "high"},
                {"action": "entry", "signal_quality": "low"},
                {"action": "entry", "signal_quality": "high"},
                {"action": "entry", "signal_quality": "high"},
            ]
        )
        score = compute_decision_score(diff, _MSTAR_ID, _TO_DATE, _FROM_DATE, custom)
        assert score["signal_score"] == 75.0
        assert score["decision_state"] == "Average"

    def test_min_decisions_floor_returns_none(self) -> None:
        """Periods with fewer than min_decisions entry+exit rows get signal_score=None."""
        diff = self._make_diff(
            [
                {"action": "entry", "signal_quality": "high"},
                {"action": "entry", "signal_quality": "high"},
                # only 2 decisions, default min is 3
            ]
        )
        score = compute_decision_score(diff, _MSTAR_ID, _TO_DATE, _FROM_DATE, _DEFAULT_THRESHOLDS)
        assert score["signal_score"] is None
        assert score["decision_state"] is None

    def test_first_observation_skips_scoring(self) -> None:
        """from_date=None (first-ever snapshot): counts stored, signal_score must be None."""
        diff = self._make_diff(
            [
                {"action": "entry", "signal_quality": "high"},
                {"action": "entry", "signal_quality": "high"},
                {"action": "entry", "signal_quality": "high"},
            ]
        )
        score = compute_decision_score(diff, _MSTAR_ID, _TO_DATE, None, _DEFAULT_THRESHOLDS)
        assert score["entries_count"] == 3
        assert score["signal_score"] is None
        assert score["decision_state"] is None

    def test_exit_uses_from_state_map(self) -> None:
        """Exit quality should use exit_state_map (from_date states), not to_date states."""
        to_df = pd.DataFrame(columns=["instrument_id", "symbol", "weight_pct"])  # type: ignore[call-overload]
        from_df = _snapshot(("IID001", "X", 5.0))
        # to_date state_map has no entry for IID001 (stock left universe)
        state_map: dict = {}
        # exit_state_map records Weak at from_date
        exit_state_map = {"IID001": ("Weak", "Declining")}
        result = compute_holdings_diff(
            to_df, from_df, state_map, 0.25, exit_state_map=exit_state_map
        )
        assert result.iloc[0]["rs_state_at_action"] == "Weak"
        assert result.iloc[0]["signal_quality"] == "high"  # exit from Weak = high quality
