"""Custom portfolio API endpoints.

Sync route handlers (consistent with the rest of this repo). All SQL is
parameterized via SQLAlchemy ``text()`` — no f-strings on user input.

Endpoints:
- POST   /api/portfolios/custom              create + trigger background backtest
- GET    /api/portfolios/custom/{id}/status  poll for backtest completion
- GET    /api/portfolios/custom/{id}         full portfolio detail incl. backtest
- GET    /api/portfolios/custom              list all custom portfolios
- POST   /api/portfolios/rule-based          FM-authored rule-based portfolio (M15)
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.api._rule_allowlist import ConfigValidationError, validate_config
from atlas.compute import open_compute_session
from atlas.db import get_engine
from atlas.simulation.custom import InstrumentWeight, create_custom_portfolio

router = APIRouter(prefix="/api/portfolios/custom", tags=["custom-portfolio"])

# Separate router for rule-based portfolios (different URL prefix)
rule_based_router = APIRouter(prefix="/api/portfolios", tags=["rule-based-portfolio"])


class InstrumentWeightRequest(BaseModel):
    instrument_id: str
    instrument_type: str
    weight_pct: float


class CreatePortfolioRequest(BaseModel):
    name: str
    instruments: list[InstrumentWeightRequest]


@router.post("", status_code=201)
def create_portfolio(
    body: CreatePortfolioRequest,
    engine: Engine = Depends(get_engine),  # noqa: B008 — FastAPI dependency idiom
) -> dict[str, str]:
    """Validate, save, and trigger a background backtest.

    Returns ``{"portfolio_id": ..., "status": "pending"}`` immediately. The
    backtest runs in a separate process (see
    :func:`atlas.simulation.custom.portfolio.create_custom_portfolio`).
    Validation failures from the orchestrator surface as HTTP 422.
    """
    instruments = [
        InstrumentWeight(i.instrument_id, i.instrument_type, i.weight_pct) for i in body.instruments
    ]
    try:
        portfolio_id = create_custom_portfolio(body.name, instruments, engine)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"portfolio_id": portfolio_id, "status": "pending"}


@router.get("/{portfolio_id}/status")
def get_portfolio_status(
    portfolio_id: str,
    engine: Engine = Depends(get_engine),  # noqa: B008 — FastAPI dependency idiom
) -> dict[str, Any]:
    """Polling endpoint — returns ``pending`` until backtest_id is populated."""
    with open_compute_session(engine) as conn:
        row = conn.execute(
            text(
                "SELECT backtest_id::text, updated_at "
                "FROM atlas.strategy_fm_custom_portfolios WHERE id = :pid"
            ),
            {"pid": portfolio_id},
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    if row.backtest_id is None:
        return {
            "portfolio_id": portfolio_id,
            "status": "pending",
            "backtest_id": None,
        }
    return {
        "portfolio_id": portfolio_id,
        "status": "complete",
        "backtest_id": row.backtest_id,
    }


@router.get("/{portfolio_id}")
def get_portfolio(
    portfolio_id: str,
    engine: Engine = Depends(get_engine),  # noqa: B008 — FastAPI dependency idiom
) -> dict[str, Any]:
    """Full portfolio detail, joined with backtest results when available."""
    with open_compute_session(engine) as conn:
        row = conn.execute(
            text(
                """
                SELECT p.id::text, p.name, p.instruments, p.paper_trading_active,
                       p.backtest_id::text, p.created_at,
                       b.sharpe_ratio, b.max_drawdown, b.total_return,
                       b.start_date, b.end_date
                FROM atlas.strategy_fm_custom_portfolios p
                LEFT JOIN atlas.strategy_backtest_results b ON b.id = p.backtest_id
                WHERE p.id = :pid
                """
            ),
            {"pid": portfolio_id},
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    backtest_block: dict[str, Any] | None = None
    if row[4]:
        backtest_block = {
            "sharpe_ratio": float(row[6]) if row[6] is not None else None,
            "max_drawdown": float(row[7]) if row[7] is not None else None,
            "total_return": float(row[8]) if row[8] is not None else None,
            "start_date": str(row[9]) if row[9] is not None else None,
            "end_date": str(row[10]) if row[10] is not None else None,
        }

    return {
        "id": row[0],
        "name": row[1],
        "instruments": row[2],
        "paper_trading_active": row[3],
        "backtest_id": row[4],
        "created_at": str(row[5]),
        "backtest": backtest_block,
    }


@router.get("")
def list_portfolios(
    engine: Engine = Depends(get_engine),  # noqa: B008 — FastAPI dependency idiom
) -> list[dict[str, Any]]:
    """List all custom portfolios with status, newest first."""
    with open_compute_session(engine) as conn:
        rows = conn.execute(
            text(
                "SELECT id::text, name, backtest_id::text, paper_trading_active, "
                "created_at FROM atlas.strategy_fm_custom_portfolios "
                "ORDER BY created_at DESC"
            )
        ).fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "status": "complete" if r[2] else "pending",
            "backtest_id": r[2],
            "paper_trading_active": r[3],
            "created_at": str(r[4]),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Rule-based portfolio endpoints (M15)
# ---------------------------------------------------------------------------


class RuleBasedPortfolioRequest(BaseModel):
    name: str
    description: str | None = None
    config: dict  # type: ignore[type-arg]


@rule_based_router.post("/rule-based", status_code=201)
def create_rule_based_portfolio(
    body: RuleBasedPortfolioRequest,
    engine: Engine = Depends(get_engine),  # noqa: B008
) -> dict:  # type: ignore[type-arg]
    """Create an FM-authored rule-based portfolio (lives in strategy_configs).

    Validates config against the _rule_allowlist security boundary, then
    INSERTs into atlas.strategy_configs with is_fm_authored=TRUE.
    The audit trigger (migration 025) captures the creation context.
    Returns 201 with strategy_id + status.
    """
    try:
        validate_config(body.config)
    except ConfigValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "invalid_config",
                "message": str(exc),
                "context": {},
            },
        ) from exc

    if not body.name.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "name_required",
                "message": "name is required",
                "context": {},
            },
        )

    new_strategy_id = uuid.uuid4()
    with engine.begin() as conn:
        reason = body.description or "FM-authored rule-based portfolio creation"
        conn.execute(text("SET LOCAL atlas.change_reason = :r"), {"r": reason})
        conn.execute(
            text("""
                INSERT INTO atlas.strategy_configs
                  (id, name, tier, archetype, variant, config,
                   is_active, is_fm_authored, created_by)
                VALUES
                  (:id, :name, 'fm', 'fm_authored', 'custom',
                   CAST(:cfg AS jsonb), TRUE, TRUE, 'fund-manager')
            """),
            {
                "id": str(new_strategy_id),
                "name": body.name.strip(),
                "cfg": json.dumps(body.config),
            },
        )
    return {
        "data": {
            "strategy_id": str(new_strategy_id),
            "name": body.name.strip(),
            "status": "created",
        },
        "meta": {"source": "atlas-api"},
    }
