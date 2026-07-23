"""EmaCross execution-timing config: same_day_fill is independent of intraday.

Three configurations matter:
  * daily-close + next-session fill (default) — the original behavior.
  * intraday-cross + same-day fill (intraday=True) — earlier but admits fakeouts.
  * daily-close confirmation + same-day fill — removes the +1-session lag WITHOUT
    the intraday fakeouts (same_day_fill=True, intraday=False).
"""

from __future__ import annotations

import pytest

from atlas.portfolio.strategies import EmaCross

pytestmark = pytest.mark.unit


def test_default_is_daily_close_next_session() -> None:
    s = EmaCross(13, 34)
    assert s.intraday is False
    assert s.same_day_fill is False
    assert s.needs_ohlc is False


def test_intraday_implies_same_day_fill_and_ohlc() -> None:
    s = EmaCross(13, 34, intraday=True)
    assert s.same_day_fill is True
    assert s.needs_ohlc is True


def test_same_day_fill_without_intraday_detection() -> None:
    # confirmation-based detection (no OHLC), but fill on the confirmation close.
    s = EmaCross(13, 34, same_day_fill=True)
    assert s.intraday is False
    assert s.needs_ohlc is False
    assert s.same_day_fill is True
