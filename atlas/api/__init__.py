"""Atlas FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI

from atlas.api.portfolios import router as portfolios_router
from atlas.api.portfolios import rule_based_router
from atlas.api.strategies import router as strategies_router

app = FastAPI(title="Atlas API", version="0.1.0")
app.include_router(portfolios_router)
app.include_router(rule_based_router)
app.include_router(strategies_router)
