"""Fund manager decision history API endpoints.

GET /api/v1/funds/{mstar_id}/decision-history
GET /api/v1/funds/{mstar_id}/decisions/{period_date}
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from atlas.compute._session import open_compute_session
from atlas.db import get_engine

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/funds", tags=["fund-decisions"])


class DecisionScoreRow(BaseModel):
    period_date: date
    entries_count: int
    exits_count: int
    increases_count: int
    decreases_count: int
    signal_score: float | None = None
    outcome_score_1m: float | None = None
    outcome_score_3m: float | None = None
    decision_state: str | None = None


class DecisionHistoryResponse(BaseModel):
    data: list[DecisionScoreRow]
    meta: dict


class HoldingsChangeRow(BaseModel):
    symbol: str
    action: str
    weight_before: float
    weight_after: float
    weight_delta: float
    rs_state_at_action: str | None = None
    momentum_state_at_action: str | None = None
    signal_quality: str | None = None
    outcome_ret_1m: float | None = None
    outcome_quality_1m: str | None = None
    outcome_ret_3m: float | None = None
    outcome_quality_3m: str | None = None


class DecisionDetailResponse(BaseModel):
    data: list[HoldingsChangeRow]
    meta: dict


@router.get("/{mstar_id}/decision-history", response_model=DecisionHistoryResponse)
def get_decision_history(
    mstar_id: str,
    limit: int = Query(default=12, ge=1, le=24),
) -> DecisionHistoryResponse:
    engine = get_engine()
    with open_compute_session(engine) as conn:
        rows = conn.execute(
            text("""
                SELECT
                    period_date,
                    entries_count, exits_count, increases_count, decreases_count,
                    signal_score::float,
                    outcome_score_1m::float,
                    outcome_score_3m::float,
                    decision_state
                FROM atlas.atlas_fund_decision_scores
                WHERE mstar_id = :mstar_id
                ORDER BY period_date DESC
                LIMIT :limit
            """),
            {"mstar_id": mstar_id, "limit": limit},
        ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No decision history for fund {mstar_id}")

    data = [DecisionScoreRow(**dict(r._mapping)) for r in rows]
    return DecisionHistoryResponse(
        data=data,
        meta={
            "mstar_id": mstar_id,
            "count": len(data),
            "fetched_at": datetime.now(UTC).isoformat(),
            "source": "atlas_fund_decision_scores",
        },
    )


@router.get("/{mstar_id}/decisions/{period_date}", response_model=DecisionDetailResponse)
def get_decision_detail(
    mstar_id: str,
    period_date: date,
    action: str | None = Query(default=None, pattern="^(entry|exit|increase|decrease)$"),
) -> DecisionDetailResponse:
    engine = get_engine()
    action_filter = "AND action = :action" if action else ""

    with open_compute_session(engine) as conn:
        rows = conn.execute(
            text(f"""
                SELECT
                    COALESCE(symbol, instrument_id) AS symbol,
                    action,
                    weight_before::float,
                    weight_after::float,
                    weight_delta::float,
                    rs_state_at_action,
                    momentum_state_at_action,
                    signal_quality,
                    outcome_ret_1m::float,
                    outcome_quality_1m,
                    outcome_ret_3m::float,
                    outcome_quality_3m
                FROM atlas.atlas_fund_holdings_changes
                WHERE mstar_id = :mstar_id
                  AND to_date = :period_date
                  {action_filter}
                ORDER BY ABS(weight_delta) DESC
            """),
            {"mstar_id": mstar_id, "period_date": period_date, "action": action},
        ).fetchall()

    data = [HoldingsChangeRow(**dict(r._mapping)) for r in rows]
    return DecisionDetailResponse(
        data=data,
        meta={
            "mstar_id": mstar_id,
            "period_date": str(period_date),
            "count": len(data),
            "fetched_at": datetime.now(UTC).isoformat(),
            "source": "atlas_fund_holdings_changes",
        },
    )
