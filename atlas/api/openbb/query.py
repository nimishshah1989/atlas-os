"""SP03: POST /v1/query — OpenBB BYO Copilot streaming query endpoint.

Accepts a ``QueryRequest`` (conversation history + optional widget/context),
classifies the last user message intent, dispatches to the matching handler,
and streams the handler's SSE events via ``sse-starlette`` ``EventSourceResponse``.

Unknown intents get a ``message_chunk`` with usage hints — no error, no 4xx.
OpenBB Workspace expects a 200 with SSE stream even for unrecognised queries.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.engine import Engine
from sse_starlette.sse import EventSourceResponse

from atlas.api.openbb.auth import verify_api_key
from atlas.api.openbb.events import done, message_chunk
from atlas.api.openbb.handlers import HANDLER_DISPATCH
from atlas.api.openbb.handlers.router import classify_intent
from atlas.api.openbb.schemas import QueryRequest
from atlas.db import get_engine

log = structlog.get_logger()

router = APIRouter()

_FALLBACK_MESSAGE = (
    "I can help with the following Atlas research queries:\n\n"
    '- **Market regime**: "What is the current market regime?" or "show me regime"\n'
    '- **RS leaders**: "Top RS stocks" or "leading stocks in IT"\n'
    '- **Sector rotation**: "Sector rotation" or "which sectors are Leading?"\n'
    '- **Breakouts**: "Breakout candidates" or "stocks breaking out today"\n\n'
    "Please rephrase your query using one of these topics."
)


async def _stream(
    request: QueryRequest,
    engine: Engine,
) -> AsyncGenerator[dict, None]:
    """Async generator: classify → dispatch → stream handler events."""
    query_text = request.last_user_message
    intent = classify_intent(query_text)

    log.info(
        "openbb_query_received",
        intent=intent,
        query_preview=query_text[:80],
    )

    if intent == "unknown":
        yield message_chunk(_FALLBACK_MESSAGE)
        yield done()
        return

    handler = HANDLER_DISPATCH[intent]
    async for event in handler(engine, query_text):
        yield event


@router.post(
    "/v1/query",
    tags=["openbb"],
    summary="OpenBB BYO Copilot streaming query",
    dependencies=[Depends(verify_api_key)],
)
async def post_query(
    body: QueryRequest,
    engine: Engine = Depends(get_engine),  # noqa: B008 — FastAPI dependency injection idiom
) -> EventSourceResponse:
    """Accept a QueryRequest and return a text/event-stream SSE response."""
    return EventSourceResponse(_stream(body, engine))
