"""M15 strategy re-run backtest endpoint.

Endpoint:
- POST /api/strategies/{id}/backtest  — trigger a fresh backtest for an existing
  strategy with a custom date range + initial capital. Returns 202 immediately
  with a run_id; the UI polls atlas.atlas_pipeline_runs by run_id.

Concurrency guard: 409 if another backtest is already queued or in-flight
(script_name 'backtest_engine', status IN ('queued','running'),
started_at > NOW() - INTERVAL '30 minutes').

The endpoint inserts status='queued' (not 'running') so the row is honest about
the actual state — no subprocess is spawned here. A background worker picks up
queued rows and transitions them to running → success/failed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger()
router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class ReRunBacktestRequest(BaseModel):
    start_date: date
    end_date: date
    initial_capital: int  # in INR

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:  # type: ignore[type-arg]
        start = info.data.get("start_date")
        if start and v <= start:
            raise ValueError("end_date must be after start_date")
        return v

    @field_validator("initial_capital")
    @classmethod
    def positive_capital(cls, v: int) -> int:
        if v < 100_000:
            raise ValueError("initial_capital must be >= 100000 INR")
        return v


@router.post("/{strategy_id}/backtest", status_code=202)
def trigger_backtest_rerun(
    strategy_id: uuid.UUID,
    body: ReRunBacktestRequest,
    engine: Engine = Depends(get_engine),  # noqa: B008
) -> dict:  # type: ignore[type-arg]
    """Trigger a fresh backtest for an existing strategy with a new date range.

    Returns 202 with a compute_run_id immediately; the backtest runs in
    background. UI polls atlas.atlas_pipeline_runs by run_id.
    """
    # Concurrency guard — same pattern as M13 internal_recompute
    with engine.connect() as conn:
        # Check strategy exists
        row = conn.execute(
            text("SELECT id FROM atlas.strategy_configs WHERE id = :id LIMIT 1"),
            {"id": str(strategy_id)},
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error_code": "strategy_not_found",
                    "message": f"strategy_id {strategy_id} not found",
                    "context": {},
                },
            )
        # Check no in-flight or queued backtest (any strategy, per spec AD4)
        existing = conn.execute(
            text("""
                SELECT run_id FROM atlas.atlas_pipeline_runs
                WHERE script_name = 'backtest_engine'
                  AND status IN ('queued', 'running')
                  AND started_at > NOW() - INTERVAL '30 minutes'
                ORDER BY started_at DESC LIMIT 1
            """),
        ).fetchone()
        if existing:
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "already_running",
                    "message": "A backtest is already in progress",
                    "context": {"run_id": str(existing[0])},
                },
            )

    new_run_id = uuid.uuid4()
    fetched_at = datetime.now(UTC).isoformat()

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO atlas.atlas_pipeline_runs
                  (run_id, script_name, milestone, started_at, status, host, git_sha)
                VALUES
                  (:rid, 'backtest_engine', 'M15', NOW(), 'queued', 'api', NULL)
            """),
            {"rid": str(new_run_id)},
        )
    log.info(
        "backtest_rerun_queued",
        compute_run_id=str(new_run_id),
        strategy_id=str(strategy_id),
        start_date=body.start_date.isoformat(),
        end_date=body.end_date.isoformat(),
        initial_capital=body.initial_capital,
    )
    return {
        "data": {
            "compute_run_id": str(new_run_id),
            "strategy_id": str(strategy_id),
            "status": "queued",
        },
        "meta": {
            "data_as_of": fetched_at,
            "fetched_at": fetched_at,
            "source": "atlas-api",
        },
    }
