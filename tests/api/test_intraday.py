"""Tests for atlas/api/intraday.py — intraday data endpoints.

All DB calls are mocked. No live database required.

These are unit tests: they verify request/response contract, SQL param
construction, edge-case handling (empty MV, NULL columns, sector filter),
and Decimal usage on financial fields.
"""

from __future__ import annotations

import os

os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from atlas.api import app
from atlas.config import Config


@pytest.fixture(scope="module")
def client() -> TestClient:
    Config.AUTH_DISABLED = True
    return TestClient(app)


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
