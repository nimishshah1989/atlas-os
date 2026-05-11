"""SP07: REST surface for invoking specialist agents.

Endpoint:
    POST /api/agents/invoke
    GET  /api/agents

Auth: this router is NOT in ``atlas.api.auth._EXEMPT_PREFIXES``. Every
request flows through the JWT middleware. In dev, set
``ATLAS_AUTH_DISABLED=true`` to bypass — the existing pattern.

The endpoint persists every successful invocation to
``atlas.atlas_agent_invocations`` with ``caller='api'``.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.agents.specialists import (
    SEBIComplianceError,
    get_specialist,
    invoke_routed,
    list_specialists,
)
from atlas.agents.specialists.base import AgentResult
from atlas.db import get_engine

log = structlog.get_logger()

router = APIRouter(prefix="/api/agents", tags=["agents"])


class InvokeRequest(BaseModel):
    agent: str = Field(
        default="auto",
        description=(
            "Specialist name or 'auto'. Valid: auto, sector_rotation, "
            "stock_screener, regime_watcher, drift_detector."
        ),
    )
    question: str = Field(min_length=1, max_length=2000)
    persist: bool = Field(
        default=True,
        description="If true, audit-log the invocation to atlas_agent_invocations.",
    )


class ToolCallSummary(BaseModel):
    tool: str
    args: dict[str, Any]
    result_keys: list[str]


class InvokeResponse(BaseModel):
    agent: str
    narrative: str
    tool_calls: list[ToolCallSummary]
    model: str
    input_tokens: int | None
    output_tokens: int | None
    iterations: int
    data_as_of: str | None


class ListResponse(BaseModel):
    specialists: list[dict[str, str]]


@router.get("", summary="List available specialist agents")
def list_agents() -> ListResponse:
    return ListResponse(specialists=list_specialists())


@router.post("/invoke", summary="Invoke a specialist agent")
def invoke_agent(
    body: InvokeRequest,
    request: Request,
    engine: Engine = Depends(get_engine),  # noqa: B008 — FastAPI dependency idiom
) -> InvokeResponse:
    user_id = getattr(getattr(request.state, "user", None), "user_id", None)
    log.info(
        "agents_invoke_request",
        agent=body.agent,
        question_preview=body.question[:80],
        user_id=user_id,
    )

    try:
        if body.agent == "auto":
            agent_name, result = invoke_routed(body.question, engine=engine)
        else:
            try:
                agent = get_specialist(body.agent)
            except KeyError as exc:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error_code": "unknown_agent",
                        "message": str(exc),
                        "context": {"agent": body.agent},
                    },
                ) from exc
            result = agent.invoke(body.question, engine=engine)
            agent_name = body.agent
    except SEBIComplianceError as exc:
        log.warning("agents_sebi_violation", agent=body.agent, err=str(exc))
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "sebi_violation",
                "message": "Specialist output failed the SEBI banned-word scan.",
                "context": {"agent": body.agent},
            },
        ) from exc
    except RuntimeError as exc:
        log.error("agents_runtime_error", agent=body.agent, err=str(exc))
        raise HTTPException(
            status_code=502,
            detail={
                "error_code": "agent_runtime_error",
                "message": str(exc),
                "context": {"agent": body.agent},
            },
        ) from exc

    if body.persist:
        try:
            _persist_invocation(
                engine,
                agent_name=agent_name,
                question=body.question,
                result=result,
                caller="api",
                user_id=user_id,
            )
        except Exception as exc:
            log.warning("agents_persist_failed", err=str(exc))

    return InvokeResponse(
        agent=agent_name,
        narrative=result.narrative,
        tool_calls=[ToolCallSummary(**tc) for tc in result.tool_calls],
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        iterations=result.iterations,
        data_as_of=result.data_as_of.isoformat() if result.data_as_of else None,
    )


def _persist_invocation(
    engine: Engine,
    *,
    agent_name: str,
    question: str,
    result: AgentResult,
    caller: str,
    user_id: str | None,
) -> None:
    """Write the invocation to atlas.atlas_agent_invocations."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO atlas.atlas_agent_invocations (
                    agent_name, question, narrative, tool_calls, model,
                    input_tokens, output_tokens, iterations, data_as_of,
                    caller, user_id
                ) VALUES (
                    :agent_name, :question, :narrative,
                    CAST(:tool_calls AS JSONB),
                    :model, :input_tokens, :output_tokens, :iterations,
                    :data_as_of, :caller, :user_id
                )
                """
            ),
            {
                "agent_name": agent_name,
                "question": question,
                "narrative": result.narrative,
                "tool_calls": json.dumps(result.tool_calls),
                "model": result.model,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "iterations": result.iterations,
                "data_as_of": result.data_as_of,
                "caller": caller,
                "user_id": user_id,
            },
        )
