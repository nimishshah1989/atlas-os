"""Walk-forward window generator for M7 optimizer.

Window: 6M train / 3M test, slide by 1M.
Minimum history: 547 days (≈18M) to produce ≥10 OOS windows.
Formula: windows = (total_months - train_months - test_months) / slide_months + 1
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import TypedDict


class InsufficientHistoryError(ValueError):
    pass


_MONTH_DAYS = 30.44
_TRAIN_MONTHS = 6
_TEST_MONTHS = 3
_SLIDE_MONTHS = 1
_MIN_DAYS = 547  # ≈18M — ensures ≥10 OOS windows


class OOSWindow(TypedDict):
    window_idx: int
    train_start: date
    train_end: date
    oos_start: date
    oos_end: date


def _add_months(d: date, months: int) -> date:
    """Approximate month addition using 30.44 days/month (floor to avoid drift)."""
    return date.fromordinal(d.toordinal() + math.floor(months * _MONTH_DAYS))


def generate_oos_windows(start: date, end: date) -> list[OOSWindow]:
    """Generate walk-forward OOS windows from [start, end].

    Raises InsufficientHistoryError if (end - start).days < 547.
    """
    total_days = (end - start).days
    if total_days < _MIN_DAYS:
        raise InsufficientHistoryError(
            f"Signal history {total_days} days < {_MIN_DAYS} required (≈18 months). "
            "Need at least 18 months of Atlas signals for reliable optimizer scoring."
        )

    windows: list[OOSWindow] = []
    idx = 0
    train_start = start

    while True:
        train_end = _add_months(train_start, _TRAIN_MONTHS)
        oos_start = train_end + timedelta(days=1)
        oos_end = _add_months(oos_start, _TEST_MONTHS)

        if oos_end > end:
            break

        windows.append(
            OOSWindow(
                window_idx=idx,
                train_start=train_start,
                train_end=train_end,
                oos_start=oos_start,
                oos_end=oos_end,
            )
        )

        train_start = _add_months(train_start, _SLIDE_MONTHS)
        idx += 1

    return windows
