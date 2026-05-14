"""Tests for atlas/api/tv_signals.py — TradingView webhook receiver endpoints.

All DB calls are mocked. No live database required.

These are unit tests: they verify secret validation, deduplication logic,
query-param filtering, and missing-field rejection.
"""

from __future__ import annotations

import os

# Set auth flags before any atlas import so Config reads them at module load.
os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")
os.environ.setdefault("ATLAS_INTERNAL_SECRET", "test-service-secret")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from atlas.api import app
from atlas.config import Config

_SERVICE_HEADERS = {"Authorization": "Bearer test-service-secret"}

_TEST_WEBHOOK_SECRET = "test_webhook_secret_32chars_exact"  # noqa: S105

VALID_PAYLOAD = {
    "tier": 1,
    "code": "breakout_52w_volume",
    "chart": "vs_nifty",
    "ticker": "HDFCBANK",
    "exchange": "NSE",
    "close": "1820.50",
    "volume": "4500000",
    "time": "2026-05-13T09:20:00Z",
    "secret": _TEST_WEBHOOK_SECRET,
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    Config.AUTH_DISABLED = True
    return TestClient(app, headers=_SERVICE_HEADERS)


# ---------------------------------------------------------------------------
# POST /api/v1/tv/signal
# ---------------------------------------------------------------------------


class TestReceiveTvSignal:
    def test_receive_signal_valid_returns_200_accepted(self, client: TestClient) -> None:
        """Valid payload with correct secret returns 200 and status=accepted."""
        with (
            patch("atlas.api.tv_signals.Config") as mock_cfg,
            patch("atlas.api.tv_signals._is_duplicate", return_value=False),
            patch("atlas.api.tv_signals.process_signal", new_callable=AsyncMock),
        ):
            mock_cfg.TV_WEBHOOK_SECRET = _TEST_WEBHOOK_SECRET
            r = client.post("/api/v1/tv/signal", json=VALID_PAYLOAD)

        assert r.status_code == 200
        assert r.json()["status"] == "accepted"

    def test_receive_signal_wrong_secret_returns_401(self, client: TestClient) -> None:
        """Wrong secret is rejected with 401."""
        payload = {**VALID_PAYLOAD, "secret": "wrong_secret_value_here"}
        with (
            patch("atlas.api.tv_signals.Config") as mock_cfg,
            patch("atlas.api.tv_signals._is_duplicate", return_value=False),
        ):
            mock_cfg.TV_WEBHOOK_SECRET = "correct_secret_32_chars_long_xxx"  # noqa: S105
            r = client.post("/api/v1/tv/signal", json=payload)

        assert r.status_code == 401

    def test_receive_signal_missing_ticker_returns_422(self, client: TestClient) -> None:
        """Payload missing required field 'ticker' is rejected with 422."""
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "ticker"}
        r = client.post("/api/v1/tv/signal", json=payload)
        assert r.status_code == 422

    def test_receive_signal_duplicate_returns_200_deduplicated(self, client: TestClient) -> None:
        """Duplicate signal within dedup window: status=duplicate, pipeline not called."""
        with (
            patch("atlas.api.tv_signals.Config") as mock_cfg,
            patch("atlas.api.tv_signals._is_duplicate", return_value=True),
            patch("atlas.api.tv_signals.process_signal", new_callable=AsyncMock) as mock_proc,
        ):
            mock_cfg.TV_WEBHOOK_SECRET = _TEST_WEBHOOK_SECRET
            r = client.post("/api/v1/tv/signal", json=VALID_PAYLOAD)

        assert r.status_code == 200
        assert r.json()["status"] == "duplicate"
        mock_proc.assert_not_called()

    def test_receive_signal_invalid_chart_returns_422(self, client: TestClient) -> None:
        """chart value not in ('vs_nifty', 'vs_sector') is rejected with 422."""
        payload = {**VALID_PAYLOAD, "chart": "vs_world"}
        r = client.post("/api/v1/tv/signal", json=payload)
        assert r.status_code == 422

    def test_receive_signal_missing_secret_field_is_accepted(self, client: TestClient) -> None:
        """Payload without 'secret' is accepted — TV webhooks cannot send custom headers."""
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "secret"}
        with (
            patch("atlas.api.tv_signals._is_duplicate", return_value=False),
            patch("atlas.api.tv_signals.process_signal", new_callable=AsyncMock),
        ):
            r = client.post("/api/v1/tv/signal", json=payload)
        assert r.status_code == 200
        assert r.json()["status"] == "accepted"


