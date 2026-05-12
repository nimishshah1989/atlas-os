"""Unit tests for atlas.api.cts_sectors — mocked DB, no real connection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from atlas.api.cts_sectors import _derive_momentum, router

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_row(**kwargs) -> MagicMock:
    defaults = {
        "sector": "IT",
        "date": "2024-01-15",
        "ppc_count": 5,
        "npc_count": 2,
        "total_tradeable": 20,
        "stage2_count": 8,
        "stage2_pct": 0.4,
        "avg_ppc_conviction": 72.5,
        "action_alert_count": 3,
        "pivot_balance": 0.15,
    }
    defaults.update(kwargs)
    m = MagicMock()
    m._mapping = defaults
    return m


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# _derive_momentum unit tests
# ---------------------------------------------------------------------------


def test_derive_momentum_bullish() -> None:
    assert _derive_momentum(0.10) == "Bullish"
    assert _derive_momentum(0.50) == "Bullish"


def test_derive_momentum_bearish() -> None:
    assert _derive_momentum(-0.10) == "Bearish"
    assert _derive_momentum(-0.99) == "Bearish"


def test_derive_momentum_neutral_near_boundary() -> None:
    assert _derive_momentum(0.09) == "Neutral"
    assert _derive_momentum(-0.09) == "Neutral"
    assert _derive_momentum(0.0) == "Neutral"


def test_derive_momentum_null_returns_neutral() -> None:
    assert _derive_momentum(None) == "Neutral"


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


def test_get_sector_cts_returns_200_with_data(client: TestClient) -> None:
    rows = [_make_row(sector="IT", pivot_balance=0.20)]
    with patch(
        "atlas.api.cts_sectors._fetch_sector_pivot", return_value=[dict(r._mapping) for r in rows]
    ):
        resp = client.get("/api/v1/cts/sectors")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "as_of_date" in body
    assert len(body["data"]) == 1
    assert body["data"][0]["sector"] == "IT"
    assert body["data"][0]["momentum"] == "Bullish"


def test_get_sector_cts_returns_404_when_empty(client: TestClient) -> None:
    with patch("atlas.api.cts_sectors._fetch_sector_pivot", return_value=[]):
        resp = client.get("/api/v1/cts/sectors")
    assert resp.status_code == 404


def test_get_sector_cts_null_pivot_balance_produces_neutral(client: TestClient) -> None:
    row = {
        "sector": "BANK",
        "date": "2024-01-15",
        "ppc_count": 3,
        "npc_count": 3,
        "total_tradeable": 10,
        "stage2_count": 4,
        "stage2_pct": None,
        "avg_ppc_conviction": None,
        "action_alert_count": 0,
        "pivot_balance": None,
    }
    with patch("atlas.api.cts_sectors._fetch_sector_pivot", return_value=[row]):
        resp = client.get("/api/v1/cts/sectors")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"][0]["momentum"] == "Neutral"
    assert body["data"][0]["stage2_pct"] is None
    assert body["data"][0]["avg_ppc_conviction"] is None
    assert body["data"][0]["pivot_balance"] is None


def test_get_sector_cts_bearish_sector(client: TestClient) -> None:
    row = {
        "sector": "PHARMA",
        "date": "2024-02-01",
        "ppc_count": 1,
        "npc_count": 8,
        "total_tradeable": 15,
        "stage2_count": 2,
        "stage2_pct": 0.13,
        "avg_ppc_conviction": 45.0,
        "action_alert_count": 1,
        "pivot_balance": -0.47,
    }
    with patch("atlas.api.cts_sectors._fetch_sector_pivot", return_value=[row]):
        resp = client.get("/api/v1/cts/sectors")
    assert resp.status_code == 200
    assert resp.json()["data"][0]["momentum"] == "Bearish"


def test_get_sector_cts_response_contains_as_of_date(client: TestClient) -> None:
    row = {
        "sector": "FMCG",
        "date": "2024-03-10",
        "ppc_count": 2,
        "npc_count": 1,
        "total_tradeable": 8,
        "stage2_count": 3,
        "stage2_pct": 0.375,
        "avg_ppc_conviction": 60.0,
        "action_alert_count": 0,
        "pivot_balance": 0.125,
    }
    with patch("atlas.api.cts_sectors._fetch_sector_pivot", return_value=[row]):
        resp = client.get("/api/v1/cts/sectors")
    assert resp.status_code == 200
    assert resp.json()["as_of_date"] == "2024-03-10"
