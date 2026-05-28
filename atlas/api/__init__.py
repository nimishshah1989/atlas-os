"""Atlas FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from atlas.api.admin.proposals import router as admin_proposals_router
from atlas.api.admin.validator import router as admin_validator_router
from atlas.api.agents import router as agents_router
from atlas.api.auth import JWTAuthMiddleware
from atlas.api.cell_defs import router as cell_defs_router
from atlas.api.cts_brief import router as cts_brief_router
from atlas.api.cts_sectors import router as cts_sectors_router
from atlas.api.fund_decisions import router as fund_decisions_router
from atlas.api.instrument import router as instrument_router
from atlas.api.intraday import router as intraday_router
from atlas.api.kite_auth import router as kite_auth_router
from atlas.api.market import router as market_router
from atlas.api.openbb.router import openbb_router
from atlas.api.portfolios import router as portfolios_router
from atlas.api.portfolios import rule_based_router
from atlas.api.rank import router as rank_router
from atlas.api.screen import router as screen_router
from atlas.api.strategies import router as strategies_router
from atlas.api.trading import router as trading_router
from atlas.api.tv_signals import router as tv_signals_router
from atlas.tv.routes import _internal_router as tv_internal_router  # type: ignore[import]
from atlas.tv.routes import _portfolios_router as tv_portfolios_router  # type: ignore[import]
from atlas.tv.routes import router as tv_router  # type: ignore[import]

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
app.include_router(cts_sectors_router)  # SP09 Phase 2: sector CTS snapshot — /api/v1/cts/sectors
app.include_router(tv_signals_router)  # SP10: TV webhook receiver + signal report feed
app.include_router(trading_router)  # Strategy Lab — /api/trading/*
app.include_router(fund_decisions_router)  # MF holdings decision history
app.include_router(openbb_router)  # SP03: OpenBB BYO Copilot — /v1/agents.json + /v1/query
# v6 /v1 endpoints — screen.*, market.regime, cell.definitions, instrument/{iid}, rank.*
app.include_router(screen_router)
app.include_router(market_router)
app.include_router(cell_defs_router)
app.include_router(instrument_router)
app.include_router(rank_router)  # v6 Fund + ETF scorecard ranking (migration 093)
app.include_router(tv_router)  # TV-05: cached TV screener metrics — /v1/tv/metrics/{symbol}
app.include_router(
    tv_internal_router
)  # TV-06: internal pg_cron trigger — /v1/tv/internal/run-screener
app.include_router(
    tv_portfolios_router
)  # TV-08: portfolio analytics — /v1/portfolios/{id}/analytics


@app.get("/health", include_in_schema=False)
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})
