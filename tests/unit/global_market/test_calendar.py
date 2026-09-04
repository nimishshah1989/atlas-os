"""Calendar arithmetic on injected datetimes and hand-listed dates.

Nothing here is market data: a Friday, a DST switch and a hand-written list of session
dates are calendar facts, not observations of any instrument (rule #0).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from atlas.global_market import calendar as cal

pytestmark = pytest.mark.unit

NY = ZoneInfo("America/New_York")

# Mon 2026-03-02 … Fri 03-06, then Mon 03-09 and Tue 03-10 (03-07/08 is the weekend).
_WEEK = [
    date(2026, 3, 2),
    date(2026, 3, 3),
    date(2026, 3, 4),
    date(2026, 3, 5),
    date(2026, 3, 6),
    date(2026, 3, 9),
    date(2026, 3, 10),
]


# ── eod_cutoff ──


def test_before_close_hour_the_cutoff_is_yesterday() -> None:
    assert cal.eod_cutoff(datetime(2026, 3, 6, 16, 59, tzinfo=NY)) == date(2026, 3, 5)


def test_at_close_hour_the_cutoff_is_today() -> None:
    assert cal.eod_cutoff(datetime(2026, 3, 6, 17, 0, tzinfo=NY)) == date(2026, 3, 6)


def test_utc_input_is_converted_to_new_york() -> None:
    # January: 22:00 UTC is 17:00 EST → today; a minute earlier → yesterday.
    assert cal.eod_cutoff(datetime(2026, 1, 15, 22, 0, tzinfo=UTC)) == date(2026, 1, 15)
    assert cal.eod_cutoff(datetime(2026, 1, 15, 21, 59, tzinfo=UTC)) == date(2026, 1, 14)


def test_cutoff_is_dst_aware() -> None:
    """US DST starts Sun 2026-03-08. The same UTC wall time, 21:00, is 16:00 EST on the
    Friday before (still live → previous day) and 17:00 EDT on the Monday after (complete)."""
    assert cal.eod_cutoff(datetime(2026, 3, 6, 21, 0, tzinfo=UTC)) == date(2026, 3, 5)
    assert cal.eod_cutoff(datetime(2026, 3, 9, 21, 0, tzinfo=UTC)) == date(2026, 3, 9)


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        cal.eod_cutoff(datetime(2026, 3, 6, 17, 0))


def test_close_hour_is_a_parameter() -> None:
    at_1600 = datetime(2026, 3, 6, 16, 0, tzinfo=NY)
    assert cal.eod_cutoff(at_1600) == date(2026, 3, 5)
    assert cal.eod_cutoff(at_1600, close_hour=16) == date(2026, 3, 6)


# ── sessions / latest_session_on_or_before ──


def test_sessions_sorts_and_dedupes_whatever_the_query_returned() -> None:
    shuffled = [_WEEK[4], _WEEK[0], _WEEK[4], _WEEK[2], _WEEK[1], _WEEK[3]]
    assert cal.sessions(shuffled) == _WEEK[:5]


def test_latest_session_on_or_before() -> None:
    assert cal.latest_session_on_or_before(_WEEK, date(2026, 3, 8)) == date(2026, 3, 6)  # Sunday
    assert cal.latest_session_on_or_before(_WEEK, date(2026, 3, 4)) == date(2026, 3, 4)  # exact
    assert cal.latest_session_on_or_before(_WEEK, date(2026, 3, 1)) is None  # before first


# ── sessions_behind ──


@pytest.mark.parametrize(
    ("mx", "eod", "expected"),
    [
        (date(2026, 3, 6), date(2026, 3, 9), 1),  # Fri → Mon: one session
        (date(2026, 3, 6), date(2026, 3, 8), 0),  # Fri → Sun: the weekend is not a session
        (date(2026, 3, 4), date(2026, 3, 10), 4),  # Wed → next Tue: 5, 6, 9, 10
        (date(2026, 3, 10), date(2026, 3, 10), 0),  # at the EOD
        (date(2026, 3, 10), date(2026, 3, 9), 0),  # ahead of the EOD is never "behind"
        (date(2026, 3, 7), date(2026, 3, 10), 2),  # mx on a Saturday (not a session): 9, 10
    ],
)
def test_sessions_behind_counts_sessions_in_the_half_open_window(
    mx: date, eod: date, expected: int
) -> None:
    assert cal.sessions_behind(_WEEK, mx, eod) == expected


def test_a_weekday_holiday_is_not_a_session() -> None:
    """The reason this is not busday_count: with Monday 03-09 absent from the anchor's
    bars, a table last written on Friday is 0 behind an EOD of Monday, not 1."""
    without_monday = [d for d in _WEEK if d != date(2026, 3, 9)]
    assert cal.sessions_behind(without_monday, date(2026, 3, 6), date(2026, 3, 9)) == 0
    assert cal.sessions_behind(without_monday, date(2026, 3, 6), date(2026, 3, 10)) == 1
