"""FIFO lot matching.

RULE #0: the sequence below is BJ53's COMPLETE real INDUSINDBK history, read from
the live CPP database on 2026-07-31 — two buys and the sell that closed the position:

    2026-07-09  BUY   210 @ 1015.5100
    2026-07-10  BUY   210 @ 1027.5100
    2026-07-28  SELL  420 @  992.0000

Both lots are fully consumed by the sell, so the expected P&L is exact and
hand-checkable:
    (992.00 - 1015.51) * 210 = -4,937.10
    (992.00 - 1027.51) * 210 = -7,457.10
                        total = -12,394.20   (a real loss on a real trade)
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from atlas.maal.fifo import match_fifo

pytestmark = pytest.mark.unit

INDUSINDBK = [
    {
        "txn_date": dt.date(2026, 7, 9),
        "txn_type": "BUY",
        "quantity": Decimal("210"),
        "price": Decimal("1015.5100"),
    },
    {
        "txn_date": dt.date(2026, 7, 10),
        "txn_type": "BUY",
        "quantity": Decimal("210"),
        "price": Decimal("1027.5100"),
    },
    {
        "txn_date": dt.date(2026, 7, 28),
        "txn_type": "SELL",
        "quantity": Decimal("420"),
        "price": Decimal("992.0000"),
    },
]


def test_realized_pnl_matches_the_hand_computed_loss() -> None:
    sells = match_fifo(INDUSINDBK)
    assert len(sells) == 1
    assert sells[0]["realized_pnl"] == Decimal("-12394.20")


def test_holding_days_uses_the_oldest_matched_lot() -> None:
    # Oldest lot bought 2026-07-09, sold 2026-07-28 -> 19 days.
    assert match_fifo(INDUSINDBK)[0]["holding_days"] == 19


def test_short_holding_is_stcg() -> None:
    assert match_fifo(INDUSINDBK)[0]["tax_bucket"] == "STCG"


def test_partial_sell_consumes_only_the_oldest_lot() -> None:
    # Same real buys, but sell only 210: matches the 1015.51 lot alone.
    partial = [*INDUSINDBK[:2], dict(INDUSINDBK[2], quantity=Decimal("210"))]
    assert match_fifo(partial)[0]["realized_pnl"] == Decimal("-4937.10")


def test_bonus_shares_enter_at_zero_cost() -> None:
    # BJ53 has 2 real BONUS rows. A bonus lot must not be priced like a buy, or
    # the eventual sell understates the gain by the full market value.
    seq = [
        {
            "txn_date": dt.date(2026, 7, 9),
            "txn_type": "BUY",
            "quantity": Decimal("100"),
            "price": Decimal("100"),
        },
        {
            "txn_date": dt.date(2026, 7, 10),
            "txn_type": "BONUS",
            "quantity": Decimal("100"),
            "price": Decimal("0"),
        },
        {
            "txn_date": dt.date(2026, 7, 28),
            "txn_type": "SELL",
            "quantity": Decimal("200"),
            "price": Decimal("150"),
        },
    ]
    # (150-100)*100 + (150-0)*100 = 5,000 + 15,000
    assert match_fifo(seq)[0]["realized_pnl"] == Decimal("20000.00")


def test_corpus_in_opens_a_lot_at_its_stated_cost() -> None:
    """REGRESSION. CORPUS_IN is a securities transfer-IN, not cash.

    Found 2026-07-31 by running FIFO over the real history: 42 of 991 sells came
    back unmatched, and every one traced to an instrument with CORPUS_IN rows.
    Verified across all three books — all 17 CORPUS_IN rows carry a real quantity
    AND price, and none lacks either. Treating them as cash left BJ53's opening
    book (9 instruments transferred in at inception 2020-09-28) and JR100PASS's
    2024-05-15 corpus with no cost basis, so their sells booked no P&L at all.

    The sequence below is BJ53's REAL first two RELIANCE rows:
        2020-09-28  CORPUS_IN  15 @ 1730.75
        2020-10-19  SELL       15 @ 2222.89
    (2222.89 - 1730.75) * 15 = 7,382.10
    """
    seq = [
        {
            "txn_date": dt.date(2020, 9, 28),
            "txn_type": "CORPUS_IN",
            "quantity": Decimal("15"),
            "price": Decimal("1730.7500"),
        },
        {
            "txn_date": dt.date(2020, 10, 19),
            "txn_type": "SELL",
            "quantity": Decimal("15"),
            "price": Decimal("2222.8900"),
        },
    ]
    out = match_fifo(seq)
    assert out[0]["realized_pnl"] == Decimal("7382.10")
    assert out[0]["unmatched_qty"] == Decimal("0")
    assert out[0]["holding_days"] == 21
    assert out[0]["tax_bucket"] == "STCG"


def test_sell_with_no_matching_buy_is_reported_not_guessed() -> None:
    # The 16 pre-format BJ53 rows have no ISIN, so their buys are invisible here.
    # An unmatched sell must surface, never silently book the full proceeds as gain.
    seq = [
        {
            "txn_date": dt.date(2026, 7, 28),
            "txn_type": "SELL",
            "quantity": Decimal("10"),
            "price": Decimal("100"),
        }
    ]
    out = match_fifo(seq)
    assert out[0]["realized_pnl"] is None
    assert out[0]["unmatched_qty"] == Decimal("10")
