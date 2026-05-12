"""Tests for the admin proposals route. Uses FastAPI TestClient."""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from atlas.db import get_engine
from atlas.intelligence.conviction.optimization.persistence import insert_proposal


@pytest.fixture(scope="module")
def client() -> TestClient:
    # Auth-disable for tests so the middleware sets a dev admin user.
    os.environ["ATLAS_AUTH_DISABLED"] = "true"
    from atlas.api import app

    return TestClient(app)


@pytest.fixture()
def pending_proposal_id():
    eng = get_engine()
    pid = insert_proposal(
        eng,
        {
            "tier": "tier_5_smallcap",
            "regime": "all",
            "proposed_weights": {"ret_6m": Decimal("0.5"), "atr_21": Decimal("0.5")},
            "current_weights": {"ret_6m": Decimal("0.5"), "atr_21": Decimal("0.5")},
            "rationale": "STAGE4A_API_TEST",
        },
    )
    yield pid
    # cleanup any leftover state
    with eng.begin() as c:
        c.execute(
            text(
                "DELETE FROM atlas.atlas_weight_proposals "
                "WHERE rationale LIKE 'STAGE4A_API_TEST%'"
            )
        )


@pytest.mark.integration
class TestProposalsAPI:
    def test_list_returns_pending(self, client: TestClient, pending_proposal_id: str) -> None:
        resp = client.get("/api/admin/proposals")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ids = [p["id"] for p in body["proposals"]]
        assert pending_proposal_id in ids

    def test_reject(self, client: TestClient, pending_proposal_id: str) -> None:
        resp = client.post(
            f"/api/admin/proposals/{pending_proposal_id}/reject",
            json={"notes": "no thanks"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "rejected"

    def test_snooze(self, client: TestClient, pending_proposal_id: str) -> None:
        resp = client.post(
            f"/api/admin/proposals/{pending_proposal_id}/snooze",
            json={"until_date": "2099-12-31", "notes": "wait"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "snoozed"

    def test_double_reject_returns_400(self, client: TestClient, pending_proposal_id: str) -> None:
        # First reject succeeds
        client.post(f"/api/admin/proposals/{pending_proposal_id}/reject", json={})
        # Second reject fails (proposal no longer pending)
        resp = client.post(f"/api/admin/proposals/{pending_proposal_id}/reject", json={})
        assert resp.status_code == 400
        assert (
            "not found" in resp.json()["detail"].lower()
            or "pending" in resp.json()["detail"].lower()
        )

    def test_snooze_validates_date(self, client: TestClient, pending_proposal_id: str) -> None:
        resp = client.post(
            f"/api/admin/proposals/{pending_proposal_id}/snooze",
            json={"until_date": "not-a-date"},
        )
        assert resp.status_code == 422  # pydantic validation
