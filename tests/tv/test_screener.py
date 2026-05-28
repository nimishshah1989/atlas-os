# tests/tv/test_screener.py
from unittest.mock import MagicMock, patch

import pandas as pd

from atlas.tv.screener import _resolve_instrument_ids, fetch_and_upsert_all


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
    monkeypatch.setattr("atlas.tv.screener._fetch_tv_batch", lambda symbols: fake_df)
    engine = _mock_engine([{"symbol": "RELIANCE", "instrument_id": "uuid-1"}])
    with patch("atlas.tv.screener._upsert_rows") as mock_upsert:
        fetch_and_upsert_all(engine=engine)
    mock_upsert.assert_called_once()
