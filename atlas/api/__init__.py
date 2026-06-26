"""Atlas FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from atlas.api.auth import JWTAuthMiddleware
from atlas.api.instrument import router as instrument_router
from atlas.api.intraday import router as intraday_router
from atlas.api.kite_auth import router as kite_auth_router
from atlas.api.market import router as market_router
from atlas.api.rank import router as rank_router
from atlas.api.screen import router as screen_router
from atlas.tv.routes import _internal_router as tv_internal_router  # type: ignore[import]
from atlas.tv.routes import _portfolios_router as tv_portfolios_router  # type: ignore[import]
from atlas.tv.routes import _stocks_router as tv_stocks_router  # type: ignore[import]
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

# v4 surface — Kite auth + intraday + the v6 /v1 read endpoints the board uses.
app.include_router(kite_auth_router)  # KiteConnect OAuth — /api/kite/*
app.include_router(intraday_router)  # intraday data — /api/v1/intraday/*
app.include_router(screen_router)
app.include_router(market_router)
app.include_router(instrument_router)
app.include_router(rank_router)  # Fund + ETF scorecard ranking
app.include_router(tv_router)  # cached TV screener metrics — /v1/tv/metrics/{symbol}
app.include_router(tv_internal_router)  # internal pg_cron trigger — /v1/tv/internal/run-screener
app.include_router(tv_portfolios_router)  # portfolio analytics — /v1/portfolios/{id}/analytics
app.include_router(tv_stocks_router)  # stock detail — /v1/stocks/{symbol}/rs-ratios + peer-matrix


@app.get("/health", include_in_schema=False)
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})
