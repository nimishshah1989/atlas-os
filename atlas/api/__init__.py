"""Atlas FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from atlas.api.auth import JWTAuthMiddleware
from atlas.api.openbb.router import openbb_router
from atlas.api.portfolios import router as portfolios_router
from atlas.api.portfolios import rule_based_router
from atlas.api.strategies import router as strategies_router

app = FastAPI(title="Atlas API", version="0.1.0")

app.add_middleware(JWTAuthMiddleware)

app.include_router(portfolios_router)
app.include_router(rule_based_router)
app.include_router(strategies_router)
app.include_router(openbb_router)  # SP03: OpenBB BYO Copilot — /v1/agents.json, /v1/query


@app.get("/health", include_in_schema=False)
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})
