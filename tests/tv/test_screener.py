# tests/tv/test_screener.py
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from atlas.tv.screener import (  # type: ignore[import]
    _label,
    _resolve_instrument_ids,
    fetch_and_upsert_all,
)


def _mock_engine(rows: list[dict]):
    """Return a fake engine whose execute returns rows."""
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value.mappings.return_value.all.return_value = rows
    engine = MagicMock()
    engine.connect.return_value = conn
    return engine


def test_resolve_instrument_ids_maps_symbol_to_uuid():
    engine = _mock_engine(
        [
            {"symbol": "RELIANCE", "instrument_id": "uuid-1"},
            {"symbol": "TCS", "instrument_id": "uuid-2"},
        ]
    )
    result = _resolve_instrument_ids(["RELIANCE", "TCS"], engine)
    assert result["RELIANCE"] == "uuid-1"
    assert result["TCS"] == "uuid-2"


def test_fetch_and_upsert_all_calls_upsert(monkeypatch):
    fake_df = pd.DataFrame(
        [
            {
                "ticker": "RELIANCE",
                "Recommend.All": 0.5,
                "RSI": 55.0,
                "close": 2800.0,
                "MACD.macd": 10.0,
                "EMA20": 2750.0,
                "EMA50": 2700.0,
                "EMA200": 2600.0,
                "ATR": 40.0,
                "volume": 1_000_000,
                "average_volume_10d_calc": 900_000,
                "High.All": 3000.0,
                "Low.All": 2400.0,
                "Recommend.MA": 0.6,
                "Recommend.Other": 0.4,
            }
        ]
    )
    monkeypatch.setattr("atlas.tv.screener._fetch_tv_batch", lambda _: fake_df)
    engine = _mock_engine([{"symbol": "RELIANCE", "instrument_id": "uuid-1"}])
    with patch("atlas.tv.screener._upsert_rows") as mock_upsert:
        fetch_and_upsert_all(engine=engine)
    mock_upsert.assert_called_once()


@pytest.mark.parametrize(
    "score,expected",
    [
        (0.5, "STRONG_BUY"),
        (0.1, "BUY"),
        (0.0, "NEUTRAL"),
        (-0.09, "NEUTRAL"),
        (-0.1, "SELL"),
        (-0.49, "SELL"),
        (-0.5, "STRONG_SELL"),
        (-0.51, "STRONG_SELL"),
        (None, None),
        (float("nan"), None),
    ],
)
def test_label_boundary_values(score: float | None, expected: str | None) -> None:
    assert _label(score) == expected


def test_fundamental_columns_present_in_upsert_row(monkeypatch):
    """All 5 fundamental keys must appear in the row dict passed to _upsert_rows."""
    fake_df = pd.DataFrame(
        [
            {
                "ticker": "RELIANCE",
                "Recommend.All": 0.5,
                "RSI": 55.0,
                "close": 2800.0,
                "MACD.macd": 10.0,
                "EMA20": 2750.0,
                "EMA50": 2700.0,
                "EMA200": 2600.0,
                "ATR": 40.0,
                "volume": 1_000_000,
                "average_volume_10d_calc": 900_000,
                "High.All": 3000.0,
                "Low.All": 2400.0,
                "Recommend.MA": 0.6,
                "Recommend.Other": 0.4,
                "price_earnings_ttm": 22.5,
                "price_sales_current": 3.1,
                "price_book_fbs": 2.8,
                "debt_to_equity": 0.45,
                "return_on_equity": 0.18,
            }
        ]
    )
    monkeypatch.setattr("atlas.tv.screener._fetch_tv_batch", lambda _: fake_df)
    engine = _mock_engine([{"symbol": "RELIANCE", "instrument_id": "uuid-1"}])

    captured: list[dict] = []

    def capture_upsert(rows: list[dict], eng) -> None:
        captured.extend(rows)

    with patch("atlas.tv.screener._upsert_rows", side_effect=capture_upsert):
        fetch_and_upsert_all(engine=engine)

    assert len(captured) == 1
    row = captured[0]
    assert "pe_ttm" in row
    assert "ps_current" in row
    assert "pb_fbs" in row
    assert "debt_to_equity" in row
    assert "roe" in row
    assert row["pe_ttm"] == 22.5
    assert row["roe"] == 0.18
