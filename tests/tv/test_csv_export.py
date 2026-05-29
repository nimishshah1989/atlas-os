# tests/tv/test_csv_export.py
import csv
import io
from decimal import Decimal
from unittest.mock import MagicMock

from atlas.tv.csv_export import export_portfolio_csv  # type: ignore[import]


def _mock_engine(lots: list[dict]):
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.all.return_value = lots
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    return engine


_LOTS = [
    {
        "symbol": "RELIANCE",
        "quantity": Decimal("10"),
        "entry_price": Decimal("2800.00"),
        "entry_date": "2024-09-17",
        "exit_price": Decimal("3000.00"),
        "exit_date": "2024-09-18",
    },
    {
        "symbol": "TCS",
        "quantity": Decimal("5"),
        "entry_price": Decimal("3500.00"),
        "entry_date": "2024-10-01",
        "exit_price": None,
        "exit_date": None,
    },
]


def test_export_returns_bytes():
    result = export_portfolio_csv("pid-1", _mock_engine(_LOTS))
    assert isinstance(result, bytes)


def test_export_has_correct_header():
    csv_text = export_portfolio_csv("pid-1", _mock_engine(_LOTS)).decode("utf-8")
    reader = csv.DictReader(io.StringIO(csv_text))
    assert reader.fieldnames == [
        "Symbol",
        "Side",
        "Qty",
        "Fill Price",
        "Commission",
        "Closing Time",
    ]


def test_export_closed_lot_generates_buy_and_sell():
    csv_text = export_portfolio_csv("pid-1", _mock_engine([_LOTS[0]])).decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(rows) == 2
    buy = next(r for r in rows if r["Side"] == "Buy")
    sell = next(r for r in rows if r["Side"] == "Sell")
    assert buy["Symbol"] == "NSE:RELIANCE"
    assert buy["Fill Price"] == "2800.00"
    assert sell["Fill Price"] == "3000.00"


def test_export_open_lot_generates_only_buy():
    csv_text = export_portfolio_csv("pid-1", _mock_engine([_LOTS[1]])).decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(rows) == 1
    assert rows[0]["Side"] == "Buy"
    assert rows[0]["Symbol"] == "NSE:TCS"
    assert rows[0]["Closing Time"] == "2024-10-01 0:00:00"