# ---------------------------------------------------------------------------
# GET /api/v1/tv/signals
# ---------------------------------------------------------------------------


def _make_mock_engine_for_signals(rows: list, total: int) -> MagicMock:
    """Mock engine returning rows from fetchall() and total from fetchone()."""
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    fetch_result = MagicMock()
    # Build mock rows with ._mapping attribute
    mock_rows = []
    for row_dict in rows:
        mock_row = MagicMock()
        mock_row._mapping = row_dict
        mock_rows.append(mock_row)
    fetch_result.fetchall.return_value = mock_rows

    count_result = MagicMock()
    count_result.fetchone.return_value = (total,)

    mock_conn.execute.side_effect = [fetch_result, count_result]
    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    return mock_engine


_SAMPLE_REPORT = {
    "id": "abc-123",
    "ticker": "RELIANCE",
    "company_name": "Reliance Industries",
    "condition_tier": 1,
    "condition_code": "breakout_52w_volume",
    "condition_label": "52-week breakout on volume",
    "confirmation_level": "strong",
    "verdict": "bullish",
    "conviction_score": "0.8200",
    "triggered_at": "2026-05-13T09:20:00+00:00",
    "created_at": "2026-05-13T09:20:05+00:00",
}


class TestListSignalReports:
    def test_list_signals_returns_200(self, client: TestClient) -> None:
        """200 with reports list and total when table has rows."""
        mock_engine = _make_mock_engine_for_signals([_SAMPLE_REPORT], total=1)
        with patch("atlas.api.tv_signals.get_engine", return_value=mock_engine):
            r = client.get("/api/v1/tv/signals")
        assert r.status_code == 200
        body = r.json()
        assert "reports" in body
        assert "total" in body

    def test_list_signals_returns_correct_total(self, client: TestClient) -> None:
        """total field reflects DB count."""
        mock_engine = _make_mock_engine_for_signals([_SAMPLE_REPORT], total=42)
        with patch("atlas.api.tv_signals.get_engine", return_value=mock_engine):
            r = client.get("/api/v1/tv/signals")
        assert r.json()["total"] == 42

    def test_list_signals_empty_table_returns_empty_list(self, client: TestClient) -> None:
        """Empty table returns empty reports list, total=0."""
        mock_engine = _make_mock_engine_for_signals([], total=0)
        with patch("atlas.api.tv_signals.get_engine", return_value=mock_engine):
            r = client.get("/api/v1/tv/signals")
        assert r.status_code == 200
        body = r.json()
        assert body["reports"] == []
        assert body["total"] == 0

    def test_list_signals_limit_too_large_returns_422(self, client: TestClient) -> None:
        """limit > 100 is rejected with 422."""
        r = client.get("/api/v1/tv/signals?limit=101")
        assert r.status_code == 422

    def test_list_signals_limit_zero_returns_422(self, client: TestClient) -> None:
        """limit=0 is rejected with 422."""
        r = client.get("/api/v1/tv/signals?limit=0")
        assert r.status_code == 422

    def test_list_signals_negative_offset_returns_422(self, client: TestClient) -> None:
        """offset=-1 is rejected with 422."""
        r = client.get("/api/v1/tv/signals?offset=-1")
        assert r.status_code == 422

    def test_list_signals_tier_filter_accepted(self, client: TestClient) -> None:
        """tier query param is accepted without 422."""
        mock_engine = _make_mock_engine_for_signals([], total=0)
        with patch("atlas.api.tv_signals.get_engine", return_value=mock_engine):
            r = client.get("/api/v1/tv/signals?tier=1")
        assert r.status_code == 200

    def test_list_signals_confirmation_filter_accepted(self, client: TestClient) -> None:
        """confirmation query param is accepted without 422."""
        mock_engine = _make_mock_engine_for_signals([], total=0)
        with patch("atlas.api.tv_signals.get_engine", return_value=mock_engine):
            r = client.get("/api/v1/tv/signals?confirmation=strong")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/tv/signals/{report_id}
