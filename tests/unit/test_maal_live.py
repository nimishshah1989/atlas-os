"""Live mark-to-market for the MaaL books.

RULE #0: quantities and costs below are BJ53's REAL positions, read from the live CPP
database on 2026-07-31 — 304 CDSL at an average cost of 1277.3368, and 4334 GOLDBEES
at 94.5962.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas.maal.live import live_pnl

pytestmark = pytest.mark.unit

CDSL = {"isin": "INE736A01011", "quantity": Decimal("304"), "avg_cost": Decimal("1277.3368")}
GOLDBEES = {"isin": "INF204KB17I5", "quantity": Decimal("4334"), "avg_cost": Decimal("94.5962")}


def test_unrealized_pnl_against_a_real_position() -> None:
    # (1400 - 1277.3368) * 304 = 37,289.6128
    out = live_pnl([CDSL], {"INE736A01011": Decimal("1400")})
    assert out["market_value"] == Decimal("425600.00")
    assert out["unrealized"] == Decimal("37289.61")
    assert out["unquoted"] == []


def test_a_loss_is_reported_as_a_loss() -> None:
    # (1200 - 1277.3368) * 304 = -23,510.3872
    out = live_pnl([CDSL], {"INE736A01011": Decimal("1200")})
    assert out["unrealized"] == Decimal("-23510.39")


def test_positions_aggregate_across_the_book() -> None:
    out = live_pnl(
        [CDSL, GOLDBEES],
        {"INE736A01011": Decimal("1400"), "INF204KB17I5": Decimal("100")},
    )
    # CDSL 425,600.00 + GOLDBEES 4334 * 100 = 433,400.00
    assert out["market_value"] == Decimal("859000.00")
    assert out["cost"] == Decimal("798290.32")  # 388,310.39 + 409,979.93
    assert out["unrealized"] == out["market_value"] - out["cost"]


def test_a_position_without_a_quote_is_reported_not_dropped() -> None:
    """A missing mark on ONE name would otherwise quietly understate the whole book.

    Silently valuing it at zero, or omitting it, both produce a plausible number that
    is wrong — the worst kind for a figure the desk reads mid-session.
    """
    out = live_pnl([CDSL, GOLDBEES], {"INE736A01011": Decimal("1400")})
    assert out["unquoted"] == ["INF204KB17I5"]
    # Only the quoted position contributes; the gap is reported, never guessed.
    assert out["market_value"] == Decimal("425600.00")


def test_no_quotes_at_all_yields_zero_and_names_everything() -> None:
    out = live_pnl([CDSL, GOLDBEES], {})
    assert out["market_value"] == Decimal("0.00")
    assert out["unrealized"] == Decimal("0.00")
    assert len(out["unquoted"]) == 2


def test_an_empty_book_does_not_crash() -> None:
    out = live_pnl([], {"INE736A01011": Decimal("1400")})
    assert out["market_value"] == Decimal("0.00")
    assert out["unquoted"] == []
