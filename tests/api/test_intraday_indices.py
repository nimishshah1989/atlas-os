"""Tests for the /indices endpoint and INDEX_TOKENS constant (SP10 multi-index strip).

All DB calls are mocked. No live database required.
"""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")
os.environ.setdefault("ATLAS_INTERNAL_SECRET", "test-service-secret")

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from atlas.api import app
from fastapi.testclient import TestClient

from atlas.config import Config

_SERVICE_HEADERS = {"Authorization": "Bearer test-service-secret"}

_SAMPLE_BAR_TIME = datetime(2026, 5, 12, 9, 30, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def client() -> TestClient:
    Config.AUTH_DISABLED = True
    Config.ATLAS_INTERNAL_SECRET = "test-service-secret"  # noqa: S105
    return TestClient(app, headers=_SERVICE_HEADERS)


def _mock_engine_with_rows(rows: list[tuple]) -> MagicMock:
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_result = MagicMock()
    mock_result.fetchall.return_value = rows
    mock_conn.execute.return_value = mock_result
    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    return mock_engine


_SAMPLE_INDICES_ROWS = [
    (
        "NIFTY 50",
        _SAMPLE_BAR_TIME,
        Decimal("24500.00"),  # open
        Decimal("24550.00"),  # high
        Decimal("24480.00"),  # low
        Decimal("24530.00"),  # close
        Decimal("0.001224"),  # return_since_open
    ),
    (
        "NIFTY BANK",
        _SAMPLE_BAR_TIME,
        Decimal("52000.00"),
        Decimal("52100.00"),
        Decimal("51900.00"),
        Decimal("52050.00"),
        Decimal("0.000962"),
    ),
    (
        "NIFTY IT",
        _SAMPLE_BAR_TIME,
        Decimal("37000.00"),
        Decimal("37100.00"),
        Decimal("36900.00"),
        Decimal("37050.00"),
        None,  # return_since_open NULL — first bar of day
    ),
]


# ---------------------------------------------------------------------------
# /api/v1/intraday/indices
# ---------------------------------------------------------------------------


class TestIndicesEndpoint:
    def test_indices_returns_200_with_data(self, client: TestClient) -> None:
        """200 with list of index bars when table has rows."""
        mock_engine = _mock_engine_with_rows(_SAMPLE_INDICES_ROWS)
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/indices")
        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert "meta" in body
        assert len(body["data"]) == 3

    def test_indices_response_shape_has_required_fields(self, client: TestClient) -> None:
        """Each item has symbol, bar_time, open, high, low, close, return/pct fields."""
        mock_engine = _mock_engine_with_rows(_SAMPLE_INDICES_ROWS[:1])
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/indices")
        item = response.json()["data"][0]
        for field in (
            "symbol",
            "bar_time",
            "open",
            "high",
            "low",
            "close",
            "return_since_open",
            "pct_change_since_open",
        ):
            assert field in item, f"Missing field: {field}"

    def test_indices_symbol_values_present(self, client: TestClient) -> None:
        """symbol field matches the INDEX_TOKENS display values."""
        mock_engine = _mock_engine_with_rows(_SAMPLE_INDICES_ROWS)
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/indices")
        symbols = [item["symbol"] for item in response.json()["data"]]
        assert "NIFTY 50" in symbols
        assert "NIFTY BANK" in symbols
        assert "NIFTY IT" in symbols

    def test_indices_pct_change_is_return_times_100(self, client: TestClient) -> None:
        """pct_change_since_open = return_since_open * 100."""
        mock_engine = _mock_engine_with_rows(_SAMPLE_INDICES_ROWS[:1])
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/indices")
        item = response.json()["data"][0]
        ret = float(item["return_since_open"])
        pct = float(item["pct_change_since_open"])
        assert abs(pct - ret * 100) < 0.0001

    def test_indices_null_return_since_open_handled(self, client: TestClient) -> None:
        """NULL return_since_open → null JSON, pct_change also null — no crash."""
        null_row = _SAMPLE_INDICES_ROWS[2]  # NIFTY IT with None return
        mock_engine = _mock_engine_with_rows([null_row])
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/indices")
        assert response.status_code == 200
        item = response.json()["data"][0]
        assert item["return_since_open"] is None
        assert item["pct_change_since_open"] is None

    def test_indices_empty_table_returns_empty_list_with_note(self, client: TestClient) -> None:
        """Empty table returns data=[] with explanatory note, not an error."""
        mock_engine = _mock_engine_with_rows([])
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/indices")
        assert response.status_code == 200
        body = response.json()
        assert body["data"] == []
        assert "note" in body["meta"]

    def test_indices_cache_control_set(self, client: TestClient) -> None:
        """Cache-Control: public, max-age=30 is present on successful response."""
        mock_engine = _mock_engine_with_rows(_SAMPLE_INDICES_ROWS)
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/indices")
        assert "max-age=30" in response.headers.get("cache-control", "")

    def test_indices_cache_control_on_empty_table(self, client: TestClient) -> None:
        """Cache-Control is set even when table is empty."""
        mock_engine = _mock_engine_with_rows([])
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/indices")
        assert "max-age=30" in response.headers.get("cache-control", "")

    def test_indices_meta_data_as_of_present_when_data_available(self, client: TestClient) -> None:
        """meta.data_as_of is set to bar_time ISO string when data rows exist."""
        mock_engine = _mock_engine_with_rows(_SAMPLE_INDICES_ROWS)
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/indices")
        meta = response.json()["meta"]
        assert "data_as_of" in meta
        assert "2026-05-12" in meta["data_as_of"]

    def test_indices_meta_symbol_count_correct(self, client: TestClient) -> None:
        """meta.symbol_count reflects number of rows returned."""
        mock_engine = _mock_engine_with_rows(_SAMPLE_INDICES_ROWS)
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/indices")
        meta = response.json()["meta"]
        assert meta["symbol_count"] == 3

    def test_indices_close_price_is_decimal_compatible(self, client: TestClient) -> None:
        """close prices are Decimal-compatible strings — no floating-point imprecision."""
        mock_engine = _mock_engine_with_rows(_SAMPLE_INDICES_ROWS[:1])
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/indices")
        item = response.json()["data"][0]
        # Pydantic serialises Decimal as string; must parse without error
        price = Decimal(str(item["close"]))
        assert price == Decimal("24530.00")


# ---------------------------------------------------------------------------
# INDEX_TOKENS constant (atlas.intraday.rs_engine)
# ---------------------------------------------------------------------------


class TestIndexTokens:
    def test_index_tokens_contains_nifty50(self) -> None:
        """INDEX_TOKENS includes the canonical NIFTY 50 token matching NIFTY50_TOKEN."""
        from atlas.intraday.rs_engine import INDEX_TOKENS, NIFTY50_TOKEN

        assert NIFTY50_TOKEN in INDEX_TOKENS
        assert INDEX_TOKENS[NIFTY50_TOKEN] == "NIFTY 50"

    def test_index_tokens_contains_all_five_indices(self) -> None:
        """INDEX_TOKENS has exactly 5 entries for the 5 tracked indices."""
        from atlas.intraday.rs_engine import INDEX_TOKENS

        assert len(INDEX_TOKENS) == 5

    def test_index_tokens_correct_symbols(self) -> None:
        """All expected display symbols are present as values."""
        from atlas.intraday.rs_engine import INDEX_TOKENS

        symbols = set(INDEX_TOKENS.values())
        assert symbols == {"NIFTY 50", "NIFTY BANK", "NIFTY MID100", "NIFTY SMLCAP", "NIFTY IT"}

    def test_index_tokens_correct_kite_token_values(self) -> None:
        """Kite instrument tokens match the NSE specification."""
        from atlas.intraday.rs_engine import INDEX_TOKENS

        assert INDEX_TOKENS[256265] == "NIFTY 50"
        assert INDEX_TOKENS[260105] == "NIFTY BANK"
        assert INDEX_TOKENS[288009] == "NIFTY MID100"
        assert INDEX_TOKENS[289281] == "NIFTY SMLCAP"
        assert INDEX_TOKENS[259849] == "NIFTY IT"

    def test_index_tokens_all_keys_are_int(self) -> None:
        """All keys in INDEX_TOKENS are int (Kite token type)."""
        from atlas.intraday.rs_engine import INDEX_TOKENS

        for token in INDEX_TOKENS:
            assert isinstance(token, int), f"Token {token} is not int"

    def test_index_tokens_all_values_are_str(self) -> None:
        """All values in INDEX_TOKENS are str (display symbol)."""
        from atlas.intraday.rs_engine import INDEX_TOKENS

        for sym in INDEX_TOKENS.values():
            assert isinstance(sym, str), f"Symbol {sym} is not str"

    def test_index_tokens_nifty50_token_matches_constant(self) -> None:
        """INDEX_TOKENS[NIFTY50_TOKEN] == 'NIFTY 50' ensures RS computation stays on Nifty 50."""
        from atlas.intraday.rs_engine import INDEX_TOKENS, NIFTY50_TOKEN

        assert NIFTY50_TOKEN == 256265
        assert INDEX_TOKENS[NIFTY50_TOKEN] == "NIFTY 50"


# ---------------------------------------------------------------------------
# NiftyBarRecord symbol field (atlas.intraday.persistence)
# ---------------------------------------------------------------------------


class TestNiftyBarRecordSymbol:
    def _make_bar(self, symbol: str | None = None) -> Any:
        from atlas.intraday.persistence import NiftyBarRecord  # type: ignore[import-untyped]

        kwargs: dict = {
            "bar_time": _SAMPLE_BAR_TIME,
            "open": Decimal("24500.00"),
            "high": Decimal("24550.00"),
            "low": Decimal("24480.00"),
            "close": Decimal("24530.00"),
        }
        if symbol is not None:
            kwargs["symbol"] = symbol
        return NiftyBarRecord(**kwargs)

    def test_symbol_defaults_to_nifty50(self) -> None:
        """symbol defaults to 'NIFTY 50' so existing callers need no change."""
        bar = self._make_bar()
        assert bar.symbol == "NIFTY 50"

    def test_symbol_can_be_set_to_bank_nifty(self) -> None:
        bar = self._make_bar(symbol="NIFTY BANK")
        assert bar.symbol == "NIFTY BANK"

    def test_symbol_can_be_set_to_midcap(self) -> None:
        bar = self._make_bar(symbol="NIFTY MID100")
        assert bar.symbol == "NIFTY MID100"

    def test_symbol_is_str(self) -> None:
        bar = self._make_bar(symbol="NIFTY SMLCAP")
        assert isinstance(bar.symbol, str)

    def test_symbol_matches_index_tokens_values(self) -> None:
        """Every symbol used in NiftyBarRecord should exist in INDEX_TOKENS values."""
        from atlas.intraday.rs_engine import INDEX_TOKENS

        valid_symbols = set(INDEX_TOKENS.values())
        for sym in valid_symbols:
            bar = self._make_bar(symbol=sym)
            assert bar.symbol == sym
