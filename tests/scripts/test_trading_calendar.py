"""Tests for scripts/trading_calendar.py."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------


def _import_calendar():
    """Import the trading_calendar module (delayed to avoid sys.path issues)."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(  # type: ignore[attr-defined]
        "trading_calendar",
        Path(__file__).resolve().parent.parent.parent / "scripts" / "trading_calendar.py",
    )
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_cal = _import_calendar()
_IST = timezone(timedelta(hours=5, minutes=30))


# ---------------------------------------------------------------------------
# is_trading_day
# ---------------------------------------------------------------------------


class TestIsTradingDay:
    def test_weekday_not_in_holidays_returns_true(self):
        # 2026-01-05 is a Monday and not in NSE_HOLIDAYS
        assert _cal.is_trading_day(date(2026, 1, 5)) is True

    def test_saturday_returns_false(self):
        # 2026-01-03 is a Saturday
        assert _cal.is_trading_day(date(2026, 1, 3)) is False

    def test_sunday_returns_false(self):
        # 2026-01-04 is a Sunday
        assert _cal.is_trading_day(date(2026, 1, 4)) is False

    def test_republic_day_holiday_returns_false(self):
        # 2026-01-26 is Republic Day — in NSE_HOLIDAYS
        assert _cal.is_trading_day(date(2026, 1, 26)) is False

    def test_good_friday_returns_false(self):
        # 2026-04-03 is Good Friday — in NSE_HOLIDAYS
        assert _cal.is_trading_day(date(2026, 4, 3)) is False

    def test_holi_returns_false(self):
        assert _cal.is_trading_day(date(2026, 3, 25)) is False

    def test_mahashivratri_returns_false(self):
        assert _cal.is_trading_day(date(2026, 2, 26)) is False

    def test_all_nse_2026_holidays_return_false(self):
        """Every hardcoded holiday must return False."""
        for date_str in _cal.NSE_HOLIDAYS:
            y, m, d = map(int, date_str.split("-"))
            check = date(y, m, d)
            assert _cal.is_trading_day(check) is False, f"{date_str} should be a holiday"

    def test_day_before_holiday_returns_true(self):
        # 2026-01-25 is a Sunday already (already tested), but 2026-01-23 is a Friday
        assert _cal.is_trading_day(date(2026, 1, 23)) is True

    def test_default_date_uses_ist(self, monkeypatch):
        """When called with no argument, uses IST today — not necessarily UTC today."""
        fixed_ist = datetime(2026, 1, 5, 10, 0, 0, tzinfo=_IST)  # Monday

        class _FakeDatetime(datetime):
            @classmethod
            def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
                return fixed_ist

        monkeypatch.setattr(_cal, "datetime", _FakeDatetime)
        # Should be True since 2026-01-05 is a trading day
        assert _cal.is_trading_day() is True


# ---------------------------------------------------------------------------
# market_open_time / market_close_time
# ---------------------------------------------------------------------------


class TestMarketTimes:
    def test_market_open_time_is_09_15_ist(self):
        t = _cal.market_open_time()
        assert t.hour == 9
        assert t.minute == 15
        assert t.second == 0
        # Confirm IST offset
        assert t.utcoffset() == timedelta(hours=5, minutes=30)

    def test_market_close_time_is_15_30_ist(self):
        t = _cal.market_close_time()
        assert t.hour == 15
        assert t.minute == 30
        assert t.second == 0
        assert t.utcoffset() == timedelta(hours=5, minutes=30)

    def test_open_before_close(self):
        assert _cal.market_open_time() < _cal.market_close_time()

    def test_times_are_tz_aware(self):
        assert _cal.market_open_time().tzinfo is not None
        assert _cal.market_close_time().tzinfo is not None


# ---------------------------------------------------------------------------
# Script exit-code behaviour (subprocess test for __main__ block)
# ---------------------------------------------------------------------------


class TestScriptExitCode:
    def test_trading_day_exits_0(self, monkeypatch):
        """Patch is_trading_day to True, confirm exit(0) path."""
        exit_calls: list[int] = []

        def fake_exit(code: int) -> None:
            exit_calls.append(code)
            raise SystemExit(code)

        monkeypatch.setattr(_cal.sys, "exit", fake_exit)  # type: ignore[attr-defined]
        monkeypatch.setattr(_cal, "is_trading_day", lambda: True)
        with pytest.raises(SystemExit) as exc_info:
            _cal.main()
        assert exc_info.value.code == 0

    def test_holiday_exits_1(self, monkeypatch):
        """Patch is_trading_day to False, confirm exit(1) path."""
        monkeypatch.setattr(_cal, "is_trading_day", lambda: False)
        with pytest.raises(SystemExit) as exc_info:
            _cal.main()
        assert exc_info.value.code == 1
