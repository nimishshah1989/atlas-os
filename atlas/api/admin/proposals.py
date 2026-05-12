"""Admin endpoints for Stage 4a weight-proposal review.

POST /api/admin/proposals/{id}/approve  → atomic apply with smoothing
POST /api/admin/proposals/{id}/reject   → mark rejected
POST /api/admin/proposals/{id}/snooze   → mark snoozed with until_date
GET  /api/admin/proposals               → list pending proposals

All endpoints require role='admin' on the JWT (or ATLAS_AUTH_DISABLED=true
in dev). The role is set by the Supabase JWT and surfaced via
``request.state.user`` by JWTAuthMiddleware.
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from atlas.db import get_engine
from atlas.intelligence.conviction.optimization.persistence import (
    apply_proposal,
    reject_proposal,
    snooze_proposal,
)

log = structlog.get_logger()

router = APIRouter(prefix="/api/admin/proposals", tags=["admin"])


def _require_admin(request: Request) -> str:
    """Pull the admin user_id off request.state. 403 if not admin."""
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="auth required")
    if getattr(user, "role", "") not in ("admin", "service_role"):
        raise HTTPException(status_code=403, detail="admin role required")
    return getattr(user, "user_id", "unknown")


class ApproveBody(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)


class RejectBody(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)


class SnoozeBody(BaseModel):
    until_date: date_cls
    notes: str | None = Field(default=None, max_length=1000)


@router.get("")
async def list_pending_proposals(request: Request) -> dict[str, Any]:
    """Return pending proposals with summary fields. Admin only."""
    _require_admin(request)
    engine = get_engine()
    sql = text("""
        SELECT id::text, tier, regime,
               proposed_holdout_ic, current_holdout_ic, ic_delta,
               rationale, generator_version, status, created_at
        FROM atlas.atlas_weight_proposals
        WHERE status = 'pending'
        ORDER BY created_at DESC
        LIMIT 50
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql).fetchall()
    return {
        "proposals": [
            {
                "id": r[0],
                "tier": r[1],
                "regime": r[2],
                "proposed_holdout_ic": float(r[3]) if r[3] is not None else None,
                "current_holdout_ic": float(r[4]) if r[4] is not None else None,
                "ic_delta": float(r[5]) if r[5] is not None else None,
                "rationale": r[6],
                "generator_version": r[7],
                "status": r[8],
                "created_at": r[9].isoformat() if isinstance(r[9], datetime) else str(r[9]),
            }
            for r in rows
        ],
        "count": len(rows),
    }


@router.post("/{proposal_id}/approve")
async def approve(proposal_id: str, body: ApproveBody, request: Request) -> dict[str, Any]:
    reviewer = _require_admin(request)
    engine = get_engine()
    try:
        blended = apply_proposal(
            engine,
            proposal_id=proposal_id,
            reviewer=reviewer,
            notes=body.notes,
        )
    except RuntimeError as exc:
        log.warning("approve_failed", proposal_id=proposal_id, err=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "approved",
        "proposal_id": proposal_id,
        "applied_weights": {k: str(v) for k, v in blended.items()},
        "reviewer": reviewer,
    }


@router.post("/{proposal_id}/reject")
async def reject(proposal_id: str, body: RejectBody, request: Request) -> dict[str, Any]:
    reviewer = _require_admin(request)
    engine = get_engine()
    try:
        reject_proposal(engine, proposal_id=proposal_id, reviewer=reviewer, notes=body.notes)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "rejected", "proposal_id": proposal_id, "reviewer": reviewer}


@router.post("/{proposal_id}/snooze")
async def snooze(proposal_id: str, body: SnoozeBody, request: Request) -> dict[str, Any]:
    reviewer = _require_admin(request)
    engine = get_engine()
    try:
        snooze_proposal(
            engine,
            proposal_id=proposal_id,
            reviewer=reviewer,
            until_date=body.until_date,
            notes=body.notes,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "snoozed",
        "proposal_id": proposal_id,
        "until_date": body.until_date.isoformat(),
        "reviewer": reviewer,
    }
