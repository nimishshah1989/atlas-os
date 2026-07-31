"""The BOOKED Telegram message for the EMA-cross portfolios (spec §E).

Anchored on the REAL MRPL 13/34 live trade (rule #0): BUY 476 @ ₹174.49 on 2026-07-20,
confirmed by the EMA13>EMA34 golden cross at the 2026-07-17 close (ema_13 157.52,
ema_34 156.46 from atlas_foundation.technical_daily).

These tests previously asserted against ``format_cross_alert``, which built the "why"
by re-deriving the EMAs from the DB at message time. That function is gone. The why is
now written ONCE by the engine into ``portfolio_trades.rationale`` and the message
carries it, so the alert and the stored row can never tell different stories. The
assertions here are the same intent against the new seam: the direction of the cross,
the fill, the stop being named as a stop, and no ``None`` leaking into the FM's phone.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "foundation"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import portfolio_alerts as A  # noqa: E402  # pyright: ignore[reportMissingImports]

from atlas.portfolio import alerts  # noqa: E402

pytestmark = pytest.mark.unit

_BOOK = {
    "name": "EMA Crossover 13/34 · Deathcross Close",
    "strategy_key": "ema_cross",
    "params": {"fast": 13, "slow": 34, "notify": True},
}


def test_buy_alert_reads_as_a_golden_cross() -> None:
    msg = alerts.booked(
        book=A.book_label(_BOOK),
        trade={
            "symbol": "MRPL",
            "side": "buy",
            "qty": Decimal("476"),
            "price": Decimal("174.49"),
            "trade_date": date(2026, 7, 20),
            "rationale": (
                "EMA13 crossed above EMA34; the close at ₹173.33 confirmed it. "
                "Conviction 6.8 — ranked #1 of 1 name that crossed, 3 slots open."
            ),
        },
    )
    assert "EMA Crossover 13/34" in msg
    assert "BOUGHT" in msg
    assert "MRPL" in msg
    assert "above" in msg  # EMA13 crossed above EMA34 — carried by the rationale
    assert "174.49" in msg and "476" in msg


def test_sell_signal_reads_as_a_death_cross() -> None:
    msg = alerts.booked(
        book=A.book_label(_BOOK),
        trade={
            "symbol": "MRPL",
            "side": "sell",
            "qty": Decimal("476"),
            "price": Decimal("150.53"),
            "trade_date": date(2026, 5, 8),
            "rationale": (
                "EMA13 crossed below EMA34 intraday — price broke ₹151.30, and was "
                "still below at the 15:15 lock (close ₹150.53). Sold at that close."
            ),
        },
    )
    assert "SOLD" in msg
    assert "below" in msg
    assert "15:15" in msg


def test_sell_stop_names_the_stop_not_a_cross() -> None:
    msg = alerts.booked(
        book="Golden Cross 50/200",
        trade={
            "symbol": "GRAVITA",
            "side": "sell",
            "qty": Decimal("100"),
            "price": Decimal("1500.00"),
            "trade_date": date(2026, 6, 1),
            "rationale": (
                "Stop hit: prior close ₹1,499.00 fell below ₹1,505.00, more than 10% "
                "below entry. Sold at this session's close."
            ),
        },
    )
    assert "SOLD" in msg
    assert "stop" in msg.lower()
    # the REASON must not read as a cross. "cross" alone is no good as a check — the
    # book is literally called "Golden Cross 50/200" — so assert on the verb.
    assert "crossed" not in msg.lower()


def test_no_none_ever_reaches_the_fm() -> None:
    # A trade booked before the trail existed has rationale NULL. The message must
    # simply omit the line rather than print the word "None".
    msg = alerts.booked(
        book=A.book_label(_BOOK),
        trade={
            "symbol": "MRPL",
            "side": "sell",
            "qty": Decimal("476"),
            "price": Decimal("150.53"),
            "trade_date": date(2026, 5, 8),
            "rationale": None,
        },
    )
    assert "None" not in msg


def test_notify_is_opt_in_per_book() -> None:
    trades = pd.DataFrame(
        [
            {
                "symbol": "MRPL",
                "side": "buy",
                "qty": Decimal("476"),
                "price": Decimal("174.49"),
                "trade_date": date(2026, 7, 20),
                "rationale": "x",
            }
        ]
    )
    off = {**_BOOK, "params": {"fast": 13, "slow": 34}}
    assert A.notify_new_trades(off, trades) == 0


def test_a_non_crossover_book_never_alerts() -> None:
    trades = pd.DataFrame([{"symbol": "X", "side": "buy"}])
    assert (
        A.notify_new_trades({"strategy_key": "rank_policy", "params": {"notify": True}}, trades)
        == 0
    )
