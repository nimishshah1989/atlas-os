"""Real-data tests for the NSE trading-calendar helpers (RULE #0 compliant).

These tests assert against REAL rows in atlas_foundation.index_prices (the
NIFTY 50 session calendar) — never synthetic inputs. They prove the helpers are
MEMBERSHIP-based (a date is a trading day iff a real session row exists), not
weekday-based. The two load-bearing cases:

  * 2026-02-01 (Sunday) — the NSE Budget-day SPECIAL session — must be a trading
    day even though it is a weekend.
  * 2026-01-26 (Monday) — Republic Day — must NOT be a trading day even though it
    is a weekday.

A weekday-arithmetic implementation would get BOTH of these wrong; only reading
the real calendar gets them right.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import text

from atlas.db import get_engine
from atlas.lenses.data.adapters import (
    _NSE_CAL_INDEX,
    is_trading_day,
    latest_trading_day,
)


@pytest.fixture(scope="module")
def engine():
    eng = get_engine()
    # Skip (don't fail) if the calendar source is unreachable/empty in this env.
    with eng.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM atlas_foundation.index_prices WHERE index_code = :idx"),
            {"idx": _NSE_CAL_INDEX},
        ).scalar()
    if not n:
        pytest.skip(f"no {_NSE_CAL_INDEX} calendar rows available")
    return eng


def _row_exists(eng, d: date) -> bool:
    """Ground truth read straight from the raw calendar table."""
    with eng.connect() as conn:
        return bool(
            conn.execute(
                text(
                    "SELECT EXISTS(SELECT 1 FROM atlas_foundation.index_prices "
                    "WHERE index_code = :idx AND date = :d)"
                ),
                {"idx": _NSE_CAL_INDEX, "d": d},
            ).scalar()
        )


class TestIsTradingDay:
    """is_trading_day must equal raw calendar membership — no weekday logic."""

    def test_budget_sunday_is_a_session(self, engine) -> None:
        # CRITICAL: 2026-02-01 is a Sunday but a real NSE Budget-day session.
        assert _row_exists(engine, date(2026, 2, 1)) is True  # ground truth
        assert is_trading_day(engine, date(2026, 2, 1)) is True

    def test_republic_day_is_not_a_session(self, engine) -> None:
        # CRITICAL: 2026-01-26 is a Monday (weekday) but an NSE holiday.
        assert _row_exists(engine, date(2026, 1, 26)) is False  # ground truth
        assert is_trading_day(engine, date(2026, 1, 26)) is False

    def test_regular_session(self, engine) -> None:
        assert is_trading_day(engine, date(2026, 6, 19)) is True

    def test_weekend_is_not_a_session(self, engine) -> None:
        assert is_trading_day(engine, date(2026, 6, 20)) is False  # Saturday
        assert is_trading_day(engine, date(2026, 6, 21)) is False  # Sunday

    def test_helper_matches_raw_membership_across_a_window(self, engine) -> None:
        # Property: over a real date range, the helper agrees with the raw table
        # on every single day (the helper IS membership, nothing else).
        base = date(2026, 5, 11)
        for offset in range(40):
            d = base + timedelta(days=offset)
            assert is_trading_day(engine, d) == _row_exists(engine, d), d


class TestLatestTradingDay:
    """latest_trading_day snaps a reference date back to the last real session."""

    def test_sunday_snaps_to_friday(self, engine) -> None:
        assert latest_trading_day(engine, date(2026, 6, 21)) == date(2026, 6, 19)

    def test_saturday_snaps_to_friday(self, engine) -> None:
        assert latest_trading_day(engine, date(2026, 6, 20)) == date(2026, 6, 19)

    def test_idempotent_on_a_session(self, engine) -> None:
        assert latest_trading_day(engine, date(2026, 6, 19)) == date(2026, 6, 19)

    def test_budget_sunday_is_its_own_latest(self, engine) -> None:
        # The Budget Sunday is a session, so it resolves to itself, not the Friday.
        assert latest_trading_day(engine, date(2026, 2, 1)) == date(2026, 2, 1)

    def test_result_is_always_a_real_session_on_or_before_ref(self, engine) -> None:
        # Property over real reference dates: the resolved day is itself a real
        # session and never after the reference.
        for ref in (date(2026, 1, 27), date(2026, 3, 26), date(2026, 6, 21)):
            d = latest_trading_day(engine, ref)
            assert d <= ref
            assert is_trading_day(engine, d) is True

    def test_raises_before_calendar_start(self, engine) -> None:
        with pytest.raises(ValueError):
            latest_trading_day(engine, date(1990, 1, 1))
