"""Atlas FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from atlas.api.admin.proposals import router as admin_proposals_router
from atlas.api.agents import router as agents_router
from atlas.api.auth import JWTAuthMiddleware
from atlas.api.openbb.router import openbb_router
from atlas.api.portfolios import router as portfolios_router
from atlas.api.portfolios import rule_based_router
from atlas.api.strategies import router as strategies_router

app = FastAPI(title="Atlas API", version="0.1.0")

# CORS for OpenBB Workspace + browser-based clients. Must be added BEFORE
# JWTAuthMiddleware so OPTIONS preflight passes without auth.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://pro.openbb.co", "https://app.openbb.co", "https://openbb.co"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.add_middleware(JWTAuthMiddleware)

app.include_router(portfolios_router)
app.include_router(rule_based_router)
app.include_router(strategies_router)
app.include_router(openbb_router)  # SP03: OpenBB BYO Copilot — /v1/agents.json, /v1/query
app.include_router(agents_router)  # SP07: specialist agents — /api/agents/invoke
app.include_router(admin_proposals_router)  # SP04 Stage 4a — admin proposals


@app.get("/health", include_in_schema=False)
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})
