"""Tests for continuous dwell_days recompute.

TDD: these tests were written before the implementation. They define the
contract for recompute_dwell_days: vectorized run-length encoding, 0-indexed,
resets on state change, computed per-instrument independently.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from atlas.intelligence.states.dwell_recompute import recompute_dwell_days


def test_dwell_accumulates_across_a_continuous_run() -> None:
    # Same state 5 consecutive trading days -> dwell 0,1,2,3,4
    panel = pd.DataFrame(
        [
            {"instrument_id": "a", "date": date(2025, 1, d), "state": "stage_1"}
            for d in (2, 3, 6, 7, 8)
        ]
    )
    out = recompute_dwell_days(panel)
    assert out["dwell_days"].tolist() == [0, 1, 2, 3, 4]


def test_dwell_resets_on_state_change() -> None:
    panel = pd.DataFrame(
        [
            {"instrument_id": "a", "date": date(2025, 1, 2), "state": "stage_1"},
            {"instrument_id": "a", "date": date(2025, 1, 3), "state": "stage_1"},
            {"instrument_id": "a", "date": date(2025, 1, 6), "state": "stage_2a"},
            {"instrument_id": "a", "date": date(2025, 1, 7), "state": "stage_2a"},
        ]
    )
    out = recompute_dwell_days(panel)
    assert out["dwell_days"].tolist() == [0, 1, 0, 1]


def test_dwell_computed_per_instrument_independently() -> None:
    """Instruments a and b have interleaved rows; dwell must be tracked separately.

    Instrument a: stage_1 for 3 days, then stage_2a for 2 days -> [0,1,2,0,1]
    Instrument b: stage_1 for 2 days, then stage_3 for 3 days  -> [0,1,0,1,2]
    After sorting by [instrument_id, date] the output order is:
      a 2025-01-02 stage_1   dwell=0
      a 2025-01-03 stage_1   dwell=1
      a 2025-01-06 stage_1   dwell=2
      a 2025-01-07 stage_2a  dwell=0
      a 2025-01-08 stage_2a  dwell=1
      b 2025-01-02 stage_1   dwell=0
      b 2025-01-03 stage_1   dwell=1
      b 2025-01-06 stage_3   dwell=0
      b 2025-01-07 stage_3   dwell=1
      b 2025-01-08 stage_3   dwell=2
    """
    rows = [
        # Instrument a
        {"instrument_id": "a", "date": date(2025, 1, 2), "state": "stage_1"},
        {"instrument_id": "a", "date": date(2025, 1, 3), "state": "stage_1"},
        {"instrument_id": "a", "date": date(2025, 1, 6), "state": "stage_1"},
        {"instrument_id": "a", "date": date(2025, 1, 7), "state": "stage_2a"},
        {"instrument_id": "a", "date": date(2025, 1, 8), "state": "stage_2a"},
        # Instrument b — interleaved in input order to confirm sorting
        {"instrument_id": "b", "date": date(2025, 1, 2), "state": "stage_1"},
        {"instrument_id": "b", "date": date(2025, 1, 3), "state": "stage_1"},
        {"instrument_id": "b", "date": date(2025, 1, 6), "state": "stage_3"},
        {"instrument_id": "b", "date": date(2025, 1, 7), "state": "stage_3"},
        {"instrument_id": "b", "date": date(2025, 1, 8), "state": "stage_3"},
    ]
    # Shuffle input to verify sorting is done internally
    panel = pd.DataFrame(rows[::-1])
    out = recompute_dwell_days(panel)

    a_rows = out[out["instrument_id"] == "a"].sort_values("date")
    b_rows = out[out["instrument_id"] == "b"].sort_values("date")

    assert a_rows["dwell_days"].tolist() == [
        0,
        1,
        2,
        0,
        1,
    ], f"instrument a dwell wrong: {a_rows['dwell_days'].tolist()}"
    assert b_rows["dwell_days"].tolist() == [
        0,
        1,
        0,
        1,
        2,
    ], f"instrument b dwell wrong: {b_rows['dwell_days'].tolist()}"
