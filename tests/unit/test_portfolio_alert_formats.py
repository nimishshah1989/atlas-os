"""Three-stage Telegram formats for the crossover books (spec §E).

The FM's rule is that he hears about a crossover THREE times, not once after the fill:

    provisional -> the 5-min feed breached the level. Explicitly not a trade.
    confirmed   -> the close (buys) or the 15:15 quote (sells) held it. It will execute.
    booked      -> it executed, at this price.

Every message names its book first. Twin books alert on the same symbol with opposite
verdicts on the same day, and without the book name that reads as a contradiction
rather than as two rules disagreeing — which is the entire point of running both.

Prices below are real MRPL records (rule #0): P* 163.88 on 2026-07-16, the 17th's
confirming close 173.33, the 20th's open 172.00.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from atlas.portfolio.alerts import booked, confirmed, provisional

pytestmark = pytest.mark.unit

BOOK = "EMA 13/34 · Deathcross Close"


def test_provisional_buy_says_plainly_that_it_is_not_a_trade() -> None:
    m = provisional(
        book=BOOK, symbol="MRPL", side="buy", level=Decimal("163.88"), quote=Decimal("165.10")
    )
    assert m.startswith("🟡")
    assert BOOK in m.splitlines()[0]
    assert "MRPL" in m and "163.88" in m
    # the single most important word in the whole message
    assert "not a trade" in m.lower()


def test_confirmed_buy_says_when_and_at_what_it_will_execute() -> None:
    m = confirmed(
        book=BOOK, symbol="MRPL", side="buy", level=Decimal("163.88"), quote=Decimal("173.33")
    )
    assert m.startswith("🟢")
    assert "next open" in m.lower()
    assert "173.33" in m


def test_confirmed_sell_names_the_1515_lock_and_todays_close() -> None:
    m = confirmed(
        book=BOOK, symbol="MRPL", side="sell", level=Decimal("167.17"), quote=Decimal("162.29")
    )
    assert m.startswith("🔴")
    assert "15:15" in m
    assert "today" in m.lower() and "close" in m.lower()


def test_booked_carries_the_fill_and_the_reason() -> None:
    m = booked(
        book=BOOK,
        trade={
            "symbol": "MRPL",
            "side": "buy",
            "qty": Decimal("476"),
            "price": Decimal("172.00"),
            "trade_date": date(2026, 7, 20),
            "rationale": "EMA13 crossed above EMA34; the close confirmed it. Conviction 6.8.",
        },
    )
    assert m.startswith("✅")
    assert "476" in m and "172.00" in m and "2026-07-20" in m
    assert "Conviction 6.8" in m  # the decision trail rides along


def test_whole_number_quantities_do_not_render_a_decimal_tail() -> None:
    m = booked(
        book=BOOK,
        trade={
            "symbol": "MRPL",
            "side": "buy",
            "qty": Decimal("476"),
            "price": Decimal("172.00"),
            "trade_date": date(2026, 7, 20),
            "rationale": None,
        },
    )
    assert "476 @" in m
    assert "476.0" not in m


def test_the_twin_books_are_distinguishable_on_the_same_symbol_and_day() -> None:
    a = confirmed(
        book="EMA 13/34 · Deathcross Close",
        symbol="MRPL",
        side="sell",
        level=Decimal("121.22"),
        quote=Decimal("120.40"),
    )
    b = confirmed(
        book="EMA 13/34 · EMA13 Close",
        symbol="MRPL",
        side="sell",
        level=Decimal("167.17"),
        quote=Decimal("162.29"),
    )
    assert a.splitlines()[0] != b.splitlines()[0]
    assert "Deathcross" in a and "EMA13 Close" in b
