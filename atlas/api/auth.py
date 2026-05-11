"""Supabase JWT authentication middleware.

Verifies Bearer tokens against SUPABASE_JWT_SECRET (HS256). Sets
request.state.user with user_id and role on every authenticated request.

Set ATLAS_AUTH_DISABLED=true in .env to bypass verification for local dev.
Never set AUTH_DISABLED in production.

Exempt paths (no token required): /health, /docs, /openapi.json, /redoc
"""

from __future__ import annotations

import jwt
import structlog
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from atlas.config import Config

log = structlog.get_logger()

_EXEMPT_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc", "/v1")


class _User:
    __slots__ = ("user_id", "role")

    def __init__(self, user_id: str, role: str) -> None:
        self.user_id = user_id
        self.role = role


class JWTAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        path = request.url.path
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

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
        try:
            payload: dict = jwt.decode(token, secret, algorithms=["HS256"])  # type: ignore[assignment]
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
