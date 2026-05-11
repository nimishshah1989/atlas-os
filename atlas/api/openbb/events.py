"""SP03: SSE event builder helpers.

Each function takes typed arguments and returns a dict formatted for
``sse_starlette.sse.ServerSentEvent(data=...)``.

Usage in a handler async generator:
    yield message_chunk("Market is in Risk-On regime.")
    yield reasoning_step("Querying regime view", "Reading mv_current_market_regime")
    yield table(table_data)
    yield done()
"""

from __future__ import annotations

from typing import Any

from atlas.api.openbb.schemas import (
    ChartData,
    ChartEvent,
    DoneEvent,
    MessageChunkEvent,
    ReasoningStep,
    ReasoningStepEvent,
    TableData,
    TableEvent,
)


def _sse(event_obj: Any) -> dict[str, str]:
    """Serialise a schema object to sse-starlette-compatible dict."""
    return {"data": event_obj.model_dump_json()}


def message_chunk(text: str) -> dict[str, str]:
    """Emit one chunk of narrative prose."""
    return _sse(MessageChunkEvent(data=text))


def reasoning_step(name: str, description: str) -> dict[str, str]:
    """Emit a visible 'thinking' step in the OpenBB UI."""
    return _sse(ReasoningStepEvent(data=ReasoningStep(name=name, description=description)))


def table(data: TableData) -> dict[str, str]:
    """Emit a tabular result."""
    return _sse(TableEvent(data=data))


def chart(data: ChartData) -> dict[str, str]:
    """Emit a chart payload."""
    return _sse(ChartEvent(data=data))


def done() -> dict[str, str]:
    """Emit the terminal done event to close the SSE stream."""
    return _sse(DoneEvent())
