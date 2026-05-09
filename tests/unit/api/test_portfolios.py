"""Unit tests for atlas.api.portfolios — mocked DB, no real backtest."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_engine() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(mock_engine: MagicMock) -> TestClient:
    """TestClient with get_engine overridden to a MagicMock."""
    from atlas.api.portfolios import router
    from atlas.db import get_engine

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_engine] = lambda: mock_engine
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _patch_session(rows_or_row):
    """Build a context manager that replaces open_compute_session.

    rows_or_row: either a single fetchone() row (Mock or None) or a list for fetchall().
    A SimpleNamespace-style mock is configured to return both shapes; tests choose.
    """
    conn = MagicMock()
    execute_result = MagicMock()
    if isinstance(rows_or_row, list):
        execute_result.fetchall.return_value = rows_or_row
        execute_result.fetchone.return_value = rows_or_row[0] if rows_or_row else None
    else:
        execute_result.fetchone.return_value = rows_or_row
        execute_result.fetchall.return_value = [rows_or_row] if rows_or_row else []
    conn.execute.return_value = execute_result

    @contextmanager
    def _cm(_engine):
        yield conn

    return _cm


class TestCreatePortfolio:
    def test_create_portfolio_returns_201_and_portfolio_id(self, client: TestClient):
        with patch(
            "atlas.api.portfolios.create_custom_portfolio",
            return_value="abc-123",
        ) as m:
            response = client.post(
                "/api/portfolios/custom",
                json={
                    "name": "My Test",
                    "instruments": [
                        {"instrument_id": "INS_A", "instrument_type": "stock", "weight_pct": 50.0},
                        {"instrument_id": "INS_B", "instrument_type": "stock", "weight_pct": 50.0},
                    ],
                },
            )
        assert response.status_code == 201
        body = response.json()
        assert body == {"portfolio_id": "abc-123", "status": "pending"}
        assert m.call_count == 1

    def test_create_portfolio_validation_error_returns_422(self, client: TestClient):
        with patch(
            "atlas.api.portfolios.create_custom_portfolio",
            side_effect=ValueError("Portfolio weights must sum to 100"),
        ):
            response = client.post(
                "/api/portfolios/custom",
                json={
                    "name": "Bad",
                    "instruments": [
                        {"instrument_id": "INS_A", "instrument_type": "stock", "weight_pct": 60.0},
                    ],
                },
            )
        assert response.status_code == 422
        assert "weights must sum" in response.json()["detail"]


class TestPortfolioStatus:
    def test_get_portfolio_status_pending(self, client: TestClient):
        row = MagicMock()
        row.backtest_id = None
        row.updated_at = "2026-05-09T12:00:00Z"
        with patch(
            "atlas.api.portfolios.open_compute_session",
            _patch_session(row),
        ):
            response = client.get("/api/portfolios/custom/abc-123/status")
        assert response.status_code == 200
        assert response.json() == {
            "portfolio_id": "abc-123",
            "status": "pending",
            "backtest_id": None,
        }

    def test_get_portfolio_status_complete(self, client: TestClient):
        row = MagicMock()
        row.backtest_id = "bt-uuid-9"
        row.updated_at = "2026-05-09T12:30:00Z"
        with patch(
            "atlas.api.portfolios.open_compute_session",
            _patch_session(row),
        ):
            response = client.get("/api/portfolios/custom/abc-123/status")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "complete"
        assert body["backtest_id"] == "bt-uuid-9"

    def test_get_portfolio_status_not_found_returns_404(self, client: TestClient):
        with patch(
            "atlas.api.portfolios.open_compute_session",
            _patch_session(None),
        ):
            response = client.get("/api/portfolios/custom/missing/status")
        assert response.status_code == 404


class TestPortfolioDetail:
    def test_get_portfolio_not_found_returns_404(self, client: TestClient):
        with patch(
            "atlas.api.portfolios.open_compute_session",
            _patch_session(None),
        ):
            response = client.get("/api/portfolios/custom/missing")
        assert response.status_code == 404
        assert response.json()["detail"] == "Portfolio not found"


class TestListPortfolios:
    def test_list_portfolios_returns_list(self, client: TestClient):
        rows = [
            ("p1", "Portfolio One", "bt-1", False, "2026-05-01"),
            ("p2", "Portfolio Two", None, False, "2026-04-30"),
        ]
        with patch(
            "atlas.api.portfolios.open_compute_session",
            _patch_session(rows),
        ):
            response = client.get("/api/portfolios/custom")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 2
        assert body[0]["id"] == "p1"
        assert body[0]["status"] == "complete"
        assert body[1]["id"] == "p2"
        assert body[1]["status"] == "pending"
