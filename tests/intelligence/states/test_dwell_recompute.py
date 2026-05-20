"""Tests for continuous dwell_days recompute.

TDD: these tests were written before the implementation. They define the
contract for recompute_dwell_days: vectorized run-length encoding, 0-indexed,
resets on state change, computed per-instrument independently.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from atlas.intelligence.states.dwell_recompute import (
    _UPDATE_CHUNK_SIZE,
    _chunked,
    recompute_dwell_days,
)


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


# ---------------------------------------------------------------------------
# _chunked helper tests
# ---------------------------------------------------------------------------


def test_chunked_splits_evenly() -> None:
    # 10 items, chunk size 5 -> [[0..4], [5..9]]
    result = _chunked(list(range(10)), 5)
    assert result == [list(range(0, 5)), list(range(5, 10))]


def test_chunked_last_chunk_shorter() -> None:
    # 12 items, chunk size 5 -> three chunks: 5, 5, 2
    result = _chunked(list(range(12)), 5)
    assert [len(c) for c in result] == [5, 5, 2]
    assert result[2] == [10, 11]


def test_chunked_single_chunk_when_seq_smaller_than_size() -> None:
    result = _chunked([1, 2, 3], 100)
    assert result == [[1, 2, 3]]


def test_chunked_empty_seq_returns_empty_list() -> None:
    assert _chunked([], 5) == []


def test_chunked_size_one_produces_singleton_chunks() -> None:
    result = _chunked([10, 20, 30], 1)
    assert result == [[10], [20], [30]]


def test_chunked_raises_on_zero_size() -> None:
    import pytest

    with pytest.raises(ValueError, match="size must be > 0"):
        _chunked([1, 2], 0)


# ---------------------------------------------------------------------------
# Module-level constant guard
# ---------------------------------------------------------------------------


def test_update_chunk_size_is_5000() -> None:
    assert _UPDATE_CHUNK_SIZE == 5000
    assert isinstance(_UPDATE_CHUNK_SIZE, int)
    assert _UPDATE_CHUNK_SIZE > 0
