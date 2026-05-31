"""Phase C Validator API — run listing and finding queries.

Endpoints:
    GET /api/admin/validator/runs
        List recent validator runs (all scopes), most-recent first.
        Query params: limit (default 20, max 100), scope (optional filter).

    GET /api/admin/validator/findings
        Query validator findings with filtering.
        Query params: run_id, severity, finding_class, surface, limit.

Admin-only: uses the same ``_require_admin`` guard as proposals.py.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import text

router = APIRouter(prefix="/api/admin/validator", tags=["admin"])


def _require_admin(request: Request) -> str:
    """Authorize via JWT or internal secret. Returns reviewer label."""
    user = getattr(request.state, "user", None)
    if user is not None and getattr(user, "role", "") in ("admin", "service_role"):
        return getattr(user, "user_id", "unknown")

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        secret = os.environ.get("ATLAS_INTERNAL_SECRET", "")
        if secret and token == secret:
            return "internal-proxy"

    if user is None:
        raise HTTPException(status_code=401, detail="auth required")
    raise HTTPException(status_code=403, detail="admin role required")


@router.get("/runs")
async def list_runs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    scope: str | None = Query(default=None),
) -> dict[str, Any]:
    """List recent validator runs.

    Args:
        limit: Max runs to return.
        scope: Filter by scope (sensibility, schema_coverage, frontend_diff).
    """
    _require_admin(request)

    from atlas.db import get_engine

    engine = get_engine()
    scope_clause = "AND scope = :scope" if scope else ""

    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT id, started_at, completed_at, status, scope, n_findings
                FROM atlas.atlas_validator_runs
                WHERE 1=1 {scope_clause}
                ORDER BY started_at DESC
                LIMIT :limit
            """),
            {"scope": scope, "limit": limit} if scope else {"limit": limit},
        ).fetchall()

    return {
        "data": [
            {
                "id": str(r[0]),
                "started_at": r[1].isoformat() if r[1] else None,
                "completed_at": r[2].isoformat() if r[2] else None,
                "status": r[3],
                "scope": r[4],
                "n_findings": r[5],
            }
            for r in rows
        ],
        "meta": {"count": len(rows)},
    }


@router.get("/findings")
async def list_findings(
    request: Request,
    run_id: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    finding_class: str | None = Query(default=None),
    surface: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    """List validator findings with optional filters.

    Args:
        run_id: Filter by run UUID.
        severity: Filter by severity (P0, P1, P2, P3).
        finding_class: Filter by class (frontend_diff, insensible_value, etc.).
        surface: Filter by surface (e.g. 'stock.conviction_score').
        limit: Max findings to return.
    """
    _require_admin(request)

    from atlas.db import get_engine

    engine = get_engine()

    clauses: list[str] = []
    params: dict[str, Any] = {"limit": limit}

    if run_id:
        clauses.append("run_id = :run_id")
        params["run_id"] = run_id
    if severity:
        clauses.append("severity = :severity")
        params["severity"] = severity
    if finding_class:
        clauses.append("finding_class = :finding_class")
        params["finding_class"] = finding_class
    if surface:
        clauses.append("surface ILIKE :surface")
        params["surface"] = f"%{surface}%"

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT id, run_id, finding_class, severity, route, surface,
                       identifier, expected_value, actual_value,
                       delta_abs, delta_pct,
                       first_seen, last_seen
                FROM atlas.atlas_validator_findings
                {where}
                ORDER BY severity ASC, last_seen DESC
                LIMIT :limit
            """),
            params,
        ).fetchall()

    return {
        "data": [
            {
                "id": str(r[0]),
                "run_id": str(r[1]),
                "finding_class": r[2],
                "severity": r[3],
                "route": r[4],
                "surface": r[5],
                "identifier": r[6],
                "expected_value": r[7],
                "actual_value": r[8],
                "delta_abs": str(r[9]) if r[9] is not None else None,
                "delta_pct": str(r[10]) if r[10] is not None else None,
                "first_seen": r[11].isoformat() if r[11] else None,
                "last_seen": r[12].isoformat() if r[12] else None,
            }
            for r in rows
        ],
        "meta": {"count": len(rows)},
    }
