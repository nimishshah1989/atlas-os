"""Pure CPP-row mapping.

RULE #0: every constant below is a REAL row read from the live CPP database
(jip-data-engine ... /client_portal) on 2026-07-31. BJ53 and JR100PASS holdings
and a BJ53 SELL transaction, verbatim. Nothing here is invented.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas.maal.source import (
    CODE_BY_CLIENT_CODE,
    is_cash,
    split_cash_and_positions,
    trade_from_txn,
    weight_pct,
)

pytestmark = pytest.mark.unit

# Real BJ53 holdings, 2026-07-31 (symbol, isin, asset_class, quantity, avg_cost).
BJ53_HOLDINGS = [
    ("GOLDBEES", "INF204KB17I5", "EQUITY", Decimal("4334"), Decimal("94.5962")),
    ("NIFTYBEES", "INF204KB14I2", "EQUITY", Decimal("1467"), Decimal("273.0900")),
    ("CDSL", "INE736A01011", "EQUITY", Decimal("304"), Decimal("1277.3368")),
    ("JINDALSAW", "INE324A01032", "EQUITY", Decimal("1572"), Decimal("273.6910")),
    ("DELHIVERY", "INE148O01028", "EQUITY", Decimal("808"), Decimal("506.2200")),
    ("HDFCSML250", "INF179KC1FB2", "EQUITY", Decimal("1667"), Decimal("180.5100")),
    ("SILVERBEES", "INF204KC1402", "EQUITY", Decimal("1181"), Decimal("218.1817")),
    ("JSFB", "INE953L01027", "EQUITY", Decimal("408"), Decimal("534.4294")),
    ("DIVISLAB", "INE361B01024", "EQUITY", Decimal("29"), Decimal("7008.5000")),
    ("ATHERENERG", "INE0LEZ01016", "EQUITY", Decimal("172"), Decimal("1051.5524")),
]

# Real JR100PASS liquid-ETF row, 2026-07-31 — CPP already tags it CASH.
JR100PASS_LIQUIDCASE = (
    "LIQUIDCASE",
    "INF0R8F01034",
    "CASH",
    Decimal("1"),
    Decimal("1000"),
)

# Real BJ53 SELL, 2026-07-28: 420 INDUSINDBK at 992.00 net / 984.9938 all-in.
BJ53_SELL = {
    "id": 1,
    "txn_date": "2026-07-28",
    "txn_type": "SELL",
    "symbol": "INDUSINDBK",
    "isin": "INE095A01012",
    "quantity": Decimal("420"),
    "price": Decimal("992.0000"),
    "cost_rate": Decimal("984.9938"),
    "amount": Decimal("413697.40"),
}


def test_liquid_etf_counts_as_cash() -> None:
    assert is_cash(JR100PASS_LIQUIDCASE[2]) is True


def test_equity_etf_is_not_cash() -> None:
    # GOLDBEES is asset-class exposure, not cash — it must stay a position.
    assert is_cash("EQUITY") is False


def test_split_puts_liquid_in_cash_and_the_rest_in_positions() -> None:
    rows = [
        {"symbol": s, "isin": i, "asset_class": a, "quantity": q, "avg_cost": c}
        for s, i, a, q, c in [*BJ53_HOLDINGS, JR100PASS_LIQUIDCASE]
    ]
    positions, cash_rows = split_cash_and_positions(rows)
    assert len(positions) == 10
    assert len(cash_rows) == 1
    assert cash_rows[0]["symbol"] == "LIQUIDCASE"
    assert all(p["asset_class"] == "EQUITY" for p in positions)


def test_weight_is_percent_of_total_including_cash() -> None:
    # 33.43L invested + 6.57L cash = 40L total. A 5L position is 12.5%, not 14.96%.
    assert weight_pct(Decimal("500000"), Decimal("4000000")) == Decimal("12.5000")


def test_weight_of_zero_total_is_zero_not_a_crash() -> None:
    assert weight_pct(Decimal("500000"), Decimal("0")) == Decimal("0")


def test_client_codes_map_to_maal_codes() -> None:
    assert CODE_BY_CLIENT_CODE == {
        "BJ53": "leaders",
        "BJ53IND": "ind11",
        "JR100PASS": "passive",
    }


def test_instrument_key_is_the_uuid_and_symbol_is_separate() -> None:
    """REGRESSION. portfolio_trades.instrument_key holds the instrument_master UUID.

    Found 2026-07-31 against the live board: writing a readable "stock:CDSL" key made
    getPortfolioDetail's `instrument_id = ANY(...::uuid[])` throw, so every MaaL detail
    page returned 404 while the list page looked perfectly fine. The engine's own rows
    carry bare UUIDs (e.g. 001a1ce4-cc25-4639-9795-528a67d97c34); MaaL must match.
    """
    iid = "001a1ce4-cc25-4639-9795-528a67d97c34"
    trade = trade_from_txn(BJ53_SELL, instrument_key=iid, asset_class="stock", symbol="INDUSINDBK")
    assert trade is not None
    assert trade["instrument_key"] == iid
    assert ":" not in trade["instrument_key"]
    assert trade["symbol"] == "INDUSINDBK"


def test_sell_trade_uses_net_price_and_carries_source_id() -> None:
    trade = trade_from_txn(
        BJ53_SELL,
        instrument_key="001a1ce4-cc25-4639-9795-528a67d97c34",
        asset_class="stock",
        symbol="INDUSINDBK",
    )
    assert trade is not None
    assert trade["side"] == "sell"
    assert trade["price"] == Decimal("992.0000")  # net rate, NOT the all-in cost_rate
    assert trade["cost"] == Decimal("984.9938")  # all-in kept separately
    assert trade["qty"] == Decimal("420")
    assert trade["value"] == Decimal("413697.40")
    assert trade["reason"] == "manual"
    assert trade["source_txn_id"] == 1


def test_corpus_in_is_a_buy_marked_inception() -> None:
    """CORPUS_IN opens a position, so it belongs in the trade log.

    BJ53's whole opening book arrived this way on 2020-09-28 (RELIANCE 15 @ 1730.75,
    WIPRO 160 @ 298.45, ...). Omitting it would render those names as sold in Oct-2020
    with no record of ever arriving. reason='inception' already exists in the
    portfolio_trades CHECK for exactly this case.
    """
    row = dict(BJ53_SELL, txn_type="CORPUS_IN")
    trade = trade_from_txn(
        row,
        instrument_key="00000000-0000-4000-8000-000000000001",
        asset_class="stock",
        symbol="RELIANCE",
    )
    assert trade is not None
    assert trade["side"] == "buy"
    assert trade["reason"] == "inception"


def test_bonus_rows_stay_out_of_the_trade_log() -> None:
    """Bonus shares arrive at price 0 and portfolio_trades has CHECK (price > 0).

    They cannot be stored there at all. FIFO still opens a zero-cost lot for them
    (atlas.maal.fifo), so realized P&L stays correct — only the log omits them.
    Two rows on BJ53 as of 2026-07-31, both at price exactly 0.0000.
    """
    row = dict(BJ53_SELL, txn_type="BONUS")
    assert (
        trade_from_txn(
            row,
            instrument_key="00000000-0000-4000-8000-000000000001",
            asset_class="stock",
            symbol="X",
        )
        is None
    )


def test_ordinary_buys_and_sells_are_marked_manual() -> None:
    # Only a corpus transfer is 'inception'; desk activity stays 'manual'.
    for kind in ("BUY", "SELL"):
        row = dict(BJ53_SELL, txn_type=kind)
        trade = trade_from_txn(
            row,
            instrument_key="00000000-0000-4000-8000-000000000001",
            asset_class="stock",
            symbol="X",
        )
        assert trade is not None
        assert trade["reason"] == "manual"
