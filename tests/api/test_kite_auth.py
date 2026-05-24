"""Tests for atlas/api/kite_auth.py — KiteConnect OAuth endpoints.

Unit tests only: all external calls (KiteConnect, DB, Telegram) are mocked.
No integration / real-network calls.

Pattern: ATLAS_AUTH_DISABLED=true so JWTAuthMiddleware skips token checks
(both /api/kite/* paths are also in _EXEMPT_PREFIXES, but disabling auth
avoids any edge cases with the TestClient).
"""

from __future__ import annotations

import os

os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from atlas.api import app
from atlas.config import Config


@pytest.fixture(scope="module")
def client() -> TestClient:
    Config.AUTH_DISABLED = True
    return TestClient(app, follow_redirects=False)


# ---------------------------------------------------------------------------
# /api/kite/login
# ---------------------------------------------------------------------------


class TestKiteLogin:
    def test_kite_login_missing_api_key_returns_503(self, client: TestClient) -> None:
        """503 when KITE_API_KEY env var is absent."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KITE_API_KEY", None)
            response = client.get("/api/kite/login")
        assert response.status_code == 503
        body = response.json()
        assert body["detail"]["error_code"] == "kite_not_configured"

    def test_kite_login_with_api_key_redirects_302(self, client: TestClient) -> None:
        """302 redirect to Zerodha login URL when KITE_API_KEY is set."""
        with patch.dict(os.environ, {"KITE_API_KEY": "test_key_abc123"}):
            response = client.get("/api/kite/login")
        assert response.status_code == 302
        location = response.headers["location"]
        assert "kite.trade/connect/login" in location
        assert "api_key=test_key_abc123" in location
        assert "v=3" in location

    def test_kite_login_redirect_url_format(self, client: TestClient) -> None:
        """Redirect URL includes all required KiteConnect query params."""
        with patch.dict(os.environ, {"KITE_API_KEY": "myapikey"}):
            response = client.get("/api/kite/login")
        location = response.headers["location"]
        assert location == "https://kite.trade/connect/login?api_key=myapikey&v=3"


# ---------------------------------------------------------------------------
# /api/kite/callback
# ---------------------------------------------------------------------------


class TestKiteCallback:
    def test_kite_callback_missing_database_url_returns_500(self, client: TestClient) -> None:
        """500 when ATLAS_DB_URL is not configured."""
        with patch.dict(os.environ, {"KITE_API_KEY": "k", "KITE_API_SECRET": "s"}, clear=False):
            with patch.object(Config, "DB_URL", ""):
                response = client.get("/api/kite/callback?request_token=tok123")
        assert response.status_code == 500
        body = response.json()
        assert body["detail"]["error_code"] == "server_misconfigured"

    def test_kite_callback_exchange_failure_returns_500(self, client: TestClient) -> None:
        """500 when exchange_request_token raises RuntimeError."""
        with patch.dict(os.environ, {"KITE_API_KEY": "k", "KITE_API_SECRET": "s"}):
            with patch.object(Config, "DB_URL", "postgresql://x"):
                with patch(
                    "atlas.api.kite_auth.exchange_request_token",
                    side_effect=RuntimeError("KiteConnect error"),
                ):
                    response = client.get("/api/kite/callback?request_token=badtoken")
        assert response.status_code == 500
        body = response.json()
        assert body["detail"]["error_code"] == "token_exchange_failed"

    def test_kite_callback_success_redirects_to_admin(self, client: TestClient) -> None:
        """On successful token exchange: stores token, notifies, redirects to /admin."""
        fake_session = {"access_token": "live_token_xyz", "login_time": "", "user_id": "u1"}

        with patch.dict(
            os.environ,
            {
                "KITE_API_KEY": "k",
                "KITE_API_SECRET": "s",
                "KITE_TOKEN_ENCRYPTION_KEY": "secret_enc_key",
            },
        ):
            with patch.object(Config, "DB_URL", "postgresql://localhost/atlas"):
                with patch(
                    "atlas.api.kite_auth.exchange_request_token", return_value=fake_session
                ) as mock_exchange:
                    with patch("atlas.api.kite_auth.store_access_token") as mock_store:
                        with patch("atlas.api.kite_auth.send_message_sync") as mock_notify:
                            response = client.get("/api/kite/callback?request_token=validtoken123")

        assert response.status_code == 302
        assert response.headers["location"] == "/admin"

        mock_exchange.assert_called_once_with("validtoken123")
        mock_store.assert_called_once_with(
            "live_token_xyz",
            conn_str="postgresql://localhost/atlas",
        )
        mock_notify.assert_called_once()
        # Verify Telegram message mentions session/token
        notify_arg: str = mock_notify.call_args[0][0]
        assert "Kite session" in notify_arg or "Token" in notify_arg

    def test_kite_callback_missing_request_token_param_returns_422(
        self, client: TestClient
    ) -> None:
        """422 when required request_token query param is absent."""
        response = client.get("/api/kite/callback")
        assert response.status_code == 422

    def test_kite_callback_store_failure_returns_500(self, client: TestClient) -> None:
        """500 when store_access_token raises (e.g. DB down)."""
        fake_session = {"access_token": "tok", "login_time": "", "user_id": "u1"}

        with patch.dict(os.environ, {"KITE_API_KEY": "k"}):
            with patch.object(Config, "DB_URL", "postgresql://x"):
                with patch("atlas.api.kite_auth.exchange_request_token", return_value=fake_session):
                    with patch(
                        "atlas.api.kite_auth.store_access_token",
                        side_effect=OSError("DB connection refused"),
                    ):
                        response = client.get("/api/kite/callback?request_token=tok123")

        assert response.status_code == 500
        body = response.json()
        assert body["detail"]["error_code"] == "token_exchange_failed"


# ---------------------------------------------------------------------------
# JWT exemption verification
# ---------------------------------------------------------------------------


class TestKiteJWTExemption:
    def test_login_route_in_exempt_prefixes(self) -> None:
        """Both kite paths appear in auth.py _EXEMPT_PREFIXES."""
        from atlas.api.auth import _EXEMPT_PREFIXES

        assert "/api/kite/login" in _EXEMPT_PREFIXES
        assert "/api/kite/callback" in _EXEMPT_PREFIXES
