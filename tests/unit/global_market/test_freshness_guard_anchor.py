"""``--eod`` on a non-session date (a weekend, a holiday) anchors the global freshness guard
to the latest SPY session on or before it, so every check runs against that session.

Asserted through ``main`` on the Labor Day week calendar (``script_loader.LABOR_DAY_WEEK``);
``latest_session_on_or_before`` itself is covered in test_calendar.py. ``spy_sessions`` and
the two checks are stubbed: no DB, no network.
"""

from __future__ import annotations

import datetime as dt

import pytest

from tests.unit.global_market.script_loader import LABOR_DAY_WEEK, load_global_script

guard = load_global_script("freshness_guard")

pytestmark = pytest.mark.unit


def test_a_holiday_eod_is_checked_as_the_prior_session(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dt.date] = []
    monkeypatch.setattr(guard, "spy_sessions", lambda: LABOR_DAY_WEEK)
    monkeypatch.setattr(guard, "check", lambda eod, _cal: seen.append(eod) or [])
    monkeypatch.setattr(guard, "check_board", lambda eod, _cal: seen.append(eod) or [])
    monkeypatch.setattr("sys.argv", ["freshness_guard.py", "--eod", "2026-09-07"])  # Labor Day
    assert guard.main() == 0
    assert seen == [dt.date(2026, 9, 4), dt.date(2026, 9, 4)]  # the Friday before, twice