# ---------------------------------------------------------------------------


def _make_mock_engine_fetchone(row) -> MagicMock:
    """Mock engine returning row from fetchone()."""
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_result = MagicMock()
    if row is not None:
        mock_row = MagicMock()
        mock_row._mapping = row
        mock_result.fetchone.return_value = mock_row
    else:
        mock_result.fetchone.return_value = None
    mock_conn.execute.return_value = mock_result
    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    return mock_engine


class TestGetSignalReport:
    def test_get_report_found_returns_200(self, client: TestClient) -> None:
        """Existing report ID returns 200 with report dict."""
        mock_engine = _make_mock_engine_fetchone(_SAMPLE_REPORT)
        with patch("atlas.api.tv_signals.get_engine", return_value=mock_engine):
            r = client.get("/api/v1/tv/signals/abc-123")
        assert r.status_code == 200
        assert r.json()["ticker"] == "RELIANCE"

    def test_get_report_not_found_returns_404(self, client: TestClient) -> None:
        """Non-existent report ID returns 404."""
        mock_engine = _make_mock_engine_fetchone(None)
        with patch("atlas.api.tv_signals.get_engine", return_value=mock_engine):
            r = client.get("/api/v1/tv/signals/does-not-exist")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/tv/generate-report
# ---------------------------------------------------------------------------


class TestGenerateReportAdhoc:
    def test_generate_report_valid_secret_returns_accepted(self, client: TestClient) -> None:
        """Valid internal secret + ticker returns 200 with status=accepted."""
        with (
            patch("atlas.api.tv_signals.Config") as mock_cfg,
            patch("atlas.api.tv_signals.process_signal", new_callable=AsyncMock),
        ):
            mock_cfg.ATLAS_INTERNAL_SECRET = "test-service-secret"  # noqa: S105
            mock_cfg.TV_WEBHOOK_SECRET = _TEST_WEBHOOK_SECRET
            r = client.post(
                "/api/v1/tv/generate-report",
                json={"ticker": "INFY"},
                headers={"X-Internal-Secret": "test-service-secret"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "accepted"
        assert body["ticker"] == "INFY"

    def test_generate_report_wrong_secret_returns_401(self, client: TestClient) -> None:
        """Wrong internal secret returns 401."""
        with patch("atlas.api.tv_signals.Config") as mock_cfg:
            mock_cfg.ATLAS_INTERNAL_SECRET = "test-service-secret"  # noqa: S105
            r = client.post(
                "/api/v1/tv/generate-report",
                json={"ticker": "INFY"},
                headers={"X-Internal-Secret": "bad-secret"},
            )
        assert r.status_code == 401

    def test_generate_report_missing_ticker_returns_422(self, client: TestClient) -> None:
        """Missing ticker in body returns 422."""
        with patch("atlas.api.tv_signals.Config") as mock_cfg:
            mock_cfg.ATLAS_INTERNAL_SECRET = "test-service-secret"  # noqa: S105
            mock_cfg.TV_WEBHOOK_SECRET = _TEST_WEBHOOK_SECRET
            r = client.post(
                "/api/v1/tv/generate-report",
                json={},
                headers={"X-Internal-Secret": "test-service-secret"},
            )
        assert r.status_code == 422

    def test_generate_report_ticker_uppercased(self, client: TestClient) -> None:
        """Ticker in response is uppercased regardless of input case."""
        with (
            patch("atlas.api.tv_signals.Config") as mock_cfg,
            patch("atlas.api.tv_signals.process_signal", new_callable=AsyncMock),
        ):
            mock_cfg.ATLAS_INTERNAL_SECRET = "test-service-secret"  # noqa: S105
            mock_cfg.TV_WEBHOOK_SECRET = _TEST_WEBHOOK_SECRET
            r = client.post(
                "/api/v1/tv/generate-report",
                json={"ticker": "infy"},
                headers={"X-Internal-Secret": "test-service-secret"},
            )
        assert r.json()["ticker"] == "INFY"
