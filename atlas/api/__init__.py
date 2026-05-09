"""Atlas FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI

from atlas.api.portfolios import router as portfolios_router

app = FastAPI(title="Atlas API", version="0.1.0")
app.include_router(portfolios_router)
