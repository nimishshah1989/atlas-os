"""Tests for fund decision history API endpoints."""

from __future__ import annotations

import os

# Disable auth before any atlas import so Config reads them at module load.
os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")
os.environ.setdefault("ATLAS_INTERNAL_SECRET", "test-service-secret")

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from atlas.api import app
from atlas.config import Config

_SERVICE_HEADERS = {"Authorization": "Bearer test-service-secret"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    Config.AUTH_DISABLED = True
    Config.ATLAS_INTERNAL_SECRET = "test-service-secret"  # noqa: S105
    return TestClient(app, headers=_SERVICE_HEADERS)


def _mock_conn(rows):
    mock_result = MagicMock()
    mock_result.fetchall.return_value = rows
    mock_conn = MagicMock()
    mock_conn.execute.return_value = mock_result
    return mock_conn


def _make_session_mock(mock_session, mock_conn_obj):
    """Wire up context manager mock correctly for open_compute_session."""
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_conn_obj)
    mock_cm.__exit__ = MagicMock(return_value=False)
    mock_session.return_value = mock_cm


def _make_score_row(data: dict):
    """Create a mock SQLAlchemy Row with _mapping attribute."""
    mock_row = MagicMock()
    mock_row._mapping = data
    return mock_row


@patch("atlas.api.fund_decisions.get_engine")
@patch("atlas.api.fund_decisions.open_compute_session")
def test_decision_history_returns_200(mock_session, mock_engine, client):
    mock_rows = [
        _make_score_row(
            {
                "period_date": "2026-04-30",
                "entries_count": 3,
                "exits_count": 2,
                "increases_count": 5,
                "decreases_count": 4,
                "signal_score": 72.5,
                "outcome_score_1m": 65.0,
                "outcome_score_3m": None,
                "decision_state": "Sharp",
            }
        )
    ]
    mock_conn_obj = _mock_conn(mock_rows)
    _make_session_mock(mock_session, mock_conn_obj)

    response = client.get("/api/v1/funds/F0GBR04S23/decision-history")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert "meta" in body
    assert len(body["data"]) == 1
    assert body["meta"]["mstar_id"] == "F0GBR04S23"
    assert "fetched_at" in body["meta"]
    assert "source" in body["meta"]
    assert body["meta"]["source"] == "atlas_fund_decision_scores"


@patch("atlas.api.fund_decisions.get_engine")
@patch("atlas.api.fund_decisions.open_compute_session")
def test_decision_history_404_on_no_data(mock_session, mock_engine, client):
    mock_conn_obj = _mock_conn([])
    _make_session_mock(mock_session, mock_conn_obj)

    response = client.get("/api/v1/funds/NONEXISTENT_FUND/decision-history")
    assert response.status_code == 404


@patch("atlas.api.fund_decisions.get_engine")
@patch("atlas.api.fund_decisions.open_compute_session")
def test_decision_history_limit_param_validates(mock_session, mock_engine, client):
    response = client.get("/api/v1/funds/F001/decision-history?limit=99")
    assert response.status_code == 422  # limit max is 24


@patch("atlas.api.fund_decisions.get_engine")
@patch("atlas.api.fund_decisions.open_compute_session")
def test_decision_detail_invalid_action_returns_422(mock_session, mock_engine, client):
    response = client.get("/api/v1/funds/F001/decisions/2026-04-30?action=buyall")
    assert response.status_code == 422


@patch("atlas.api.fund_decisions.get_engine")
@patch("atlas.api.fund_decisions.open_compute_session")
def test_decision_detail_returns_200_empty(mock_session, mock_engine, client):
    mock_conn_obj = _mock_conn([])
    _make_session_mock(mock_session, mock_conn_obj)

    response = client.get("/api/v1/funds/F0GBR04S23/decisions/2026-04-30")
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["meta"]["count"] == 0
    assert "fetched_at" in body["meta"]
    assert "source" in body["meta"]
    assert body["meta"]["source"] == "atlas_fund_holdings_changes"


@patch("atlas.api.fund_decisions.get_engine")
@patch("atlas.api.fund_decisions.open_compute_session")
def test_decision_detail_action_filter_accepted(mock_session, mock_engine, client):
    mock_conn_obj = _mock_conn([])
    _make_session_mock(mock_session, mock_conn_obj)

    response = client.get("/api/v1/funds/F0GBR04S23/decisions/2026-04-30?action=entry")
    assert response.status_code == 200
