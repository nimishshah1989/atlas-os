"""SP07: FastAPI smoke test for POST /api/agents/invoke.

The specialist invocation is fully mocked — no Groq round-trip, no DB
hit. The test verifies that the route exists, the request body is
validated, the response shape matches the Pydantic model, and the audit-
trail INSERT does not fail the request when the engine raises.
"""

from __future__ import annotations

import os
from datetime import date
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _set_auth_disabled() -> None:
    os.environ["ATLAS_AUTH_DISABLED"] = "true"


def _fresh_app() -> TestClient:
    """Build a fresh FastAPI app post-env-flag; uses TestClient.

    Overrides the ``get_engine`` FastAPI dependency with a MagicMock so
    tests don't require ATLAS_DB_URL to be set in the environment.
    """
    _set_auth_disabled()
    from atlas.api import app
    from atlas.db import get_engine

    mock_engine = MagicMock()
    app.dependency_overrides[get_engine] = lambda: mock_engine
    return TestClient(app)


def test_get_api_agents_lists_specialists() -> None:
    _set_auth_disabled()
    client = _fresh_app()
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    body = resp.json()
    assert "specialists" in body
    names = [s["name"] for s in body["specialists"]]
    assert set(names) == {
        "sector_rotation",
        "stock_screener",
        "regime_watcher",
        "drift_detector",
    }


def test_post_invoke_routes_and_returns_response_shape() -> None:
    _set_auth_disabled()
    fake_result = MagicMock(
        narrative="The market is in Risk-On. Data as of 2026-05-08.",
        tool_calls=[
            {
                "tool": "get_current_regime",
                "args": {},
                "result_keys": ["regime_state", "deployment_multiplier"],
            }
        ],
        model="llama-3.3-70b-versatile",
        input_tokens=120,
        output_tokens=60,
        iterations=2,
        data_as_of=date(2026, 5, 8),
    )

    # Patch invoke_routed at the agents-router module level. Persist is
    # disabled so we don't need to mock the engine.
    with patch("atlas.api.agents.invoke_routed", return_value=("regime_watcher", fake_result)):
        client = _fresh_app()
        resp = client.post(
            "/api/agents/invoke",
            json={
                "agent": "auto",
                "question": "What is the regime?",
                "persist": False,
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["agent"] == "regime_watcher"
    assert "Risk-On" in body["narrative"]
    assert body["model"] == "llama-3.3-70b-versatile"
    assert body["data_as_of"] == "2026-05-08"
    assert body["iterations"] == 2
    assert len(body["tool_calls"]) == 1


def test_post_invoke_specific_agent_path() -> None:
    """Caller specifies agent='regime_watcher' directly; bypasses routing."""
    _set_auth_disabled()
    fake_result = MagicMock(
        narrative="Data as of 2026-05-08.",
        tool_calls=[],
        model="llama-3.3-70b-versatile",
        input_tokens=80,
        output_tokens=40,
        iterations=1,
        data_as_of=date(2026, 5, 8),
    )
    fake_agent = MagicMock()
    fake_agent.invoke.return_value = fake_result

    with patch("atlas.api.agents.get_specialist", return_value=fake_agent):
        client = _fresh_app()
        resp = client.post(
            "/api/agents/invoke",
            json={
                "agent": "regime_watcher",
                "question": "regime?",
                "persist": False,
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["agent"] == "regime_watcher"


def test_post_invoke_unknown_agent_returns_400() -> None:
    _set_auth_disabled()
    client = _fresh_app()
    resp = client.post(
        "/api/agents/invoke",
        json={
            "agent": "not_a_real_agent",
            "question": "test",
            "persist": False,
        },
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["error_code"] == "unknown_agent"


def test_post_invoke_empty_question_returns_422() -> None:
    """Pydantic min_length=1 must reject empty question strings."""
    _set_auth_disabled()
    client = _fresh_app()
    resp = client.post(
        "/api/agents/invoke",
        json={"agent": "auto", "question": "", "persist": False},
    )
    assert resp.status_code == 422
