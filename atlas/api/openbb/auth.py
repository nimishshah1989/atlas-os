"""SP03: API-key authentication for the OpenBB /v1/* routes.

OpenBB Workspace sends ``Authorization: Bearer <api-key>`` where the key is
``OPENBB_BACKEND_API_KEY`` (not a Supabase JWT). The Supabase JWT middleware
skips /v1/* entirely (see ``atlas/api/auth.py`` ``_EXEMPT_PREFIXES``).

This module provides ``verify_api_key`` — a FastAPI ``Depends()`` dependency.
Mount it on the OpenBB router so every /v1 route is protected.

Dev mode: if ``OPENBB_BACKEND_API_KEY`` is empty string, the check is skipped
and a warning is logged. Mirrors the ``ATLAS_AUTH_DISABLED`` pattern.
Never leave the key empty in production.
"""

from __future__ import annotations

import structlog
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from atlas.config import Config

log = structlog.get_logger()

_bearer = HTTPBearer(auto_error=False)


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),  # noqa: B008
) -> None:
    """FastAPI dependency — verifies the OpenBB API key.

    Raises HTTP 401 if:
      - No Authorization header (and key is configured)
      - Token does not match ``OPENBB_BACKEND_API_KEY``

    Passes through silently (dev mode) if ``OPENBB_BACKEND_API_KEY`` is empty.
    """
    expected = Config.OPENBB_BACKEND_API_KEY

    if not expected:
        log.warning(
            "openbb_auth_disabled",
            reason="OPENBB_BACKEND_API_KEY not set — allowing all /v1 requests",
        )
        return

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "openbb_missing_token",
                "message": "Authorization: Bearer <api-key> required for /v1 routes",
                "context": {},
            },
        )

    if credentials.credentials != expected:
        log.warning("openbb_auth_rejected", reason="api_key_mismatch")
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "openbb_invalid_token",
                "message": "Invalid API key",
                "context": {},
            },
        )
