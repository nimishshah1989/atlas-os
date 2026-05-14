"""Supabase JWT authentication middleware.

Verifies Bearer tokens against SUPABASE_JWT_SECRET (HS256). Sets
request.state.user with user_id and role on every authenticated request.

Set ATLAS_AUTH_DISABLED=true in .env to bypass verification for local dev.
Never set AUTH_DISABLED in production.

Exempt paths (no token required): /health, /docs, /openapi.json, /redoc,
/api/kite/login, /api/kite/callback

Service-token paths (ATLAS_INTERNAL_SECRET bearer required):
/api/v1/intraday/* — called only by the Next.js proxy, never by browser clients
"""

from __future__ import annotations

import secrets

import jwt
import structlog
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from atlas.config import Config

log = structlog.get_logger()

_EXEMPT_PREFIXES = (
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/kite/login",  # SP08: KiteConnect OAuth — no user JWT at this point
    "/api/kite/callback",  # SP08: Zerodha redirect — called without our JWT
)

# Exact-path exemptions — use when startswith would over-match siblings.
# /api/v1/tv/signal is exempt (TV webhooks can't send Bearer tokens; validated by body secret).
# /api/v1/tv/generate-report is exempt (validated by X-Internal-Secret header).
# /api/v1/tv/signals and /api/v1/tv/signals/{id} remain under JWT auth.
_EXEMPT_EXACT: frozenset[str] = frozenset(
    {
        "/api/v1/tv/signal",
        "/api/v1/tv/generate-report",
    }
)

_SERVICE_TOKEN_PREFIXES = ("/api/v1/intraday",)


class _User:
    __slots__ = ("role", "user_id")

    def __init__(self, user_id: str, role: str) -> None:
        self.user_id = user_id
        self.role = role


async def _check_service_token(request: Request, call_next) -> Response:  # type: ignore[misc]
    """Validate ATLAS_INTERNAL_SECRET for service-to-service routes."""
    expected = Config.ATLAS_INTERNAL_SECRET
    if not expected:
        log.error("atlas_internal_secret_not_configured")
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "server_misconfigured",
                "message": "ATLAS_INTERNAL_SECRET is not set on the server.",
                "context": {},
            },
        )
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return _unauthorized("missing_token", "Service token required")
    token = auth_header[7:]
    if not secrets.compare_digest(token.encode(), expected.encode()):
        log.warning("service_token_invalid", path=request.url.path)
        return _unauthorized("invalid_service_token", "Invalid service token")
    request.state.user = _User(user_id="service:intraday", role="service")
    return await call_next(request)


class JWTAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        path = request.url.path
        if path in _EXEMPT_EXACT or any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        if any(path.startswith(p) for p in _SERVICE_TOKEN_PREFIXES):
            return await _check_service_token(request, call_next)

        if Config.AUTH_DISABLED:
            request.state.user = _User(user_id="dev-user", role="admin")
            return await call_next(request)

        secret = Config.SUPABASE_JWT_SECRET
        if not secret:
            log.error("supabase_jwt_secret_not_configured")
            return JSONResponse(
                status_code=500,
                content={
                    "error_code": "auth_misconfigured",
                    "message": "Server auth is not configured",
                    "context": {},
                },
            )

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _unauthorized("missing_token", "Authorization: Bearer <token> required")

        token = auth_header[7:]
        decode_kwargs: dict = {"algorithms": ["HS256"]}
        if Config.SUPABASE_JWT_AUDIENCE:
            decode_kwargs["audience"] = Config.SUPABASE_JWT_AUDIENCE
        if Config.SUPABASE_JWT_ISSUER:
            decode_kwargs["issuer"] = Config.SUPABASE_JWT_ISSUER
        try:
            payload: dict = jwt.decode(token, secret, **decode_kwargs)  # type: ignore[assignment]
        except jwt.ExpiredSignatureError:
            return _unauthorized("token_expired", "Token has expired")
        except jwt.InvalidTokenError as exc:
            log.info("jwt_invalid", detail=str(exc))
            return _unauthorized("invalid_token", "Invalid token")

        user_id: str = payload.get("sub", "")
        role: str = payload.get("role", "authenticated")
        if not user_id:
            return _unauthorized("missing_sub", "Token is missing subject claim")

        request.state.user = _User(user_id=user_id, role=role)
        return await call_next(request)


def _unauthorized(error_code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"error_code": error_code, "message": message, "context": {}},
    )
