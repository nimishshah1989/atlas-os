"""The global freshness guard on a timestamptz-guarded table (instrument_master.updated_at).

``check_board`` measures ``max(<col>)`` in SPY sessions; ``instrument_master`` is guarded on
``updated_at`` (a timestamptz), which ``sessions_behind`` cannot compare with the EOD date.
The guard converts it to the New York calendar day first — asserted here on injected
datetimes and the Labor Day week calendar (``script_loader.LABOR_DAY_WEEK``).

Pure: ``_gdb.scalar`` is replaced by a stub; no DB, no network.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from tests.unit.global_market.script_loader import LABOR_DAY_WEEK, load_global_script

pytestmark = pytest.mark.unit

NY = ZoneInfo("America/New_York")


@pytest.fixture
def g():
    return load_global_script("freshness_guard")


def test_instrument_master_is_guarded_on_updated_at_with_the_weekly_lag(g) -> None:
    assert ("instrument_master", "updated_at", 8) in g.BOARD_TABLES
    assert g.PRODUCERS["instrument_master"] == "build_identity.py"


def test_as_date_takes_the_new_york_day_of_an_aware_timestamp(g) -> None:
    # Sat 01:30 UTC (the weekly cron) is Fri 21:30 in New York: the Friday's identity run.
    assert g._as_date(dt.datetime(2026, 9, 5, 1, 30, tzinfo=dt.UTC)) == dt.date(2026, 9, 4)
    assert g._as_date(dt.datetime(2026, 9, 4, 16, 0, tzinfo=NY)) == dt.date(2026, 9, 4)
    assert g._as_date(dt.date(2026, 9, 4)) == dt.date(2026, 9, 4)  # a date column passes through


def test_check_board_counts_sessions_behind_from_the_timestamp(g, monkeypatch) -> None:
    monkeypatch.setattr(g, "BOARD_TABLES", [("instrument_master", "updated_at", 8)])
    # Touched Fri 09-04 21:30 NY (Sat 01:30 UTC); EOD Tue 09-08 → one session behind (09-08).
    stamp = dt.datetime(2026, 9, 5, 1, 30, tzinfo=dt.UTC)
    monkeypatch.setattr(g._gdb, "scalar", lambda _sql, _params=None: stamp)
    assert g.check_board(dt.date(2026, 9, 8), LABOR_DAY_WEEK) == []  # 1 behind, tolerance 8


def test_check_board_flags_a_stale_timestamp(g, monkeypatch) -> None:
    monkeypatch.setattr(g, "BOARD_TABLES", [("instrument_master", "updated_at", 0)])
    stamp = dt.datetime(2026, 9, 5, 1, 30, tzinfo=dt.UTC)  # Fri 09-04 in New York
    monkeypatch.setattr(g._gdb, "scalar", lambda _sql, _params=None: stamp)
    warn = g.check_board(dt.date(2026, 9, 8), LABOR_DAY_WEEK)
    assert warn == ["instrument_master: 1 session(s) behind (max=2026-09-04)"]


def test_check_board_reports_an_empty_table(g, monkeypatch) -> None:
    monkeypatch.setattr(g, "BOARD_TABLES", [("instrument_master", "updated_at", 8)])
    monkeypatch.setattr(g._gdb, "scalar", lambda _sql, _params=None: None)
    assert g.check_board(dt.date(2026, 9, 8), LABOR_DAY_WEEK) == ["instrument_master: EMPTY"]
