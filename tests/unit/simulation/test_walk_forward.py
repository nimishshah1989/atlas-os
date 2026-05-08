"""Unit tests for walk-forward window generation — no DB, no vectorbt."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from atlas.simulation.backtest.walk_forward import (
    InsufficientHistoryError,
    generate_oos_windows,
)


def _date_range(months: int) -> tuple[date, date]:
    start = date(2024, 1, 1)
    end = start + timedelta(days=int(months * 30.44))
    return start, end


def test_raises_insufficient_history_below_547_days():
    start = date(2024, 1, 1)
    end = start + timedelta(days=546)
    with pytest.raises(InsufficientHistoryError, match="18 months"):
        generate_oos_windows(start, end)


def test_does_not_raise_at_exactly_547_days():
    start = date(2024, 1, 1)
    end = start + timedelta(days=547)
    windows = generate_oos_windows(start, end)
    assert len(windows) >= 1


def test_twelve_months_raises_insufficient_history():
    # 12 months = ~365 days, below the 547-day minimum required for reliable scoring.
    # The guard enforces that callers provide ≥18 months of history.
    start, end = _date_range(12)
    with pytest.raises(InsufficientHistoryError, match="18 months"):
        generate_oos_windows(start, end)


def test_eighteen_months_produces_ten_oos_windows():
    start, end = _date_range(18)
    windows = generate_oos_windows(start, end)
    assert len(windows) == 10, f"Expected 10, got {len(windows)}"


def test_oos_windows_do_not_overlap_train_period():
    start, end = _date_range(18)
    windows = generate_oos_windows(start, end)
    for win in windows:
        assert (
            win["oos_start"] > win["train_end"]
        ), f"OOS start {win['oos_start']} <= train end {win['train_end']}"


def test_window_structure_has_required_keys():
    start, end = _date_range(18)
    windows = generate_oos_windows(start, end)
    required = {"train_start", "train_end", "oos_start", "oos_end", "window_idx"}
    for win in windows:
        assert required <= win.keys()
