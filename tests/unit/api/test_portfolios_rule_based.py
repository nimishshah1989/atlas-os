"""Tests for POST /api/portfolios/rule-based — FM-authored rule-based portfolio.

Fixture pattern matches test_portfolios.py (mock engine, dependency_overrides).
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_engine() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(mock_engine: MagicMock) -> TestClient:
    """TestClient with get_engine overridden to a MagicMock."""
    from atlas.api.portfolios import rule_based_router
    from atlas.db import get_engine

    app = FastAPI()
    app.include_router(rule_based_router)
    app.dependency_overrides[get_engine] = lambda: mock_engine
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _configure_engine_begin(mock_engine: MagicMock) -> MagicMock:
    """Set up engine.begin() context manager to return a usable connection mock."""
    conn = MagicMock()
    mock_engine.begin.return_value.__enter__ = MagicMock(return_value=conn)
    mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)
    return conn


# ---------------------------------------------------------------------------
# 400 — validation failures
# ---------------------------------------------------------------------------


class TestRuleBasedPortfolio400:
    def test_empty_name_returns_400(self, client: TestClient, mock_engine: MagicMock) -> None:
        response = client.post(
            "/api/portfolios/rule-based",
            json={
                "name": "   ",  # whitespace-only
                "config": {},
            },
        )
        assert response.status_code == 400, response.text
        detail = response.json()["detail"]
        assert detail["error_code"] == "name_required"

    def test_unknown_config_key_returns_400(
        self, client: TestClient, mock_engine: MagicMock
    ) -> None:
        response = client.post(
            "/api/portfolios/rule-based",
            json={
                "name": "Test Strategy",
                "config": {"unknown_key": "value"},
            },
        )
        assert response.status_code == 400, response.text
        detail = response.json()["detail"]
        assert detail["error_code"] == "invalid_config"
        assert "unknown_key" in detail["message"]

    def test_unknown_rs_state_returns_400(self, client: TestClient, mock_engine: MagicMock) -> None:
        response = client.post(
            "/api/portfolios/rule-based",
            json={
                "name": "Test Strategy",
                "config": {"rs_state_filter": ["SuperLeader"]},
            },
        )
        assert response.status_code == 400, response.text
        detail = response.json()["detail"]
        assert detail["error_code"] == "invalid_config"

    def test_unknown_breadth_field_returns_400(
        self, client: TestClient, mock_engine: MagicMock
    ) -> None:
        response = client.post(
            "/api/portfolios/rule-based",
            json={
                "name": "Test Strategy",
                "config": {"breadth_gates": {"unknown_breadth_metric": 50}},
            },
        )
        assert response.status_code == 400, response.text
        detail = response.json()["detail"]
        assert detail["error_code"] == "invalid_config"

    def test_invalid_position_sizing_returns_400(
        self, client: TestClient, mock_engine: MagicMock
    ) -> None:
        response = client.post(
            "/api/portfolios/rule-based",
            json={
                "name": "Test Strategy",
                "config": {"position_sizing": "random_weighting"},
            },
        )
        assert response.status_code == 400, response.text

    def test_missing_config_field_raises_422(self, client: TestClient) -> None:
        """config field is required by Pydantic — missing raises 422."""
        response = client.post(
            "/api/portfolios/rule-based",
            json={"name": "Test Strategy"},
        )
        assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# 201 — happy path
# ---------------------------------------------------------------------------


class TestRuleBasedPortfolio201:
    def test_happy_path_returns_201_with_strategy_id(
        self, client: TestClient, mock_engine: MagicMock
    ) -> None:
        _configure_engine_begin(mock_engine)
        response = client.post(
            "/api/portfolios/rule-based",
            json={
                "name": "My Rule Strategy",
                "description": "Test FM-authored rule strategy",
                "config": {
                    "rs_state_filter": ["Leader", "Strong"],
                    "position_sizing": "equal_weight",
                    "max_positions": 20,
                    "rebalance_trigger": "weekly",
                },
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert "data" in body
        assert "strategy_id" in body["data"]
        # strategy_id must be a valid UUID
        uuid.UUID(body["data"]["strategy_id"])

    def test_happy_path_response_contains_name_and_status(
        self, client: TestClient, mock_engine: MagicMock
    ) -> None:
        _configure_engine_begin(mock_engine)
        response = client.post(
            "/api/portfolios/rule-based",
            json={
                "name": "  Padded Name  ",
                "config": {},
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["data"]["name"] == "Padded Name"  # stripped
        assert body["data"]["status"] == "created"

    def test_happy_path_calls_engine_begin(
        self, client: TestClient, mock_engine: MagicMock
    ) -> None:
        """engine.begin() must be called to INSERT into strategy_configs."""
        _configure_engine_begin(mock_engine)
        client.post(
            "/api/portfolios/rule-based",
            json={"name": "Test", "config": {}},
        )
        assert mock_engine.begin.called, "engine.begin() must be called for transactional INSERT"

    def test_happy_path_response_has_meta(self, client: TestClient, mock_engine: MagicMock) -> None:
        _configure_engine_begin(mock_engine)
        response = client.post(
            "/api/portfolios/rule-based",
            json={"name": "Meta Test", "config": {}},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert "meta" in body
        assert body["meta"]["source"] == "atlas-api"

    def test_empty_config_is_valid_rule_based_portfolio(
        self, client: TestClient, mock_engine: MagicMock
    ) -> None:
        """An empty config dict is allowed (FM may set no rules initially)."""
        _configure_engine_begin(mock_engine)
        response = client.post(
            "/api/portfolios/rule-based",
            json={"name": "Blank Rules", "config": {}},
        )
        assert response.status_code == 201, response.text

    def test_description_optional(self, client: TestClient, mock_engine: MagicMock) -> None:
        """description field is optional — omitting it should not fail."""
        _configure_engine_begin(mock_engine)
        response = client.post(
            "/api/portfolios/rule-based",
            json={"name": "No Description", "config": {}},
        )
        assert response.status_code == 201, response.text

    def test_breadth_gates_config_accepted(
        self, client: TestClient, mock_engine: MagicMock
    ) -> None:
        """Full breadth gate config should pass validation and return 201."""
        _configure_engine_begin(mock_engine)
        response = client.post(
            "/api/portfolios/rule-based",
            json={
                "name": "Breadth Gated Strategy",
                "config": {
                    "breadth_gates": {
                        "pct_above_ema_50": 60.0,
                        "ad_ratio": 1.2,
                        "new_high_low_ratio": 2.0,
                    },
                    "regime_state_filter": ["Risk-On", "Constructive"],
                    "max_positions": 15,
                },
            },
        )
        assert response.status_code == 201, response.text
