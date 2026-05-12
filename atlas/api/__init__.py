"""Atlas FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from atlas.api.admin.proposals import router as admin_proposals_router
from atlas.api.admin.validator import router as admin_validator_router
from atlas.api.agents import router as agents_router
from atlas.api.auth import JWTAuthMiddleware
from atlas.api.cts_brief import router as cts_brief_router
from atlas.api.intraday import router as intraday_router
from atlas.api.kite_auth import router as kite_auth_router
from atlas.api.portfolios import router as portfolios_router
from atlas.api.portfolios import rule_based_router
from atlas.api.strategies import router as strategies_router

app = FastAPI(title="Atlas API", version="0.1.0")

# CORS — must be added BEFORE JWTAuthMiddleware so OPTIONS preflight passes without auth.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://atlas.jslwealth.in"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.add_middleware(JWTAuthMiddleware)

app.include_router(portfolios_router)
app.include_router(rule_based_router)
app.include_router(strategies_router)
app.include_router(agents_router)  # SP07: specialist agents — /api/agents/invoke
app.include_router(admin_proposals_router)  # SP04 Stage 4a — admin proposals
app.include_router(admin_validator_router)  # Phase C — validator runs + findings
app.include_router(kite_auth_router)  # SP08: KiteConnect OAuth — /api/kite/*
app.include_router(intraday_router)  # SP08: intraday data — /api/v1/intraday/*
app.include_router(
    cts_brief_router
)  # SP09: CTS on-demand brief — /api/v1/stocks/{symbol}/cts_brief


@app.get("/health", include_in_schema=False)
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})
