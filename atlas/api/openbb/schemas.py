"""SP03: Pydantic schemas for the OpenBB BYO Copilot contract.

Two groups:
1. Request schema — QueryRequest matches what OpenBB Workspace POSTs to /v1/query.
2. SSE event schemas — typed wrappers for each event type we emit.

OpenBB contract reference: https://docs.openbb.co/workspace/custom-backend/copilot
The single dict literal in ``metadata.py`` is the only place to update the
agent registration payload if OpenBB's field names evolve.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ------------------------------------------------------------------ #
# Request                                                              #
# ------------------------------------------------------------------ #


class ChatMessage(BaseModel):
    """One message in the conversation history."""

    role: str  # OpenBB sends "human"/"ai"/"tool"; accept any string
    content: str


class QueryRequest(BaseModel):
    """POST /v1/query request body.

    OpenBB Workspace sends the full conversation history so the copilot can
    handle follow-up questions. For v1, we only look at the last user message.

    ``widgets`` and ``context`` are optional OpenBB fields that carry widget
    state and dashboard context. We accept but do not act on them in v1.
    """

    messages: list[ChatMessage] = Field(..., min_length=1)
    widgets: dict[str, Any] | list[Any] | None = None  # object in OpenBB v4
    context: dict[str, Any] | list[Any] | None = None

    @property
    def last_user_message(self) -> str:
        """Extract the content of the last user-role message."""
        for msg in reversed(self.messages):
            if msg.role in ("human", "user"):
                return msg.content
        return ""


# ------------------------------------------------------------------ #
# SSE event schemas                                                    #
# ------------------------------------------------------------------ #


class MessageChunkEvent(BaseModel):
    """Incremental narrative text chunk.

    OpenBB renders these as streaming prose before/after tabular results.
    SEBI note: content must never contain buy/sell/invest/recommend verbs.
    """

    type: Literal["message_chunk"] = "message_chunk"
    data: str


class ReasoningStep(BaseModel):
    """Visible 'thinking' step shown in the OpenBB UI while the query runs."""

    name: str
    description: str


class ReasoningStepEvent(BaseModel):
    type: Literal["reasoning_step"] = "reasoning_step"
    data: ReasoningStep


class TableColumn(BaseModel):
    """Column definition for the table event."""

    name: str
    dtype: Literal["str", "int", "float", "date", "bool"] = "str"


class TableData(BaseModel):
    """Tabular result payload."""

    name: str
    description: str = ""
    columns: list[TableColumn]
    rows: list[dict[str, Any]]
    data_as_of: str | None = None  # ISO date string; None if view is empty


class TableEvent(BaseModel):
    type: Literal["table"] = "table"
    data: TableData


class ChartSeries(BaseModel):
    """One series in a chart payload.

    v1 note: ChartEvent is shipped under the assumption it is in the OpenBB
    BYO Copilot SDK contract. If the live SDK rejects the chart event type,
    handlers can drop the chart() call without touching this module.
    """

    name: str
    x: list[float | str]
    y: list[float | str]
    labels: list[str] | None = None  # hover labels per point


class ChartData(BaseModel):
    """Chart payload for a scatter or line chart."""

    name: str
    kind: Literal["scatter", "line", "bar"] = "scatter"
    x_label: str = ""
    y_label: str = ""
    series: list[ChartSeries]


class ChartEvent(BaseModel):
    type: Literal["chart"] = "chart"
    data: ChartData


class DoneEvent(BaseModel):
    """Terminal event. OpenBB closes the SSE stream on receipt."""

    type: Literal["done"] = "done"
    data: Literal[""] = ""


# Union type for type-narrowing in tests
SSEEvent = MessageChunkEvent | ReasoningStepEvent | TableEvent | ChartEvent | DoneEvent
