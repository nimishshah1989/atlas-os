"""KiteConnect OAuth endpoints: /api/kite/login + /api/kite/callback.

Both routes are exempt from JWTAuthMiddleware (see atlas.api.auth._EXEMPT_PREFIXES):
  - /api/kite/login   — user has no JWT before authenticating
  - /api/kite/callback — called by Zerodha's redirect, no Atlas JWT present

SP08: KiteConnect OAuth daily token refresh.
"""

from __future__ import annotations

import os
from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from atlas.config import Config
from atlas.intraday.auth import exchange_request_token, store_access_token
from atlas.intraday.notify import send_message_sync

log = structlog.get_logger()

router = APIRouter(prefix="/api/kite", tags=["kite-auth"])

_KITE_LOGIN_BASE = "https://kite.trade/connect/login"


@router.get(
    "/login",
    summary="Redirect to KiteConnect OAuth login",
    response_class=RedirectResponse,
    status_code=302,
    include_in_schema=True,
)
def kite_login() -> RedirectResponse:
    """Redirect the browser to KiteConnect's OAuth login page.

    Reads ``KITE_API_KEY`` from the environment. On success the user is
    sent to Zerodha's login page; Zerodha redirects back to
    ``/api/kite/callback?request_token=...`` on successful auth.

    Returns:
        302 redirect to KiteConnect login URL.

    Raises:
        HTTPException(503): If ``KITE_API_KEY`` is not configured.
    """
    api_key = os.environ.get("KITE_API_KEY")
    if not api_key:
        log.error("kite_login_missing_api_key")
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "kite_not_configured",
                "message": "KITE_API_KEY is not set. Configure it in the server environment.",
                "context": {},
            },
        )

    login_url = f"{_KITE_LOGIN_BASE}?api_key={api_key}&v=3"
    log.info("kite_login_redirect")
    return RedirectResponse(url=login_url, status_code=302)


@router.get(
    "/callback",
    summary="KiteConnect OAuth callback — exchange request_token for access_token",
    response_class=RedirectResponse,
    status_code=302,
    include_in_schema=True,
)
def kite_callback(
    request_token: Annotated[str, Query(description="Short-lived token from Zerodha redirect")],
) -> RedirectResponse:
    """Handle the KiteConnect OAuth callback.

    Zerodha redirects here after successful user login. This endpoint:
    1. Exchanges the ``request_token`` for a long-lived ``access_token``.
    2. Stores the token (encrypted) in ``atlas.atlas_kite_session``.
    3. Fires a Telegram notification confirming the session is live.
    4. Redirects the user to ``/admin``.

    Args:
        request_token: Short-lived OAuth token provided by Zerodha.

    Returns:
        302 redirect to /admin on success.

    Raises:
        HTTPException(500): If token exchange or storage fails.
    """
    try:
        conn_str = Config.assert_db_url()
    except RuntimeError as exc:
        log.error("kite_callback_missing_database_url")
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "server_misconfigured",
                "message": "ATLAS_DB_URL not set.",
                "context": {},
            },
        ) from exc

    try:
        session_data = exchange_request_token(request_token)
        access_token: str = session_data["access_token"]

        store_access_token(access_token, conn_str=conn_str)

        send_message_sync("Kite session active. Token valid until midnight IST.")

        log.info(
            "kite_callback_success",
            # Never log the access token itself — no PII/secrets in logs
            has_token=True,
        )
    except Exception as exc:
        log.error("kite_callback_failed", error=str(exc))
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "token_exchange_failed",
                "message": "Token exchange failed. Check server logs.",
                "context": {},
            },
        ) from exc

    return RedirectResponse(url="/admin", status_code=302)
