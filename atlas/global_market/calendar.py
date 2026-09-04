"""Trading-session arithmetic for the US platform. Pure — no I/O, no market data.

A session EXISTS iff the anchor (SPY) has a bar in ``atlas_global.ohlcv_daily`` —
membership-by-presence, exactly as India defines its calendar by NIFTY 50 presence.
Sessions are never derived from weekday arithmetic or a holiday table: a day the feed did
not deliver is not a day we scored, and a day it did deliver is a session even if some
calendar says otherwise. Callers run ``select distinct date … where instrument_id = SPY``
and hand the resulting dates to the helpers here.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

NEW_YORK = "America/New_York"


def eod_cutoff(now: datetime, close_hour: int = 17, tz: str = NEW_YORK) -> date:
    """The last COMPLETE trading day as of ``now`` (tz-aware), in the market's local time.

    Mirrors India's ``_db.eod_cutoff`` (16:00 IST): once the local clock reaches
    ``close_hour`` (17:00 ET = one hour after the 16:00 close, the finalisation buffer)
    today is a candidate EOD; before that, today is still live and the cutoff is yesterday.
    The result is a calendar date — callers anchor to the latest SESSION on or before it
    with :func:`latest_session_on_or_before`, which is what skips weekends and holidays.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("eod_cutoff: `now` must be tz-aware (rule #5)")
    local = now.astimezone(ZoneInfo(tz))
    cutoff = local.date()
    if local.hour < close_hour:
        cutoff -= timedelta(days=1)
    return cutoff


def sessions(dates: Iterable[date]) -> list[date]:
    """Sorted, de-duplicated session list from whatever the SPY query returned."""
    return sorted(set(dates))


def latest_session_on_or_before(sessions: Sequence[date], d: date) -> date | None:
    """The newest session ``<= d``, or ``None`` when ``d`` precedes the first session.

    ``sessions`` must be ascending (as :func:`sessions` returns them).
    """
    i = bisect.bisect_right(sessions, d)
    return sessions[i - 1] if i else None


def sessions_behind(sessions: Sequence[date], mx: date, eod: date) -> int:
    """How many anchor sessions fall in ``(mx, eod]`` — the staleness of a table whose
    ``max(date)`` is ``mx`` relative to the EOD, counted in SESSIONS, not calendar days.

    A table at ``mx >= eod`` is 0 behind. A holiday between ``mx`` and ``eod`` is not a
    session, so it does not count (India's ``busday_count`` counted weekday holidays and
    made every post-holiday run read one day staler than it was). ``mx`` itself need not
    be a session. ``sessions`` must be ascending.
    """
    if mx >= eod:
        return 0
    lo = bisect.bisect_right(sessions, mx)
    hi = bisect.bisect_right(sessions, eod)
    return hi - lo
