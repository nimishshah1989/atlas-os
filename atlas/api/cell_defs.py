"""v6 /v1/cell.definitions endpoint.

Lists every active cell from atlas_cell_definitions plus the top-K
runner-ups from atlas_cell_rule_candidates, with ELI5 text.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from atlas.db import get_engine

log = structlog.get_logger()

router = APIRouter(prefix="/v1", tags=["cells"])


class CellCandidate(BaseModel):
    candidate_id: str
    rank: int
    archetype: str
    ic: Decimal | None
    friction_adjusted_excess: Decimal | None
    bh_q_value: Decimal | None
    eli5: str | None


class CellDefinition(BaseModel):
    cell_id: str
    cap_tier: str
    action: str
    tenure: str
    methodology_lock_ref: str
    confidence_unconditional: Decimal | None
    friction_adjusted_excess: Decimal | None
    drift_status: str
    rule_dsl: dict[str, Any]
    candidates: list[CellCandidate]


class CellDefinitionsResponse(BaseModel):
    data: list[CellDefinition]
    meta: dict[str, Any]


_CELLS_SQL = text(
    """
    SELECT
        cell_id::text AS cell_id,
        cap_tier::text AS cap_tier,
        action::text AS action,
        tenure::text AS tenure,
        methodology_lock_ref,
        confidence_unconditional,
        friction_adjusted_excess,
        drift_status::text AS drift_status,
        rule_dsl
    FROM atlas.atlas_cell_definitions
    WHERE deprecated_at IS NULL
    ORDER BY cap_tier, tenure, action
    """
)


_CANDIDATES_SQL = text(
    """
    SELECT
        id::text AS candidate_id,
        cell_definition_id::text AS cell_definition_id,
        rank,
        archetype,
        ic,
        friction_adjusted_excess,
        bh_q_value,
        eli5
    FROM atlas.atlas_cell_rule_candidates
    WHERE cell_definition_id::text = ANY(:cell_ids)
    ORDER BY cell_definition_id, rank
    """
)


@router.get("/cell.definitions", response_model=CellDefinitionsResponse)
def cell_definitions(
    top_k: Annotated[int, Query(ge=1, le=20)] = 5,
) -> CellDefinitionsResponse:
    """Return every active cell with its top-K candidate runner-ups."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            cell_rows = conn.execute(_CELLS_SQL).mappings().all()
            if not cell_rows:
                return CellDefinitionsResponse(
                    data=[],
                    meta={
                        "fetched_at": datetime.now(UTC).isoformat(),
                        "degraded": True,
                        "note": "no cell_definitions rows yet",
                    },
                )
            cell_ids = [r["cell_id"] for r in cell_rows]
            candidate_rows = conn.execute(_CANDIDATES_SQL, {"cell_ids": cell_ids}).mappings().all()
    except OperationalError as exc:
        log.warning("cell_definitions_db_unavailable", error=str(exc))
        raise HTTPException(status_code=503, detail="database unavailable") from exc

    cands_by_cell: dict[str, list[CellCandidate]] = {}
    for c in candidate_rows:
        if c["rank"] > top_k:
            continue
        cands_by_cell.setdefault(c["cell_definition_id"], []).append(
            CellCandidate(
                candidate_id=c["candidate_id"],
                rank=c["rank"],
                archetype=c["archetype"],
                ic=c["ic"],
                friction_adjusted_excess=c["friction_adjusted_excess"],
                bh_q_value=c["bh_q_value"],
                eli5=c["eli5"],
            )
        )
    data = [
        CellDefinition(
            cell_id=r["cell_id"],
            cap_tier=r["cap_tier"],
            action=r["action"],
            tenure=r["tenure"],
            methodology_lock_ref=r["methodology_lock_ref"],
            confidence_unconditional=r["confidence_unconditional"],
            friction_adjusted_excess=r["friction_adjusted_excess"],
            drift_status=r["drift_status"],
            rule_dsl=r["rule_dsl"] if isinstance(r["rule_dsl"], dict) else {},
            candidates=cands_by_cell.get(r["cell_id"], []),
        )
        for r in cell_rows
    ]
    return CellDefinitionsResponse(
        data=data,
        meta={
            "fetched_at": datetime.now(UTC).isoformat(),
            "n_cells": len(data),
            "top_k": top_k,
        },
    )
