#!/usr/bin/env python3
"""NSE trading calendar: holiday and early-close detection.

Usage as a script:
    python scripts/trading_calendar.py
    Exits 0 if today (IST) is a trading day, exits 1 if not.
    Prints "TRADING_DAY" or "HOLIDAY" to stdout.
    This allows systemd ExecStartPre / ExecCondition to gate service startup.

TODO: Update NSE_HOLIDAYS each January with the new NSE circular for that year.
      NSE publishes the holiday list at: https://www.nseindia.com/resources/exchange-communication-holidays
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root on sys.path
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# IST timezone constant (UTC+5:30)
# ---------------------------------------------------------------------------
_IST = timezone(timedelta(hours=5, minutes=30))

# ---------------------------------------------------------------------------
# NSE 2026 trading holidays (published by NSE at start of calendar year).
# TODO: Update this set every January from the official NSE circular.
# Approximate dates for Diwali 2026 (Oct 26 / Nov 5) — confirm from NSE circular
# when published; adjust if NSE announces different muhurat timing.
# ---------------------------------------------------------------------------
NSE_HOLIDAYS: frozenset[str] = frozenset(
    [
        "2026-01-26",  # Republic Day
        "2026-02-26",  # Mahashivratri
        "2026-03-25",  # Holi
        "2026-04-02",  # Ram Navami
        "2026-04-03",  # Good Friday
        "2026-04-14",  # Dr. Ambedkar Jayanti
        "2026-05-01",  # Maharashtra Day
        "2026-08-15",  # Independence Day
        "2026-10-02",  # Gandhi Jayanti
        "2026-10-26",  # Diwali Laxmi Pujan (approximate — confirm from NSE circular)
        "2026-11-05",  # Diwali Balipratipada (approximate — confirm from NSE circular)
        "2026-11-25",  # Gurunanak Jayanti
        "2026-12-25",  # Christmas
    ]
)


def is_trading_day(check_date: date | None = None) -> bool:
    """Return True if ``check_date`` is an NSE trading day.

    Defaults to today in IST timezone when ``check_date`` is None.

    Args:
        check_date: The date to check. Defaults to today in IST.

    Returns:
        True if the market trades on this day, False otherwise.

    Fail-open per wiki pattern: if a holiday is accidentally omitted from
    NSE_HOLIDAYS the function returns True (ingest runs) rather than False
    (silent data gap). Duplicate ticks are handled by ON CONFLICT upsert.
    """
    if check_date is None:
        check_date = datetime.now(tz=_IST).date()

    # Saturday = 5, Sunday = 6
    if check_date.weekday() >= 5:
        return False

    date_str = check_date.strftime("%Y-%m-%d")
    return date_str not in NSE_HOLIDAYS


def market_open_time() -> datetime:
    """Return 09:15 IST today as a tz-aware datetime.

    Returns:
        A tz-aware datetime for 09:15:00 IST on today's date.
    """
    today = datetime.now(tz=_IST).date()
    return datetime(today.year, today.month, today.day, 9, 15, 0, tzinfo=_IST)


def market_close_time() -> datetime:
    """Return 15:30 IST today as a tz-aware datetime.

    Returns:
        A tz-aware datetime for 15:30:00 IST on today's date.
    """
    today = datetime.now(tz=_IST).date()
    return datetime(today.year, today.month, today.day, 15, 30, 0, tzinfo=_IST)


def main() -> None:
    """Print TRADING_DAY or HOLIDAY and exit with the corresponding code.

    Exit 0 = trading day (systemd ExecStartPre succeeds, service starts).
    Exit 1 = holiday/weekend (systemd ExecStartPre fails, service does not start).
    """
    if is_trading_day():
        print("TRADING_DAY")
        sys.exit(0)
    else:
        print("HOLIDAY")
        sys.exit(1)


if __name__ == "__main__":
    main()
