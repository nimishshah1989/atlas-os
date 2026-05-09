"""Tests for atlas.api.strategies — POST /api/strategies/{id}/backtest.

Fixture pattern matches test_portfolios.py (mock engine, dependency_overrides).
Integration tests require ATLAS_DB_URL and are skipped without it.
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_SKIP_INTEGRATION = pytest.mark.skipif(
    os.environ.get("ATLAS_DB_URL") is None,
    reason="needs ATLAS_DB_URL — integration tests run on EC2 only",
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_engine() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(mock_engine: MagicMock) -> TestClient:
    """TestClient with get_engine overridden to a MagicMock."""
    from atlas.api.strategies import router
    from atlas.db import get_engine

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_engine] = lambda: mock_engine
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _valid_strategy_id() -> str:
    return str(uuid.uuid4())


def _valid_body() -> dict:  # type: ignore[type-arg]
    return {
        "start_date": "2022-01-01",
        "end_date": "2024-12-31",
        "initial_capital": 1_000_000,
    }


# ---------------------------------------------------------------------------
# Helpers for mock engine configuration
# ---------------------------------------------------------------------------


def _configure_engine_strategy_found(mock_engine: MagicMock, strategy_id: str) -> None:
    """Configure mock engine so strategy exists and no in-flight backtest."""
    # connect() context manager for the guard check
    conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    # First execute: strategy exists → row with id
    strategy_row = MagicMock()
    strategy_row.__getitem__ = MagicMock(return_value=strategy_id)
    # Second execute: no in-flight backtest → None
    no_backtest = MagicMock()
    no_backtest.fetchone.return_value = None

    conn.execute.side_effect = [
        MagicMock(fetchone=MagicMock(return_value=(strategy_id,))),
        MagicMock(fetchone=MagicMock(return_value=None)),
    ]

    # begin() context manager for INSERT
    begin_conn = MagicMock()
    mock_engine.begin.return_value.__enter__ = MagicMock(return_value=begin_conn)
    mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)


def _configure_engine_strategy_not_found(mock_engine: MagicMock) -> None:
    """Configure mock engine so strategy does NOT exist."""
    conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value = MagicMock(fetchone=MagicMock(return_value=None))


def _configure_engine_already_running(
    mock_engine: MagicMock, strategy_id: str, run_id: str
) -> None:
    """Configure mock engine: strategy exists + in-flight backtest exists."""
    conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    # First execute: strategy found; second: existing run found
    conn.execute.side_effect = [
        MagicMock(fetchone=MagicMock(return_value=(strategy_id,))),
        MagicMock(fetchone=MagicMock(return_value=(run_id,))),
    ]


# ---------------------------------------------------------------------------
# Validation tests (400)
# ---------------------------------------------------------------------------


class TestReRunBacktestValidation:
    def test_end_date_same_as_start_raises_422(self, client: TestClient) -> None:
        sid = _valid_strategy_id()
        response = client.post(
            f"/api/strategies/{sid}/backtest",
            json={
                "start_date": "2023-01-01",
                "end_date": "2023-01-01",
                "initial_capital": 500_000,
            },
        )
        assert response.status_code == 422, response.text
        body = response.json()
        assert "end_date" in str(body).lower() or "after" in str(body).lower()

    def test_end_date_before_start_raises_422(self, client: TestClient) -> None:
        sid = _valid_strategy_id()
        response = client.post(
            f"/api/strategies/{sid}/backtest",
            json={
                "start_date": "2023-06-01",
                "end_date": "2023-01-01",
                "initial_capital": 500_000,
            },
        )
        assert response.status_code == 422, response.text

    def test_capital_below_minimum_raises_422(self, client: TestClient) -> None:
        sid = _valid_strategy_id()
        response = client.post(
            f"/api/strategies/{sid}/backtest",
            json={
                "start_date": "2022-01-01",
                "end_date": "2024-12-31",
                "initial_capital": 50_000,  # below 100_000 minimum
            },
        )
        assert response.status_code == 422, response.text

    def test_capital_zero_raises_422(self, client: TestClient) -> None:
        sid = _valid_strategy_id()
        response = client.post(
            f"/api/strategies/{sid}/backtest",
            json={
                "start_date": "2022-01-01",
                "end_date": "2024-12-31",
                "initial_capital": 0,
            },
        )
        assert response.status_code == 422, response.text

    def test_invalid_uuid_strategy_id_raises_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/strategies/not-a-uuid/backtest",
            json=_valid_body(),
        )
        assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# 404 — strategy not found
# ---------------------------------------------------------------------------


class TestReRunBacktest404:
    def test_unknown_strategy_id_returns_404(
        self, client: TestClient, mock_engine: MagicMock
    ) -> None:
        _configure_engine_strategy_not_found(mock_engine)
        sid = _valid_strategy_id()
        response = client.post(f"/api/strategies/{sid}/backtest", json=_valid_body())
        assert response.status_code == 404, response.text
        detail = response.json()["detail"]
        assert detail["error_code"] == "strategy_not_found"
        assert str(sid) in detail["message"]


# ---------------------------------------------------------------------------
# 409 — already running
# ---------------------------------------------------------------------------


class TestReRunBacktest409:
    def test_409_when_backtest_already_running(
        self, client: TestClient, mock_engine: MagicMock
    ) -> None:
        sid = _valid_strategy_id()
        existing_run = _valid_strategy_id()
        _configure_engine_already_running(mock_engine, sid, existing_run)
        response = client.post(f"/api/strategies/{sid}/backtest", json=_valid_body())
        assert response.status_code == 409, response.text
        detail = response.json()["detail"]
        assert detail["error_code"] == "already_running"
        assert "run_id" in detail["context"]


# ---------------------------------------------------------------------------
# 202 — happy path
# ---------------------------------------------------------------------------


class TestReRunBacktest202:
    def test_happy_path_returns_202_with_run_id(
        self, client: TestClient, mock_engine: MagicMock
    ) -> None:
        sid = _valid_strategy_id()
        _configure_engine_strategy_found(mock_engine, sid)
        response = client.post(f"/api/strategies/{sid}/backtest", json=_valid_body())
        assert response.status_code == 202, response.text
        body = response.json()
        assert "data" in body
        assert "compute_run_id" in body["data"]
        assert body["data"]["strategy_id"] == sid
        assert body["data"]["status"] == "running"
        # meta envelope present
        assert "meta" in body
        assert body["meta"]["source"] == "atlas-api"

    def test_happy_path_compute_run_id_is_uuid(
        self, client: TestClient, mock_engine: MagicMock
    ) -> None:
        sid = _valid_strategy_id()
        _configure_engine_strategy_found(mock_engine, sid)
        response = client.post(f"/api/strategies/{sid}/backtest", json=_valid_body())
        assert response.status_code == 202, response.text
        run_id = response.json()["data"]["compute_run_id"]
        # Must be a valid UUID — raises ValueError if not
        uuid.UUID(run_id)

    def test_happy_path_inserts_pipeline_runs_row(
        self, client: TestClient, mock_engine: MagicMock
    ) -> None:
        """Verify that engine.begin() is called (INSERT into atlas_pipeline_runs)."""
        sid = _valid_strategy_id()
        _configure_engine_strategy_found(mock_engine, sid)
        client.post(f"/api/strategies/{sid}/backtest", json=_valid_body())
        # engine.begin() must have been called to INSERT the running row
        assert mock_engine.begin.called, "engine.begin() must be called to INSERT pipeline run"

    def test_capital_exactly_at_minimum_passes(
        self, client: TestClient, mock_engine: MagicMock
    ) -> None:
        sid = _valid_strategy_id()
        _configure_engine_strategy_found(mock_engine, sid)
        body = _valid_body()
        body["initial_capital"] = 100_000  # exactly at minimum
        response = client.post(f"/api/strategies/{sid}/backtest", json=body)
        assert response.status_code == 202, response.text
