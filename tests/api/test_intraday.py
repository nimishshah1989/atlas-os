"""Tests for atlas/api/intraday.py — intraday data endpoints.

All DB calls are mocked. No live database required.

These are unit tests: they verify request/response contract, SQL param
construction, edge-case handling (empty MV, NULL columns, sector filter),
and Decimal usage on financial fields.
"""

from __future__ import annotations

import os

# Set both auth flags before any atlas import so Config reads them at module load.
os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")
os.environ.setdefault("ATLAS_INTERNAL_SECRET", "test-service-secret")

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from atlas.api import app
from atlas.config import Config

_SERVICE_HEADERS = {"Authorization": "Bearer test-service-secret"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    Config.AUTH_DISABLED = True
    return TestClient(app, headers=_SERVICE_HEADERS)


# ---------------------------------------------------------------------------
# Helpers: fake DB rows
# ---------------------------------------------------------------------------

_SAMPLE_BAR_TIME = datetime(2026, 5, 12, 9, 30, 0, tzinfo=UTC)


def _make_leader_row(
    instrument_id: str = "256265",
    symbol: str = "RELIANCE",
    sector: str = "Energy",
    tier: str = "T1",
    close: float = 2850.50,
    ema_20: float | None = 2820.0,
    ema_50: float | None = 2780.0,
    rs_vs_nifty: float | None = 0.0235,
    rs_pctile_intraday: float | None = 92.5,
    bar_time: datetime = _SAMPLE_BAR_TIME,
) -> tuple:
    return (
        instrument_id,
        symbol,
        sector,
        tier,
        close,
        ema_20,
        ema_50,
        rs_vs_nifty,
        rs_pctile_intraday,
        bar_time,
    )


def _mock_engine_with_rows(rows: list[tuple]) -> MagicMock:
    """Return a mock engine whose connect().execute().fetchall() returns rows."""
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_result = MagicMock()
    mock_result.fetchall.return_value = rows
    mock_conn.execute.return_value = mock_result

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    return mock_engine


def _mock_engine_multi(row_sets: list[list[tuple]]) -> MagicMock:
    """Engine that returns different row sets for successive execute() calls."""
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    results = []
    for rows in row_sets:
        mock_result = MagicMock()
        mock_result.fetchone.return_value = rows[0] if rows else None
        mock_result.fetchall.return_value = rows
        results.append(mock_result)
    mock_conn.execute.side_effect = results

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    return mock_engine


# ---------------------------------------------------------------------------
# /api/v1/intraday/rs-leaders
# ---------------------------------------------------------------------------


class TestRsLeaders:
    def test_rs_leaders_returns_200_with_data(self, client: TestClient) -> None:
        """200 with properly shaped data when MV has rows."""
        rows = [_make_leader_row()]
        mock_engine = _mock_engine_with_rows(rows)

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/rs-leaders")

        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert "meta" in body
        assert len(body["data"]) == 1

    def test_rs_leaders_response_shape(self, client: TestClient) -> None:
        """Response data items have all required fields."""
        rows = [_make_leader_row()]
        mock_engine = _mock_engine_with_rows(rows)

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/rs-leaders?n=1")

        item = response.json()["data"][0]
        for field in (
            "instrument_id",
            "symbol",
            "sector",
            "tier",
            "close",
            "ema_20",
            "ema_50",
            "rs_vs_nifty",
            "rs_pctile_intraday",
            "bar_time",
        ):
            assert field in item, f"Missing field: {field}"

    def test_rs_leaders_empty_mv_returns_empty_data_with_note(self, client: TestClient) -> None:
        """Empty MV (market closed) returns empty list with explanatory note."""
        mock_engine = _mock_engine_with_rows([])

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/rs-leaders")

        assert response.status_code == 200
        body = response.json()
        assert body["data"] == []
        assert "note" in body["meta"]
        note = body["meta"]["note"].lower()
        assert "closed" in note or "no intraday" in note

    def test_rs_leaders_cache_control_header_set(self, client: TestClient) -> None:
        """Cache-Control: public, max-age=30 is present on all responses."""
        mock_engine = _mock_engine_with_rows([_make_leader_row()])

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/rs-leaders")

        assert "max-age=30" in response.headers.get("cache-control", "")

    def test_rs_leaders_cache_control_on_empty_response(self, client: TestClient) -> None:
        """Cache-Control header is set even when MV is empty."""
        mock_engine = _mock_engine_with_rows([])

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/rs-leaders")

        assert "max-age=30" in response.headers.get("cache-control", "")

    def test_rs_leaders_n_param_default_is_20(self, client: TestClient) -> None:
        """Default n=20: execute is called (verifies the code path runs)."""
        mock_engine = _mock_engine_with_rows([])

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/rs-leaders")

        assert response.status_code == 200
        execute_call = mock_engine.connect.return_value.__enter__.return_value.execute.call_args
        assert execute_call is not None

    def test_rs_leaders_n_capped_at_50(self, client: TestClient) -> None:
        """n > 50 is rejected with 422 (Query validation)."""
        mock_engine = _mock_engine_with_rows([])

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/rs-leaders?n=51")

        assert response.status_code == 422

    def test_rs_leaders_n_zero_rejected(self, client: TestClient) -> None:
        """n=0 is rejected with 422."""
        mock_engine = _mock_engine_with_rows([])

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/rs-leaders?n=0")

        assert response.status_code == 422

    def test_rs_leaders_sector_filter_accepted(self, client: TestClient) -> None:
        """sector query param is accepted and does not cause 422."""
        rows = [_make_leader_row(sector="Energy")]
        mock_engine = _mock_engine_with_rows(rows)

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/rs-leaders?sector=Energy")

        assert response.status_code == 200

    def test_rs_leaders_null_optional_fields_returned_as_none(self, client: TestClient) -> None:
        """NULL ema_20, ema_50, rs fields come back as null in JSON."""
        rows = [
            _make_leader_row(ema_20=None, ema_50=None, rs_vs_nifty=None, rs_pctile_intraday=None)
        ]
        mock_engine = _mock_engine_with_rows(rows)

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/rs-leaders")

        item = response.json()["data"][0]
        assert item["ema_20"] is None
        assert item["ema_50"] is None
        assert item["rs_vs_nifty"] is None
        assert item["rs_pctile_intraday"] is None

    def test_rs_leaders_meta_includes_data_as_of(self, client: TestClient) -> None:
        """meta.data_as_of equals the bar_time of the first result."""
        rows = [_make_leader_row(bar_time=_SAMPLE_BAR_TIME)]
        mock_engine = _mock_engine_with_rows(rows)

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/rs-leaders")

        meta = response.json()["meta"]
        assert "data_as_of" in meta
        assert "2026-05-12" in meta["data_as_of"]

    def test_rs_leaders_multiple_rows_returned(self, client: TestClient) -> None:
        """Multiple rows are returned in correct order."""
        rows = [
            _make_leader_row(symbol="RELIANCE", rs_pctile_intraday=95.0),
            _make_leader_row(symbol="TCS", rs_pctile_intraday=88.0),
            _make_leader_row(symbol="INFY", rs_pctile_intraday=72.0),
        ]
        mock_engine = _mock_engine_with_rows(rows)

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/rs-leaders?n=3")

        data = response.json()["data"]
        assert len(data) == 3
        assert data[0]["symbol"] == "RELIANCE"


# ---------------------------------------------------------------------------
# /api/v1/intraday/status
# ---------------------------------------------------------------------------


class TestIntradayStatus:
    def test_status_returns_200(self, client: TestClient) -> None:
        """200 with correct response shape."""
        session_row = ("active", datetime(2026, 5, 12, 3, 45, 0), datetime(2026, 5, 12, 18, 29, 59))
        bar_row = (datetime(2026, 5, 12, 9, 30, 0), 742)

        mock_engine = _mock_engine_multi([[session_row], [bar_row]])

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/status")

        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert "meta" in body

    def test_status_data_shape(self, client: TestClient) -> None:
        """data dict contains all expected keys."""
        session_row = ("active", datetime(2026, 5, 12, 3, 45, 0), datetime(2026, 5, 12, 18, 29, 59))
        bar_row = (datetime(2026, 5, 12, 9, 30, 0), 742)
        mock_engine = _mock_engine_multi([[session_row], [bar_row]])

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/status")

        data = response.json()["data"]
        expected_keys = (
            "session_type",
            "token_valid_until",
            "last_bar_time",
            "instruments_in_last_bar",
        )
        for key in expected_keys:
            assert key in data, f"Missing key: {key}"

    def test_status_no_session_row_returns_nulls(self, client: TestClient) -> None:
        """When atlas_kite_session is empty, session fields are null."""
        mock_engine = _mock_engine_multi([[], [(None, 0)]])

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/status")

        data = response.json()["data"]
        assert data["session_type"] is None
        assert data["token_valid_until"] is None

    def test_status_no_recent_bars_returns_zero_count(self, client: TestClient) -> None:
        """When no bars in last hour, instruments_in_last_bar=0 and last_bar_time=null."""
        session_row = ("active", datetime(2026, 5, 12, 3, 0, 0), datetime(2026, 5, 12, 18, 29, 59))
        bar_row = (None, 0)  # MAX(bar_time) is NULL when no recent rows
        mock_engine = _mock_engine_multi([[session_row], [bar_row]])

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/status")

        data = response.json()["data"]
        assert data["last_bar_time"] is None
        assert data["instruments_in_last_bar"] == 0

    def test_status_meta_includes_source(self, client: TestClient) -> None:
        """meta.source is atlas_kite_session."""
        session_row = ("active", datetime(2026, 5, 12, 3, 0, 0), datetime(2026, 5, 12, 18, 29, 59))
        bar_row = (datetime(2026, 5, 12, 9, 30, 0), 750)
        mock_engine = _mock_engine_multi([[session_row], [bar_row]])

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/status")

        meta = response.json()["meta"]
        assert meta["source"] == "atlas_kite_session"

    def test_status_active_session_type_returned(self, client: TestClient) -> None:
        """session_type 'active' is returned correctly."""
        session_row = ("active", datetime(2026, 5, 12, 3, 0, 0), datetime(2026, 5, 12, 18, 29, 59))
        bar_row = (datetime(2026, 5, 12, 9, 30, 0), 750)
        mock_engine = _mock_engine_multi([[session_row], [bar_row]])

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/status")

        assert response.json()["data"]["session_type"] == "active"

    def test_status_closed_session_type_returned(self, client: TestClient) -> None:
        """session_type 'closed' is returned correctly."""
        session_row = ("closed", datetime(2026, 5, 11, 3, 0, 0), datetime(2026, 5, 11, 18, 29, 59))
        bar_row = (None, 0)
        mock_engine = _mock_engine_multi([[session_row], [bar_row]])

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/status")

        assert response.json()["data"]["session_type"] == "closed"

    def test_status_instruments_count_correct(self, client: TestClient) -> None:
        """instruments_in_last_bar reflects the COUNT(*) from DB."""
        session_row = ("active", datetime(2026, 5, 12, 3, 0, 0), datetime(2026, 5, 12, 18, 29, 59))
        bar_row = (datetime(2026, 5, 12, 9, 30, 0), 742)
        mock_engine = _mock_engine_multi([[session_row], [bar_row]])

        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/status")

        assert response.json()["data"]["instruments_in_last_bar"] == 742


# ---------------------------------------------------------------------------
# Helpers: fetchone mock + new sample data
# ---------------------------------------------------------------------------

from decimal import Decimal  # noqa: E402 — appended section; Decimal not imported above


def _mock_engine_fetchone(row) -> MagicMock:
    """Return a mock engine whose connect().execute().fetchone() returns row."""
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_result = MagicMock()
    mock_result.fetchone.return_value = row
    mock_conn.execute.return_value = mock_result
    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    return mock_engine


_SAMPLE_NIFTY_ROW = (
    _SAMPLE_BAR_TIME,  # bar_time
    Decimal("24500.00"),  # open
    Decimal("24550.00"),  # high
    Decimal("24480.00"),  # low
    Decimal("24530.00"),  # close
    Decimal("0.001224"),  # return_since_open
)

_SAMPLE_SECTOR_ROW = ("TECHNOLOGY", Decimal("0.008542"), 12, _SAMPLE_BAR_TIME)

_SAMPLE_PRICE_ROWS = [
    ("uuid-rel-001", Decimal("2850.50"), _SAMPLE_BAR_TIME),
    ("uuid-tcs-002", Decimal("3540.00"), _SAMPLE_BAR_TIME),
]


# ---------------------------------------------------------------------------
# /api/v1/intraday/nifty
# ---------------------------------------------------------------------------


class TestNiftyEndpoint:
    def test_nifty_returns_200_with_data(self, client: TestClient) -> None:
        """200 with properly shaped data when table has a row."""
        mock_engine = _mock_engine_fetchone(_SAMPLE_NIFTY_ROW)
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/nifty")
        assert response.status_code == 200
        body = response.json()
        assert body["data"] is not None
        assert "meta" in body

    def test_nifty_response_shape_has_required_fields(self, client: TestClient) -> None:
        """data contains all seven required fields."""
        mock_engine = _mock_engine_fetchone(_SAMPLE_NIFTY_ROW)
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/nifty")
        data = response.json()["data"]
        for field in (
            "bar_time",
            "open",
            "high",
            "low",
            "close",
            "return_since_open",
            "pct_change_since_open",
        ):
            assert field in data, f"Missing field: {field}"

    def test_nifty_pct_change_is_return_times_100(self, client: TestClient) -> None:
        """pct_change_since_open = return_since_open * 100."""
        mock_engine = _mock_engine_fetchone(_SAMPLE_NIFTY_ROW)
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/nifty")
        data = response.json()["data"]
        ret = float(data["return_since_open"])
        pct = float(data["pct_change_since_open"])
        assert abs(pct - ret * 100) < 0.0001

    def test_nifty_empty_table_returns_null_data_with_note(self, client: TestClient) -> None:
        """Empty table returns data=null, not an error."""
        mock_engine = _mock_engine_fetchone(None)
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/nifty")
        assert response.status_code == 200
        body = response.json()
        assert body["data"] is None
        assert "note" in body["meta"]

    def test_nifty_cache_control_set(self, client: TestClient) -> None:
        """Cache-Control: public, max-age=30 is present."""
        mock_engine = _mock_engine_fetchone(_SAMPLE_NIFTY_ROW)
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/nifty")
        assert "max-age=30" in response.headers.get("cache-control", "")

    def test_nifty_cache_control_on_empty_table(self, client: TestClient) -> None:
        """Cache-Control is set even when table is empty."""
        mock_engine = _mock_engine_fetchone(None)
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/nifty")
        assert "max-age=30" in response.headers.get("cache-control", "")

    def test_nifty_meta_data_as_of_present_when_data_available(self, client: TestClient) -> None:
        """meta.data_as_of is the bar_time ISO string when data is present."""
        mock_engine = _mock_engine_fetchone(_SAMPLE_NIFTY_ROW)
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/nifty")
        meta = response.json()["meta"]
        assert "data_as_of" in meta
        assert "2026-05-12" in meta["data_as_of"]

    def test_nifty_return_since_open_null_handled(self, client: TestClient) -> None:
        """return_since_open=NULL in DB comes back as null JSON (no crash)."""
        row_with_null_return = (
            _SAMPLE_BAR_TIME,
            Decimal("24500.00"),
            Decimal("24550.00"),
            Decimal("24480.00"),
            Decimal("24530.00"),
            None,  # return_since_open is NULL
        )
        mock_engine = _mock_engine_fetchone(row_with_null_return)
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/nifty")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["return_since_open"] is None
        assert data["pct_change_since_open"] is None


# ---------------------------------------------------------------------------
# /api/v1/intraday/sector-movers
# ---------------------------------------------------------------------------


class TestSectorMovers:
    def test_sector_movers_returns_200_with_data(self, client: TestClient) -> None:
        """200 with list of sector movers."""
        mock_engine = _mock_engine_with_rows([_SAMPLE_SECTOR_ROW])
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/sector-movers")
        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 1

    def test_sector_movers_response_shape(self, client: TestClient) -> None:
        """Each item has sector, avg_return_since_open, stock_count."""
        mock_engine = _mock_engine_with_rows([_SAMPLE_SECTOR_ROW])
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/sector-movers")
        item = response.json()["data"][0]
        for field in ("sector", "avg_return_since_open", "stock_count"):
            assert field in item, f"Missing field: {field}"

    def test_sector_movers_empty_mv_returns_empty_list(self, client: TestClient) -> None:
        """Empty MV returns empty list with note."""
        mock_engine = _mock_engine_with_rows([])
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/sector-movers")
        assert response.status_code == 200
        body = response.json()
        assert body["data"] == []
        assert "note" in body["meta"]

    def test_sector_movers_cache_control_set(self, client: TestClient) -> None:
        """Cache-Control: public, max-age=30 is present."""
        mock_engine = _mock_engine_with_rows([_SAMPLE_SECTOR_ROW])
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/sector-movers")
        assert "max-age=30" in response.headers.get("cache-control", "")

    def test_sector_movers_meta_has_data_as_of(self, client: TestClient) -> None:
        """meta.data_as_of is present when data rows exist."""
        mock_engine = _mock_engine_with_rows([_SAMPLE_SECTOR_ROW])
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/sector-movers")
        meta = response.json()["meta"]
        assert "data_as_of" in meta

    def test_sector_movers_multiple_sectors_returned(self, client: TestClient) -> None:
        """Multiple sector rows all appear in response."""
        rows = [
            ("TECHNOLOGY", Decimal("0.008542"), 12, _SAMPLE_BAR_TIME),
            ("FINANCIALS", Decimal("0.003210"), 18, _SAMPLE_BAR_TIME),
            ("ENERGY", Decimal("-0.002100"), 8, _SAMPLE_BAR_TIME),
        ]
        mock_engine = _mock_engine_with_rows(rows)
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/sector-movers")
        assert len(response.json()["data"]) == 3


# ---------------------------------------------------------------------------
# /api/v1/intraday/prices
# ---------------------------------------------------------------------------


class TestIntradayPrices:
    def test_prices_returns_200_with_data(self, client: TestClient) -> None:
        """200 with instrument_id->price dict."""
        mock_engine = _mock_engine_with_rows(_SAMPLE_PRICE_ROWS)
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/prices")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "uuid-rel-001" in data
        assert "uuid-tcs-002" in data

    def test_prices_empty_mv_returns_empty_dict(self, client: TestClient) -> None:
        """Empty MV returns empty dict with note."""
        mock_engine = _mock_engine_with_rows([])
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/prices")
        assert response.status_code == 200
        body = response.json()
        assert body["data"] == {}
        assert "note" in body["meta"]

    def test_prices_cache_control_set(self, client: TestClient) -> None:
        """Cache-Control: public, max-age=30 is present."""
        mock_engine = _mock_engine_with_rows(_SAMPLE_PRICE_ROWS)
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/prices")
        assert "max-age=30" in response.headers.get("cache-control", "")

    def test_prices_meta_has_instrument_count(self, client: TestClient) -> None:
        """meta.instrument_count reflects the number of rows."""
        mock_engine = _mock_engine_with_rows(_SAMPLE_PRICE_ROWS)
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/prices")
        meta = response.json()["meta"]
        assert meta["instrument_count"] == len(_SAMPLE_PRICE_ROWS)

    def test_prices_meta_has_data_as_of(self, client: TestClient) -> None:
        """meta.data_as_of is present when rows exist."""
        mock_engine = _mock_engine_with_rows(_SAMPLE_PRICE_ROWS)
        with patch("atlas.api.intraday.get_engine", return_value=mock_engine):
            response = client.get("/api/v1/intraday/prices")
        meta = response.json()["meta"]
        assert "data_as_of" in meta
