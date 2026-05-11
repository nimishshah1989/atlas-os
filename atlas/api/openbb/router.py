"""SP03: OpenBB sub-package router.

Collected router for all /v1 OpenBB endpoints. Imported by
``atlas/api/__init__.py`` and mounted with ``include_router()``.

Routes registered here:
  GET  /v1/agents.json  — metadata.router
  POST /v1/query        — query.router
"""

from __future__ import annotations

from fastapi import APIRouter

from atlas.api.openbb.metadata import router as metadata_router
from atlas.api.openbb.query import router as query_router

openbb_router = APIRouter()
openbb_router.include_router(metadata_router)
openbb_router.include_router(query_router)

__all__ = ["openbb_router"]
