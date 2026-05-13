"""Tests for GET /v1/agents.json.

Tests: response structure, required fields, API-key auth behaviour.
Uses ``TestClient`` (sync) — no DB needed.
"""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from atlas.api import app

# Default-disable auth — empty key means dev mode in atlas/api/openbb/auth.py
os.environ.setdefault("OPENBB_BACKEND_API_KEY", "")
os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")

client = TestClient(app)


class TestGetAgentsJson:
    def test_returns_200(self) -> None:
        resp = client.get("/v1/agents.json")
        assert resp.status_code == 200

    def test_response_is_json(self) -> None:
        resp = client.get("/v1/agents.json")
        data = resp.json()
        assert isinstance(data, dict)

    def test_has_atlas_key(self) -> None:
        data = client.get("/v1/agents.json").json()
        assert "atlas" in data

    def test_atlas_has_required_fields(self) -> None:
        agent = client.get("/v1/agents.json").json()["atlas"]
        for field in ("name", "description", "endpoints", "features"):
            assert field in agent, f"Missing field: {field}"

    def test_query_endpoint_listed(self) -> None:
        agent = client.get("/v1/agents.json").json()["atlas"]
        assert "query" in agent["endpoints"]
        assert agent["endpoints"]["query"].endswith("/v1/query")

    def test_streaming_feature_true(self) -> None:
        features = client.get("/v1/agents.json").json()["atlas"]["features"]
        assert features.get("streaming") is True

    def test_with_valid_api_key(self) -> None:
        """API key path — valid key returns 200.

        Note: ``atlas.config.Config`` reads ``OPENBB_BACKEND_API_KEY`` at
        import time. We can't reliably mutate it mid-test for TestClient.
        Instead, monkeypatch the Config attribute directly.
        """
        from atlas.config import Config

        original = Config.OPENBB_BACKEND_API_KEY
        try:
            Config.OPENBB_BACKEND_API_KEY = "test-key-abc"
            resp = client.get(
                "/v1/agents.json",
                headers={"Authorization": "Bearer test-key-abc"},
            )
            assert resp.status_code == 200
        finally:
            Config.OPENBB_BACKEND_API_KEY = original

    def test_with_invalid_api_key_returns_401(self) -> None:
        """Invalid key returns 401."""
        from atlas.config import Config

        original = Config.OPENBB_BACKEND_API_KEY
        try:
            Config.OPENBB_BACKEND_API_KEY = "correct-key"
            resp = client.get(
                "/v1/agents.json",
                headers={"Authorization": "Bearer wrong-key"},
            )
            assert resp.status_code == 401
        finally:
            Config.OPENBB_BACKEND_API_KEY = original

    def test_with_missing_api_key_returns_401_when_configured(self) -> None:
        """No Authorization header but key configured -> 401."""
        from atlas.config import Config

        original = Config.OPENBB_BACKEND_API_KEY
        try:
            Config.OPENBB_BACKEND_API_KEY = "configured-key"
            resp = client.get("/v1/agents.json")
            assert resp.status_code == 401
        finally:
            Config.OPENBB_BACKEND_API_KEY = original
