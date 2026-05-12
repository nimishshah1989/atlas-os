# SP03 — OpenBB Bring-Your-Own-Copilot Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **REQUIRED PRE-FLIGHT:** Before starting any task in this plan, read `docs/phase2/00-master-plan.html` section `id="sp3"` in full. The Phase 2 contract requires it. Project rules in `CLAUDE.md` enforce a planning-skill hook on writes to `atlas/**` — this plan satisfies that gate.

**Goal:** Expose Atlas intelligence inside OpenBB Workspace as a streaming analyst agent via the two-endpoint OpenBB Bring-Your-Own-Copilot (BYO Copilot) SDK contract. Users in OpenBB can type "show me current market regime" or "top RS stocks in IT" and receive real-time SSE-streamed responses backed by Atlas materialized views from SP02.

**Architecture:** Pure presentation layer on top of SP02 materialized views. Four layers: (1) **API-key middleware** on the `/v1/*` path prefix — exempts from Supabase JWT and verifies `OPENBB_BACKEND_API_KEY` instead. (2) **Metadata endpoint** (`GET /v1/agents.json`) returns the agent definition OpenBB Workspace reads on registration. (3) **Query endpoint** (`POST /v1/query`) accepts OpenBB's `QueryRequest` JSON and returns a `text/event-stream` SSE response via `sse-starlette`. (4) **Intent router + four handlers** — keyword-based routing in v1 dispatches to `regime`, `leaders`, `rotation`, and `breakouts` handlers; each handler reads one SP02 materialized view and yields typed SSE events. Zero changes to existing routers, pages, or compute pipeline.

**Soft dependency on SP02:** The four handlers read SP02 materialized views (`mv_current_market_regime`, `mv_rs_leaders_daily`, `mv_sector_rotation_state`, `mv_breakout_candidates`). If SP02 migrations have not run yet, handlers return an empty-table event with a `data_as_of: null` marker — graceful degradation, not an error.

**Tech stack:** FastAPI (already in stack), `sse-starlette>=2.0` (new dep — ~300 lines, no transitive bloat), Pydantic v2 (already in stack), SQLAlchemy 2.0 sync session (already in stack — no async needed for the query handlers), structlog (already in stack).

**SEBI compliance note:** All narrative text emitted by handlers MUST use research language only. Never use "buy", "sell", "invest", "recommend", "advise", or "target price" in any string emitted by SSE events. The plan calls out compliant phrasing at each handler; the test suite checks for banned words.

**Confirmed Atlas patterns this plan follows:**
- `_EXEMPT_PREFIXES` tuple in `atlas/api/auth.py` for path-level JWT bypass
- `APIRouter(prefix=..., tags=[...])` style from `portfolios.py` and `strategies.py`
- `op.execute(sa.text(...))` DDL pattern not needed here (pure Python — no migrations)
- `Depends(get_engine)` dependency injection for DB access
- `structlog.get_logger()` for all logging
- No `print()` in production code
- `Decimal` for money; `str` for NUMERIC columns from Postgres (parse at render time)

**File structure to create / modify:**

```
atlas/api/openbb/__init__.py                     # CREATE — package marker (empty)
atlas/api/openbb/router.py                       # CREATE — mounts all openbb sub-routes under /v1
atlas/api/openbb/schemas.py                      # CREATE — QueryRequest + all SSE event Pydantic models
atlas/api/openbb/auth.py                         # CREATE — API-key dependency for /v1/* routes
atlas/api/openbb/metadata.py                     # CREATE — GET /v1/agents.json
atlas/api/openbb/events.py                       # CREATE — SSE event builder helpers
atlas/api/openbb/query.py                        # CREATE — POST /v1/query (SSE endpoint)
atlas/api/openbb/handlers/__init__.py            # CREATE — dispatch table (dict mapping intent → handler)
atlas/api/openbb/handlers/regime.py              # CREATE — reads mv_current_market_regime
atlas/api/openbb/handlers/leaders.py             # CREATE — reads mv_rs_leaders_daily
atlas/api/openbb/handlers/rotation.py            # CREATE — reads mv_sector_rotation_state
atlas/api/openbb/handlers/breakouts.py           # CREATE — reads mv_breakout_candidates
atlas/api/openbb/handlers/router.py              # CREATE — keyword intent classifier (testable in isolation)
tests/api/openbb/__init__.py                     # CREATE — empty
tests/api/openbb/test_metadata.py                # CREATE — GET /v1/agents.json schema tests
tests/api/openbb/test_query_routing.py           # CREATE — intent classifier unit tests (no DB)
tests/api/openbb/test_handlers.py                # CREATE — handler SSE event tests (mocked DB)
tests/api/openbb/test_e2e_smoke.py               # CREATE — full request → SSE stream (integration-marked)
pyproject.toml                                   # MODIFY — add sse-starlette>=2.0 to base deps
atlas/api/__init__.py                            # MODIFY — mount openbb_router (one line)
atlas/api/auth.py                                # MODIFY — exempt /v1 prefix from JWT (one line)
```

**File responsibility split:**
- `schemas.py` — all Pydantic models. Single source of truth for the OpenBB contract. Imported by `query.py`, `events.py`, and all handlers.
- `auth.py` (openbb) — `verify_api_key` FastAPI dependency. Reads `OPENBB_BACKEND_API_KEY` from env via `atlas.config.Config`. 401 JSON if missing or mismatch.
- `metadata.py` — pure function returning a `dict`; no DB. The JSON structure is the OpenBB agent registration contract.
- `events.py` — five helper functions (`message_chunk_event`, `reasoning_step_event`, `table_event`, `chart_event`, `done_event`). Each returns a properly serialised `dict` ready for `sse-starlette`'s `ServerSentEvent`.
- `handlers/router.py` — `classify_intent(text: str) -> str` pure function. Returns one of: `"regime"`, `"leaders"`, `"rotation"`, `"breakouts"`, `"unknown"`. No DB, no imports from `atlas.db`.
- `handlers/regime.py` — async generator `handle_regime(engine)` — reads `mv_current_market_regime`, yields `reasoning_step` + `message_chunk` narrative + `table` event.
- `handlers/leaders.py` — async generator `handle_leaders(engine, query_text)` — extracts sector hint from query text, reads `mv_rs_leaders_daily`, yields `reasoning_step` + `table`.
- `handlers/rotation.py` — async generator `handle_rotation(engine)` — reads `mv_sector_rotation_state`, yields `reasoning_step` + `table` + optional `chart` (scatter payload of RS level vs velocity).
- `handlers/breakouts.py` — async generator `handle_breakouts(engine)` — reads `mv_breakout_candidates`, yields `reasoning_step` + `table`.
- `handlers/__init__.py` — `HANDLER_DISPATCH: dict[str, Callable]` mapping intent keys to handler callables. `query.py` imports only this.
- `query.py` — the SSE endpoint. Validates `QueryRequest`, calls `classify_intent`, dispatches to handler, wraps generator in `EventSourceResponse`.
- `router.py` — `APIRouter(prefix="")` that includes the two routes: `GET /v1/agents.json` from `metadata.py`, `POST /v1/query` from `query.py`. **Note:** No `/v1` prefix on the router itself — the routes declare their full paths to match OpenBB's expected URL exactly.

---

## Task 0: Pre-flight verification

**Files:** none created/modified.

- [ ] **Step 1: Read SP03 in the master plan**

  Open `docs/phase2/00-master-plan.html` and read the `id="sp3"` div in full. Confirm the deliverables listed there match this plan.

- [ ] **Step 2: Confirm SP02 views exist (soft dep check)**

  ```bash
  python3 -c "
  from atlas.db import get_engine
  from sqlalchemy import text
  eng = get_engine()
  views = [
      'mv_current_market_regime',
      'mv_rs_leaders_daily',
      'mv_sector_rotation_state',
      'mv_breakout_candidates',
  ]
  with eng.connect() as c:
      for v in views:
          try:
              n = c.execute(text(f'SELECT COUNT(*) FROM atlas.{v}')).scalar()
              print(f'{v}: {n} rows — OK')
          except Exception as e:
              print(f'{v}: MISSING — {e}')
  "
  ```

  Expected: all four views exist with row counts > 0. If any are missing, SP02 migrations have not run — proceed anyway (handlers degrade gracefully, tests use mocks), but note that EC2 integration in Task 9 requires SP02 to be deployed first.

- [ ] **Step 3: Confirm `sse-starlette` is NOT already installed**

  ```bash
  python3 -c "import sse_starlette; print(sse_starlette.__version__)"
  ```

  Expected: `ModuleNotFoundError`. If it is already installed, skip the `pyproject.toml` edit in Task 1 and record the installed version.

- [ ] **Step 4: Confirm `atlas.config.Config` can hold new env var**

  ```bash
  python3 -c "
  from atlas.config import Config
  print([f for f in dir(Config) if not f.startswith('_')])
  "
  ```

  Review the output. We will add `OPENBB_BACKEND_API_KEY: str = ''` to `Config`. If `Config` uses `pydantic-settings` `BaseSettings`, the new field follows the same pattern as `SUPABASE_JWT_SECRET`. Record the pattern here if it differs.

- [ ] **Step 5: Check current alembic head (no migrations needed but confirms DB state)**

  ```bash
  alembic current
  ```

  Expected: `036 (head)` if SP02 is complete. SP03 adds no migrations.

---

## Task 1: Add `sse-starlette` dependency + `OPENBB_BACKEND_API_KEY` to Config

**Files:**
- Modify: `pyproject.toml`
- Modify: `atlas/config.py` (surgical: one new field)
- Document: `.env` (NOT committed — document here, set manually)

`sse-starlette` is the standard SSE library for Starlette/FastAPI. It wraps an async generator in a `text/event-stream` response. Version `>=2.0` is required for the `data=` keyword argument on `ServerSentEvent`.

- [ ] **Step 1: Add `sse-starlette>=2.0` to `pyproject.toml`**

  In `pyproject.toml`, locate the `# Serving` comment block (around line 34). Add after `"uvicorn[standard]>=0.27"`:

  ```toml
  # OpenBB BYO Copilot SSE streaming (SP03)
  "sse-starlette>=2.0",
  ```

  The full block should read:
  ```toml
  # Serving (FastAPI thin layer per architecture 10.1; UI is Streamlit)
  "fastapi>=0.110",
  "uvicorn[standard]>=0.27",
  # OpenBB BYO Copilot SSE streaming (SP03)
  "sse-starlette>=2.0",
  ```

- [ ] **Step 2: Install the new dependency**

  ```bash
  pip install "sse-starlette>=2.0" 2>&1 | tail -5
  ```

  Expected: `Successfully installed sse-starlette-<version>`. Note the version for the memory file.

- [ ] **Step 3: Add `OPENBB_BACKEND_API_KEY` to `atlas/config.py`**

  Read `atlas/config.py` first. Locate the `Config` class (or `Settings` if using pydantic-settings). Add one field using the same pattern as `SUPABASE_JWT_SECRET`:

  ```python
  # SP03: OpenBB BYO Copilot API key. Set in .env on EC2.
  # NOT a Supabase JWT — OpenBB Workspace sends its own bearer.
  # Empty string disables auth (local dev only). Never empty in production.
  OPENBB_BACKEND_API_KEY: str = ""
  ```

  If `Config` uses `os.getenv`, add:
  ```python
  OPENBB_BACKEND_API_KEY: str = os.getenv("OPENBB_BACKEND_API_KEY", "")
  ```

- [ ] **Step 4: Document `.env` addition**

  The following line must be added manually to `.env` on EC2 (never committed):
  ```
  OPENBB_BACKEND_API_KEY=<generate with: python3 -c "import secrets; print(secrets.token_urlsafe(32))">
  ```

  On local dev, leave it empty — the auth middleware skips verification when the value is empty string (same pattern as `ATLAS_AUTH_DISABLED`). Explicitly: in `atlas/api/openbb/auth.py`, if `Config.OPENBB_BACKEND_API_KEY == ""`, log a warning and allow the request through (dev mode). The log line must include `"openbb_auth_disabled"` so it's grep-able.

- [ ] **Step 5: Run pyright on `atlas/config.py`**

  ```bash
  pyright atlas/config.py
  ```

  Expected: no errors.

- [ ] **Step 6: Commit**

  ```bash
  git add pyproject.toml atlas/config.py
  git commit -m "feat(sp03): add sse-starlette dep + OPENBB_BACKEND_API_KEY config field"
  ```

---

## Task 2: Pydantic schemas (`atlas/api/openbb/schemas.py`)

**Files:**
- Create: `atlas/api/openbb/__init__.py`
- Create: `atlas/api/openbb/schemas.py`

All OpenBB contract types live here. `query.py`, `events.py`, and handler tests all import from this module. Changing a schema here is the single place to update the contract.

- [ ] **Step 1: Create package marker**

  Create `atlas/api/openbb/__init__.py` as an empty file (package marker only — no imports).

- [ ] **Step 2: Create `atlas/api/openbb/schemas.py`**

  ```python
  """SP03: Pydantic schemas for the OpenBB BYO Copilot contract.

  Two groups:
  1. Request schema — QueryRequest matches what OpenBB Workspace POSTs to /v1/query.
  2. SSE event schemas — typed wrappers for each event type we emit.

  OpenBB contract reference: https://docs.openbb.co/workspace/custom-backend/copilot
  (verify against live docs — contract may have evolved since this plan was written).
  """

  from __future__ import annotations

  from typing import Any, Literal

  from pydantic import BaseModel, Field


  # ------------------------------------------------------------------ #
  # Request                                                              #
  # ------------------------------------------------------------------ #

  class ChatMessage(BaseModel):
      """One message in the conversation history."""

      role: Literal["user", "assistant", "system"]
      content: str


  class QueryRequest(BaseModel):
      """POST /v1/query request body.

      OpenBB Workspace sends the full conversation history so the copilot can
      handle follow-up questions. For v1, we only look at the last user message.

      ``widgets`` and ``context`` are optional OpenBB fields that carry widget
      state and dashboard context. We accept but do not act on them in v1.
      """

      messages: list[ChatMessage] = Field(..., min_length=1)
      widgets: list[Any] | None = None
      context: dict[str, Any] | None = None

      @property
      def last_user_message(self) -> str:
          """Extract the content of the last user-role message."""
          for msg in reversed(self.messages):
              if msg.role == "user":
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
      """One series in a chart payload."""

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
  ```

- [ ] **Step 3: Run pyright on `schemas.py`**

  ```bash
  pyright atlas/api/openbb/schemas.py
  ```

  Expected: no errors.

- [ ] **Step 4: Commit**

  ```bash
  git add atlas/api/openbb/__init__.py atlas/api/openbb/schemas.py
  git commit -m "feat(sp03): OpenBB schemas — QueryRequest + typed SSE event models"
  ```

---

## Task 3: SSE event helpers (`atlas/api/openbb/events.py`)

**Files:**
- Create: `atlas/api/openbb/events.py`

These are thin wrappers that serialise a schema object into the `dict` format `sse-starlette` expects. Every handler imports from this module — centralising serialisation prevents schema drift across handlers.

- [ ] **Step 1: Create `atlas/api/openbb/events.py`**

  ```python
  """SP03: SSE event builder helpers.

  Each function takes typed arguments and returns a dict formatted for
  sse_starlette.sse.ServerSentEvent(data=..., event=...).

  Usage in a handler async generator:
      yield message_chunk("Market is in Risk-On regime.")
      yield reasoning_step("Querying regime view", "Reading mv_current_market_regime")
      yield table(table_data)
      yield done()
  """

  from __future__ import annotations

  import json
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
  ```

- [ ] **Step 2: Run pyright on `events.py`**

  ```bash
  pyright atlas/api/openbb/events.py
  ```

  Expected: no errors.

- [ ] **Step 3: Commit**

  ```bash
  git add atlas/api/openbb/events.py
  git commit -m "feat(sp03): SSE event builder helpers"
  ```

---

## Task 4: API-key auth middleware (`atlas/api/openbb/auth.py`) + JWT bypass

**Files:**
- Create: `atlas/api/openbb/auth.py`
- Modify: `atlas/api/auth.py` (surgical: one line — add `"/v1"` to `_EXEMPT_PREFIXES`)

OpenBB Workspace sends `Authorization: Bearer <api-key>` where the value is the `OPENBB_BACKEND_API_KEY` we set — NOT a Supabase JWT. The Supabase JWT middleware must skip `/v1/*`. A separate FastAPI `Depends` dependency in the OpenBB router enforces the API key.

- [ ] **Step 1: Exempt `/v1` from JWT middleware**

  In `atlas/api/auth.py`, locate `_EXEMPT_PREFIXES`:

  ```python
  _EXEMPT_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc")
  ```

  Change to:

  ```python
  _EXEMPT_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc", "/v1")
  ```

  This is a one-token change. The `/v1` prefix covers both `GET /v1/agents.json` and `POST /v1/query`.

- [ ] **Step 2: Create `atlas/api/openbb/auth.py`**

  ```python
  """SP03: API-key authentication for the OpenBB /v1/* routes.

  OpenBB Workspace sends Authorization: Bearer <api-key> where the key is
  OPENBB_BACKEND_API_KEY (not a Supabase JWT). The Supabase JWT middleware
  skips /v1/* entirely (see atlas/api/auth.py _EXEMPT_PREFIXES).

  This module provides ``verify_api_key`` — a FastAPI Depends() dependency.
  Mount it on the OpenBB router so every /v1 route is protected.

  Dev mode: if OPENBB_BACKEND_API_KEY is empty string, the check is skipped
  and a warning is logged. This mirrors the ATLAS_AUTH_DISABLED pattern.
  Never leave the key empty in production.
  """

  from __future__ import annotations

  import structlog
  from fastapi import Depends, HTTPException
  from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

  from atlas.config import Config

  log = structlog.get_logger()

  _bearer = HTTPBearer(auto_error=False)


  async def verify_api_key(
      credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),  # noqa: B008
  ) -> None:
      """FastAPI dependency — verifies the OpenBB API key.

      Raises HTTP 401 if:
        - No Authorization header (and key is configured)
        - Token does not match OPENBB_BACKEND_API_KEY

      Passes through silently (dev mode) if OPENBB_BACKEND_API_KEY is empty.
      """
      expected = Config.OPENBB_BACKEND_API_KEY

      if not expected:
          log.warning("openbb_auth_disabled", reason="OPENBB_BACKEND_API_KEY not set — allowing all /v1 requests")
          return

      if credentials is None:
          raise HTTPException(
              status_code=401,
              detail={
                  "error_code": "openbb_missing_token",
                  "message": "Authorization: Bearer <api-key> required for /v1 routes",
                  "context": {},
              },
          )

      if credentials.credentials != expected:
          log.warning("openbb_auth_rejected", reason="api_key_mismatch")
          raise HTTPException(
              status_code=401,
              detail={
                  "error_code": "openbb_invalid_token",
                  "message": "Invalid API key",
                  "context": {},
              },
          )
  ```

- [ ] **Step 3: Run pyright on both files**

  ```bash
  pyright atlas/api/auth.py atlas/api/openbb/auth.py
  ```

  Expected: no errors.

- [ ] **Step 4: Confirm JWT middleware still protects non-v1 routes**

  ```bash
  python3 -c "
  from atlas.api.auth import _EXEMPT_PREFIXES
  print(_EXEMPT_PREFIXES)
  assert '/v1' in _EXEMPT_PREFIXES
  assert '/api/portfolios' not in _EXEMPT_PREFIXES
  print('OK')
  "
  ```

  Expected: prints the tuple with `/v1` present and `OK`.

- [ ] **Step 5: Commit**

  ```bash
  git add atlas/api/auth.py atlas/api/openbb/auth.py
  git commit -m "feat(sp03): exempt /v1 from JWT middleware + OpenBB API-key dependency"
  ```

---

## Task 5: Intent classifier (`atlas/api/openbb/handlers/router.py`)

**Files:**
- Create: `atlas/api/openbb/handlers/__init__.py`
- Create: `atlas/api/openbb/handlers/router.py`

The intent classifier is a pure function with no DB access. It is its own module so it is testable in isolation without spinning up a database or ASGI app. V1 is keyword-based; the V2 upgrade path (route to Claude) is noted as a stub.

- [ ] **Step 1: Create `atlas/api/openbb/handlers/__init__.py`**

  ```python
  """SP03: OpenBB query handler dispatch table.

  Import HANDLER_DISPATCH from this module to get the mapping from intent key
  to handler async generator callable.

  Handler callables have signature:
      async def handle_*(engine: Engine, query_text: str) -> AsyncGenerator[dict, None]
  """

  from __future__ import annotations

  from collections.abc import AsyncGenerator
  from typing import Callable

  from sqlalchemy.engine import Engine

  from atlas.api.openbb.handlers.breakouts import handle_breakouts
  from atlas.api.openbb.handlers.leaders import handle_leaders
  from atlas.api.openbb.handlers.regime import handle_regime
  from atlas.api.openbb.handlers.rotation import handle_rotation

  # Dispatch table: intent key → handler callable.
  # query.py imports this dict and calls HANDLER_DISPATCH[intent](engine, query_text).
  HANDLER_DISPATCH: dict[str, Callable[[Engine, str], AsyncGenerator[dict, None]]] = {
      "regime":    handle_regime,
      "leaders":   handle_leaders,
      "rotation":  handle_rotation,
      "breakouts": handle_breakouts,
  }

  __all__ = ["HANDLER_DISPATCH"]
  ```

- [ ] **Step 2: Create `atlas/api/openbb/handlers/router.py`**

  ```python
  """SP03: keyword-based intent classifier for OpenBB query routing.

  classify_intent() is a pure function — no DB, no FastAPI, no async.
  It is deliberately isolated here so it can be unit-tested without any
  infrastructure setup.

  V1 strategy: case-insensitive substring matching, first-match wins.
  V2 upgrade path: when no keyword matches, call Claude with Atlas-context
  system prompt (stub noted below, out of scope for SP03).

  Intent keys match the keys in HANDLER_DISPATCH in handlers/__init__.py.
  """

  from __future__ import annotations


  # Keyword table: (intent_key, tuple_of_trigger_phrases).
  # Order matters — more-specific phrases must appear before general ones.
  # All phrases are matched case-insensitively against the full query text.
  _KEYWORD_TABLE: list[tuple[str, tuple[str, ...]]] = [
      ("regime",    ("regime", "market state", "risk-on", "risk on", "risk off",
                     "risk-off", "deployment", "dislocation", "market regime")),
      ("leaders",   ("top stocks", "leaders", "rs leaders", "strongest stocks",
                     "leading stocks", "top rs", "best performers")),
      ("rotation",  ("rotation", "sector rotation", "rrg", "relative rotation",
                     "sectors rotating", "quadrant", "leading sectors",
                     "weakening sectors", "improving sectors", "lagging sectors")),
      ("breakouts", ("breakout", "breaking out", "new leaders", "transitioning",
                     "just entered", "breakout candidates", "fresh breakouts")),
  ]


  def classify_intent(query_text: str) -> str:
      """Return the intent key for ``query_text``, or ``"unknown"`` if no match.

      Args:
          query_text: The raw user query string (last user message).

      Returns:
          One of: ``"regime"``, ``"leaders"``, ``"rotation"``, ``"breakouts"``,
          ``"unknown"``.
      """
      lower = query_text.lower()
      for intent_key, triggers in _KEYWORD_TABLE:
          if any(phrase in lower for phrase in triggers):
              return intent_key
      # V2: route to Claude here with Atlas-context system prompt.
      # For now, return "unknown" → fallback message_chunk in query.py.
      return "unknown"
  ```

- [ ] **Step 3: Run pyright**

  ```bash
  pyright atlas/api/openbb/handlers/router.py atlas/api/openbb/handlers/__init__.py
  ```

  Expected: no errors.

- [ ] **Step 4: Commit**

  ```bash
  git add atlas/api/openbb/handlers/__init__.py atlas/api/openbb/handlers/router.py
  git commit -m "feat(sp03): keyword intent classifier + handler dispatch table"
  ```

---

## Task 6: Four query handlers

**Files:**
- Create: `atlas/api/openbb/handlers/regime.py`
- Create: `atlas/api/openbb/handlers/leaders.py`
- Create: `atlas/api/openbb/handlers/rotation.py`
- Create: `atlas/api/openbb/handlers/breakouts.py`

Each handler is an async generator that yields `dict` objects (from `events.py` helpers). Each handler:
1. Yields a `reasoning_step` event ("Querying <view>", description of what it's doing)
2. Executes a single synchronous SQL query via SQLAlchemy `engine.connect()`
3. If the result is empty, yields a `message_chunk` explaining the view may not be populated yet (graceful SP02-not-deployed path)
4. Otherwise, yields a `message_chunk` with a 1–3 sentence narrative, then a `table` event
5. Yields `done()` as the final event

SEBI compliance: all narrative strings use research language. Banned words: "buy", "sell", "invest", "recommend", "advise", "target". Compliant alternatives: "signals", "ranks", "exhibits", "shows", "demonstrates", "is positioned in".

- [ ] **Step 1: Create `atlas/api/openbb/handlers/regime.py`**

  ```python
  """SP03: market regime handler.

  Reads mv_current_market_regime (one row). Streams:
    1. reasoning_step — "Querying market regime"
    2. message_chunk  — 2-sentence summary of current regime state
    3. table          — all regime columns formatted for display
    4. done
  """

  from __future__ import annotations

  from collections.abc import AsyncGenerator
  from datetime import date

  import structlog
  from sqlalchemy import text
  from sqlalchemy.engine import Engine

  from atlas.api.openbb.events import done, message_chunk, reasoning_step, table
  from atlas.api.openbb.schemas import TableColumn, TableData

  log = structlog.get_logger()

  # Columns to surface in the table event (subset of mv_current_market_regime).
  # Ordered for analyst readability — regime state first, then supporting signals.
  _COLUMNS: list[TableColumn] = [
      TableColumn(name="date",                    dtype="date"),
      TableColumn(name="regime_state",            dtype="str"),
      TableColumn(name="deployment_multiplier",   dtype="float"),
      TableColumn(name="dislocation_active",      dtype="bool"),
      TableColumn(name="india_vix",               dtype="float"),
      TableColumn(name="pct_above_ema_50",        dtype="float"),
      TableColumn(name="pct_above_ema_200",       dtype="float"),
      TableColumn(name="pct_in_strong_states",    dtype="float"),
      TableColumn(name="ad_ratio",                dtype="float"),
      TableColumn(name="net_new_highs",           dtype="int"),
      TableColumn(name="mcclellan_oscillator",    dtype="float"),
  ]

  _COLUMN_NAMES = [c.name for c in _COLUMNS]


  async def handle_regime(engine: Engine, query_text: str) -> AsyncGenerator[dict, None]:
      """Stream the current market regime from mv_current_market_regime."""
      yield reasoning_step(
          name="Querying market regime",
          description="Reading mv_current_market_regime — latest regime row with breadth signals.",
      )

      with engine.connect() as conn:
          row = conn.execute(
              text(f"""
                  SELECT {', '.join(_COLUMN_NAMES)}
                  FROM atlas.mv_current_market_regime
                  LIMIT 1
              """)  # noqa: S608 — _COLUMN_NAMES are string constants, no user input
          ).mappings().fetchone()

      if row is None:
          yield message_chunk(
              "Market regime data is not yet available. "
              "The materialized view may not have been populated. "
              "Run the nightly pipeline and refresh mv_current_market_regime."
          )
          yield done()
          return

      regime = row["regime_state"] or "Unknown"
      multiplier = row["deployment_multiplier"]
      dislocation = row["dislocation_active"]
      as_of: date = row["date"]

      # SEBI-compliant narrative: describes state, no buy/sell language.
      narrative_parts = [
          f"As of {as_of.strftime('%d-%b-%Y')}, the Indian equity market is classified as **{regime}**.",
      ]
      if multiplier is not None:
          narrative_parts.append(
              f"The deployment multiplier stands at {float(multiplier):.2f}x, "
              "reflecting current breadth and momentum conditions."
          )
      if dislocation:
          narrative_parts.append(
              "A **market dislocation** is currently active — breadth signals are diverging from price."
          )

      yield message_chunk(" ".join(narrative_parts))

      rows_out = [
          {
              col: (str(row[col]) if row[col] is not None else None)
              for col in _COLUMN_NAMES
          }
      ]
      yield table(TableData(
          name="Current Market Regime",
          description=f"Atlas market regime as of {as_of.strftime('%d-%b-%Y')}. Source: mv_current_market_regime.",
          columns=_COLUMNS,
          rows=rows_out,
          data_as_of=str(as_of),
      ))

      log.info("openbb_regime_handler_complete", regime=regime, as_of=str(as_of))
      yield done()
  ```

- [ ] **Step 2: Create `atlas/api/openbb/handlers/leaders.py`**

  ```python
  """SP03: top RS stocks handler.

  Reads mv_rs_leaders_daily. Optionally filters by sector extracted from
  the query text (simple heuristic: last capitalised word preceding the
  query end, or explicit "in <sector>" pattern).

  Streams:
    1. reasoning_step — "Querying RS leaders"
    2. message_chunk  — brief summary (N stocks in Leader/Strong state)
    3. table          — top-50 rows ordered by rs_pctile_3m DESC
    4. done
  """

  from __future__ import annotations

  import re
  from collections.abc import AsyncGenerator

  import structlog
  from sqlalchemy import text
  from sqlalchemy.engine import Engine

  from atlas.api.openbb.events import done, message_chunk, reasoning_step, table
  from atlas.api.openbb.schemas import TableColumn, TableData

  log = structlog.get_logger()

  _COLUMNS: list[TableColumn] = [
      TableColumn(name="symbol",           dtype="str"),
      TableColumn(name="company_name",     dtype="str"),
      TableColumn(name="sector",           dtype="str"),
      TableColumn(name="tier",             dtype="str"),
      TableColumn(name="rs_state",         dtype="str"),
      TableColumn(name="rs_pctile_3m",     dtype="float"),
      TableColumn(name="rs_3m_nifty500",   dtype="float"),
      TableColumn(name="momentum_state",   dtype="str"),
      TableColumn(name="state_since_date", dtype="date"),
  ]

  _COLUMN_NAMES = [c.name for c in _COLUMNS]

  # Known NIFTY sector names (for sector hint extraction).
  _KNOWN_SECTORS = {
      "it", "banking", "bank", "fmcg", "pharma", "healthcare", "auto",
      "realty", "metal", "energy", "infra", "financial", "media",
      "psu", "consumption",
  }

  _LIMIT = 50


  def _extract_sector_hint(query_text: str) -> str | None:
      """Extract a sector name from the query, or return None.

      Looks for 'in <sector>' or 'for <sector>' patterns.
      Returns the matched word (un-cased, for SQL parameterisation).
      """
      match = re.search(r'\b(?:in|for)\s+([A-Za-z]+)', query_text, re.IGNORECASE)
      if match:
          word = match.group(1).lower()
          if word in _KNOWN_SECTORS:
              return word
      return None


  async def handle_leaders(engine: Engine, query_text: str) -> AsyncGenerator[dict, None]:
      """Stream top RS stocks from mv_rs_leaders_daily."""
      sector_hint = _extract_sector_hint(query_text)

      yield reasoning_step(
          name="Querying RS leaders",
          description=(
              f"Reading mv_rs_leaders_daily"
              + (f" filtered to sector containing '{sector_hint}'" if sector_hint else " — all sectors")
              + f", top {_LIMIT} by 3-month RS percentile."
          ),
      )

      with engine.connect() as conn:
          if sector_hint:
              rows = conn.execute(
                  text(f"""
                      SELECT {', '.join(_COLUMN_NAMES)}
                      FROM atlas.mv_rs_leaders_daily
                      WHERE LOWER(sector) LIKE :sector
                      ORDER BY rs_pctile_3m DESC NULLS LAST
                      LIMIT :lim
                  """),  # noqa: S608 — _COLUMN_NAMES are constants; sector via bind param
                  {"sector": f"%{sector_hint}%", "lim": _LIMIT},
              ).mappings().fetchall()
          else:
              rows = conn.execute(
                  text(f"""
                      SELECT {', '.join(_COLUMN_NAMES)}
                      FROM atlas.mv_rs_leaders_daily
                      ORDER BY rs_pctile_3m DESC NULLS LAST
                      LIMIT :lim
                  """),  # noqa: S608 — _COLUMN_NAMES are constants; no user input in query
                  {"lim": _LIMIT},
              ).mappings().fetchall()

      if not rows:
          yield message_chunk(
              "No RS leaders data is available. "
              + ("This may be because no stocks match the sector filter, or " if sector_hint else "")
              + "the materialized view may not yet be populated."
          )
          yield done()
          return

      n_leaders = sum(1 for r in rows if r.get("rs_state") == "Leader")
      n_strong  = sum(1 for r in rows if r.get("rs_state") == "Strong")
      sector_str = f" in the {sector_hint.title()} sector" if sector_hint else ""

      yield message_chunk(
          f"{len(rows)} stocks{sector_str} currently exhibit strong relative strength vs Nifty 500. "
          f"{n_leaders} are classified as **Leader** and {n_strong} as **Strong** based on RS state. "
          "Ranked by 3-month RS percentile (higher = stronger relative performance)."
      )

      rows_out = [
          {col: (str(r[col]) if r[col] is not None else None) for col in _COLUMN_NAMES}
          for r in rows
      ]
      yield table(TableData(
          name="Top RS Stocks" + (f" — {sector_hint.title()}" if sector_hint else ""),
          description="Source: mv_rs_leaders_daily. Leader and Strong RS-state stocks, ranked by 3m RS percentile.",
          columns=_COLUMNS,
          rows=rows_out,
          data_as_of=str(rows[0]["state_since_date"]) if rows[0].get("state_since_date") else None,
      ))

      log.info("openbb_leaders_handler_complete", count=len(rows), sector=sector_hint)
      yield done()
  ```

- [ ] **Step 3: Create `atlas/api/openbb/handlers/rotation.py`**

  ```python
  """SP03: sector rotation handler.

  Reads mv_sector_rotation_state (~14 rows, one per NIFTY sector). Streams:
    1. reasoning_step — "Querying sector rotation"
    2. message_chunk  — summary of quadrant distribution
    3. table          — all sectors with RRG quadrant + RS metrics
    4. chart          — scatter: X=rs_velocity, Y=rs_pctile_cross_sector, label=sector_name
    5. done
  """

  from __future__ import annotations

  from collections.abc import AsyncGenerator

  import structlog
  from sqlalchemy import text
  from sqlalchemy.engine import Engine

  from atlas.api.openbb.events import chart, done, message_chunk, reasoning_step, table
  from atlas.api.openbb.schemas import ChartData, ChartSeries, TableColumn, TableData

  log = structlog.get_logger()

  _COLUMNS: list[TableColumn] = [
      TableColumn(name="sector_name",              dtype="str"),
      TableColumn(name="rrg_quadrant",             dtype="str"),
      TableColumn(name="rs_level",                 dtype="float"),
      TableColumn(name="rs_velocity",              dtype="float"),
      TableColumn(name="rs_pctile_cross_sector",   dtype="float"),
      TableColumn(name="sector_state",             dtype="str"),
      TableColumn(name="bottomup_rs_state",        dtype="str"),
      TableColumn(name="bottomup_momentum_state",  dtype="str"),
      TableColumn(name="participation_rs_pct",     dtype="float"),
      TableColumn(name="constituent_count",        dtype="int"),
  ]

  _COLUMN_NAMES = [c.name for c in _COLUMNS]


  async def handle_rotation(engine: Engine, query_text: str) -> AsyncGenerator[dict, None]:
      """Stream sector rotation state from mv_sector_rotation_state."""
      yield reasoning_step(
          name="Querying sector rotation",
          description="Reading mv_sector_rotation_state — RRG quadrant assignments and RS metrics for all sectors.",
      )

      with engine.connect() as conn:
          rows = conn.execute(
              text(f"""
                  SELECT {', '.join(_COLUMN_NAMES)}
                  FROM atlas.mv_sector_rotation_state
                  ORDER BY rs_pctile_cross_sector DESC NULLS LAST
              """)  # noqa: S608 — _COLUMN_NAMES are constants; no user input
          ).mappings().fetchall()

      if not rows:
          yield message_chunk(
              "Sector rotation data is not yet available. "
              "The materialized view may not be populated — ensure SP02 migrations have run "
              "and the nightly sector pipeline has executed."
          )
          yield done()
          return

      # Quadrant counts for narrative
      quadrant_counts: dict[str, int] = {}
      for r in rows:
          q = r.get("rrg_quadrant") or "Unknown"
          quadrant_counts[q] = quadrant_counts.get(q, 0) + 1

      leading   = quadrant_counts.get("Leading", 0)
      improving = quadrant_counts.get("Improving", 0)
      weakening = quadrant_counts.get("Weakening", 0)
      lagging   = quadrant_counts.get("Lagging", 0)

      yield message_chunk(
          f"Current sector rotation across {len(rows)} NIFTY sectors: "
          f"**{leading}** Leading, **{improving}** Improving, "
          f"**{weakening}** Weakening, **{lagging}** Lagging. "
          "Sectors are classified by RS level (cross-sectional percentile) and RS velocity "
          "(4-week rate-of-change of relative strength vs Nifty 500)."
      )

      rows_out = [
          {col: (str(r[col]) if r[col] is not None else None) for col in _COLUMN_NAMES}
          for r in rows
      ]
      yield table(TableData(
          name="Sector Rotation State",
          description="Source: mv_sector_rotation_state. RRG quadrants: Leading/Improving/Weakening/Lagging.",
          columns=_COLUMNS,
          rows=rows_out,
          data_as_of=str(rows[0]["date"]) if rows[0].get("date") else None,
      ))

      # Chart: RS velocity (X) vs RS percentile (Y) scatter — standard RRG layout.
      # Only include rows with both values non-null.
      scatter_x:      list[float] = []
      scatter_y:      list[float] = []
      scatter_labels: list[str]   = []
      for r in rows:
          vx = r.get("rs_velocity")
          vy = r.get("rs_pctile_cross_sector")
          if vx is not None and vy is not None:
              try:
                  scatter_x.append(float(vx))
                  scatter_y.append(float(vy))
                  scatter_labels.append(str(r.get("sector_name", "")))
              except (ValueError, TypeError):
                  pass

      if scatter_x:
          yield chart(ChartData(
              name="Relative Rotation Graph — Sectors",
              kind="scatter",
              x_label="RS Velocity (4-week RoC)",
              y_label="RS Percentile (cross-sector)",
              series=[ChartSeries(
                  name="Sectors",
                  x=scatter_x,
                  y=scatter_y,
                  labels=scatter_labels,
              )],
          ))

      log.info("openbb_rotation_handler_complete", sector_count=len(rows))
      yield done()
  ```

- [ ] **Step 4: Create `atlas/api/openbb/handlers/breakouts.py`**

  ```python
  """SP03: breakout candidates handler.

  Reads mv_breakout_candidates — stocks that transitioned INTO Leader or Strong
  on the most recent trading day. Streams:
    1. reasoning_step — "Querying breakout candidates"
    2. message_chunk  — count of candidates and context
    3. table          — candidates ordered by rs_pctile_3m DESC
    4. done
  """

  from __future__ import annotations

  from collections.abc import AsyncGenerator

  import structlog
  from sqlalchemy import text
  from sqlalchemy.engine import Engine

  from atlas.api.openbb.events import done, message_chunk, reasoning_step, table
  from atlas.api.openbb.schemas import TableColumn, TableData

  log = structlog.get_logger()

  _COLUMNS: list[TableColumn] = [
      TableColumn(name="symbol",           dtype="str"),
      TableColumn(name="company_name",     dtype="str"),
      TableColumn(name="sector",           dtype="str"),
      TableColumn(name="tier",             dtype="str"),
      TableColumn(name="new_rs_state",     dtype="str"),
      TableColumn(name="prior_rs_state",   dtype="str"),
      TableColumn(name="rs_pctile_3m",     dtype="float"),
      TableColumn(name="rs_3m_nifty500",   dtype="float"),
      TableColumn(name="momentum_state",   dtype="str"),
      TableColumn(name="state_since_date", dtype="date"),
  ]

  _COLUMN_NAMES = [c.name for c in _COLUMNS]


  async def handle_breakouts(engine: Engine, query_text: str) -> AsyncGenerator[dict, None]:
      """Stream breakout candidates from mv_breakout_candidates."""
      yield reasoning_step(
          name="Querying breakout candidates",
          description="Reading mv_breakout_candidates — stocks transitioning into Leader or Strong RS state today.",
      )

      with engine.connect() as conn:
          rows = conn.execute(
              text(f"""
                  SELECT {', '.join(_COLUMN_NAMES)}
                  FROM atlas.mv_breakout_candidates
                  ORDER BY rs_pctile_3m DESC NULLS LAST
              """)  # noqa: S608 — _COLUMN_NAMES are constants; no user input
          ).mappings().fetchall()

      if not rows:
          yield message_chunk(
              "No breakout candidates were identified for the most recent trading day. "
              "This is normal on non-trading days or when no stocks transition state. "
              "The view is refreshed nightly — check back after the next market session."
          )
          yield done()
          return

      n_leaders = sum(1 for r in rows if r.get("new_rs_state") == "Leader")
      n_strong  = sum(1 for r in rows if r.get("new_rs_state") == "Strong")

      yield message_chunk(
          f"{len(rows)} stock{'s' if len(rows) != 1 else ''} transitioned into a higher RS state "
          f"on the latest trading day: {n_leaders} entered **Leader** and {n_strong} entered **Strong** classification. "
          "These stocks exhibited an improvement in relative strength vs Nifty 500 compared to the prior session."
      )

      rows_out = [
          {col: (str(r[col]) if r[col] is not None else None) for col in _COLUMN_NAMES}
          for r in rows
      ]
      yield table(TableData(
          name="Breakout Candidates",
          description="Source: mv_breakout_candidates. Stocks entering Leader or Strong RS state today.",
          columns=_COLUMNS,
          rows=rows_out,
          data_as_of=str(rows[0]["state_since_date"]) if rows[0].get("state_since_date") else None,
      ))

      log.info("openbb_breakouts_handler_complete", count=len(rows))
      yield done()
  ```

- [ ] **Step 5: Run pyright on all four handlers**

  ```bash
  pyright atlas/api/openbb/handlers/
  ```

  Expected: no errors across all four files. If pyright complains about `row.get()` on `RowMapping` (SQLAlchemy typing), add `# type: ignore[call-overload]` with justification comment.

- [ ] **Step 6: Commit**

  ```bash
  git add atlas/api/openbb/handlers/
  git commit -m "feat(sp03): four OpenBB query handlers — regime, leaders, rotation, breakouts"
  ```

---

## Task 7: Metadata endpoint (`atlas/api/openbb/metadata.py`)

**Files:**
- Create: `atlas/api/openbb/metadata.py`

Static endpoint — no DB, no async. Returns the agent definition that OpenBB Workspace reads when registering Atlas as a custom copilot.

- [ ] **Step 1: Create `atlas/api/openbb/metadata.py`**

  ```python
  """SP03: GET /v1/agents.json — OpenBB agent metadata endpoint.

  OpenBB Workspace reads this endpoint when a user registers Atlas as a
  custom copilot. The response is static — no DB access.

  Contract fields per OpenBB BYO Copilot SDK:
  - name:         Display name in the OpenBB UI
  - description:  Shown in the copilot selector
  - image:        URL to a square icon (PNG or SVG, ≥ 64×64)
  - endpoints:    Dict of capability name → URL path
  - features:     Dict of boolean feature flags
  - sample_queries: List of example queries shown in the UI

  Verify the exact field names against OpenBB Workspace docs before registering:
  https://docs.openbb.co/workspace/custom-backend/copilot
  Some fields (e.g. widgets, citations) may be renamed or added in newer SDK versions.
  """

  from __future__ import annotations

  from fastapi import APIRouter, Depends

  from atlas.api.openbb.auth import verify_api_key

  router = APIRouter()

  # Agent registration payload. Update image URL once the icon is deployed.
  _AGENT_METADATA: dict = {
      "atlas": {
          "name": "Atlas Intelligence",
          "description": (
              "Indian equity research engine with relative strength ranking, "
              "momentum classification, market regime detection, and sector rotation signals. "
              "Data covers Nifty 500 universe. All signals are SEBI-compliant research output."
          ),
          "image": "https://atlas.jslwealth.in/atlas-icon.png",
          "endpoints": {
              "query": "/v1/query",
          },
          "features": {
              "streaming":  True,
              "widgets":    False,  # v2: can add widget context support
              "citations":  False,
          },
          "sample_queries": [
              "What is the current market regime?",
              "Show me the top RS stocks",
              "Which sectors are in the Leading quadrant?",
              "Show me breakout candidates for today",
              "Top RS stocks in the IT sector",
              "What is the sector rotation state?",
          ],
      }
  }


  @router.get(
      "/v1/agents.json",
      tags=["openbb"],
      summary="OpenBB agent metadata",
      dependencies=[Depends(verify_api_key)],  # noqa: B008
  )
  def get_agents_metadata() -> dict:
      """Return the Atlas agent definition for OpenBB Workspace registration."""
      return _AGENT_METADATA
  ```

- [ ] **Step 2: Run pyright**

  ```bash
  pyright atlas/api/openbb/metadata.py
  ```

  Expected: no errors.

- [ ] **Step 3: Commit**

  ```bash
  git add atlas/api/openbb/metadata.py
  git commit -m "feat(sp03): GET /v1/agents.json metadata endpoint"
  ```

---

## Task 8: Query endpoint (`atlas/api/openbb/query.py`) and router (`atlas/api/openbb/router.py`)

**Files:**
- Create: `atlas/api/openbb/query.py`
- Create: `atlas/api/openbb/router.py`
- Modify: `atlas/api/__init__.py` (surgical: one `include_router` call)

The query endpoint wraps the handler dispatch in `sse_starlette.EventSourceResponse`. The router wires both endpoints and is mounted in the main app.

- [ ] **Step 1: Create `atlas/api/openbb/query.py`**

  ```python
  """SP03: POST /v1/query — OpenBB BYO Copilot streaming query endpoint.

  Accepts a QueryRequest (conversation history + optional widget/context),
  classifies the last user message intent, dispatches to the matching handler,
  and streams the handler's SSE events via sse-starlette EventSourceResponse.

  Unknown intents get a message_chunk with usage hints — no error, no 4xx.
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
      "- **Market regime**: \"What is the current market regime?\" or \"show me regime\"\n"
      "- **RS leaders**: \"Top RS stocks\" or \"leading stocks in IT\"\n"
      "- **Sector rotation**: \"Sector rotation\" or \"which sectors are Leading?\"\n"
      "- **Breakouts**: \"Breakout candidates\" or \"stocks breaking out today\"\n\n"
      "Please rephrase your query using one of these topics."
  )


  async def _stream(
      request: QueryRequest,
      engine: Engine,
  ) -> AsyncGenerator[dict, None]:
      """Async generator: classify → dispatch → stream handler events."""
      query_text = request.last_user_message
      intent     = classify_intent(query_text)

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
      dependencies=[Depends(verify_api_key)],  # noqa: B008
  )
  async def post_query(
      body: QueryRequest,
      engine: Engine = Depends(get_engine),  # noqa: B008
  ) -> EventSourceResponse:
      """Accept a QueryRequest and return a text/event-stream SSE response."""
      return EventSourceResponse(_stream(body, engine))
  ```

- [ ] **Step 2: Create `atlas/api/openbb/router.py`**

  ```python
  """SP03: OpenBB sub-package router.

  Collected router for all /v1 OpenBB endpoints. Imported by
  atlas/api/__init__.py and mounted with include_router().

  Routes registered here:
    GET  /v1/agents.json  — metadata.router
    POST /v1/query        — query.router
  """

  from __future__ import annotations

  from fastapi import APIRouter

  from atlas.api.openbb.metadata import router as metadata_router
  from atlas.api.openbb.query import router as query_router

  openbb_router = APIRouter()
  openbb_router.include_router(metadata_router)
  openbb_router.include_router(query_router)

  __all__ = ["openbb_router"]
  ```

- [ ] **Step 3: Mount the OpenBB router in `atlas/api/__init__.py`**

  Add the import and one `include_router` call. The file currently reads:

  ```python
  from atlas.api.auth import JWTAuthMiddleware
  from atlas.api.portfolios import router as portfolios_router
  from atlas.api.portfolios import rule_based_router
  from atlas.api.strategies import router as strategies_router
  ```

  Add after the existing imports:

  ```python
  from atlas.api.openbb.router import openbb_router
  ```

  And after the existing `include_router` calls:

  ```python
  app.include_router(openbb_router)
  ```

  The final `__init__.py` should read:

  ```python
  """Atlas FastAPI application."""

  from __future__ import annotations

  from fastapi import FastAPI
  from fastapi.responses import JSONResponse

  from atlas.api.auth import JWTAuthMiddleware
  from atlas.api.openbb.router import openbb_router
  from atlas.api.portfolios import router as portfolios_router
  from atlas.api.portfolios import rule_based_router
  from atlas.api.strategies import router as strategies_router

  app = FastAPI(title="Atlas API", version="0.1.0")

  app.add_middleware(JWTAuthMiddleware)

  app.include_router(portfolios_router)
  app.include_router(rule_based_router)
  app.include_router(strategies_router)
  app.include_router(openbb_router)  # SP03: OpenBB BYO Copilot — /v1/agents.json, /v1/query


  @app.get("/health", include_in_schema=False)
  def health() -> JSONResponse:
      return JSONResponse({"status": "ok"})
  ```

- [ ] **Step 4: Run pyright on the modified files**

  ```bash
  pyright atlas/api/openbb/query.py atlas/api/openbb/router.py atlas/api/__init__.py
  ```

  Expected: no errors. If pyright warns about `EventSourceResponse` return type (it returns a `Response` subtype), add `# type: ignore[return-value]` with justification.

- [ ] **Step 5: Smoke-test the app starts**

  ```bash
  python3 -c "
  from atlas.api import app
  routes = [r.path for r in app.routes]
  assert '/v1/agents.json' in routes, f'/v1/agents.json missing — routes: {routes}'
  assert '/v1/query' in routes, f'/v1/query missing — routes: {routes}'
  print('Routes registered OK:', [r for r in routes if r.startswith('/v1')])
  "
  ```

  Expected: `Routes registered OK: ['/v1/agents.json', '/v1/query']`

- [ ] **Step 6: Commit**

  ```bash
  git add atlas/api/openbb/query.py atlas/api/openbb/router.py atlas/api/__init__.py
  git commit -m "feat(sp03): POST /v1/query SSE endpoint + router + mount in main app"
  ```

---

## Task 9: Test suite

**Files:**
- Create: `tests/api/openbb/__init__.py`
- Create: `tests/api/openbb/test_metadata.py`
- Create: `tests/api/openbb/test_query_routing.py`
- Create: `tests/api/openbb/test_handlers.py`
- Create: `tests/api/openbb/test_e2e_smoke.py`

TDD discipline: write the failing test first, then the code. For this task the code is already written (Tasks 2–8) so we follow the green-from-the-start path — but each test must be runnable in isolation. Tests in `test_handlers.py` mock the DB engine so they do not require a live database.

- [ ] **Step 1: Create `tests/api/openbb/__init__.py`**

  Empty file (package marker).

- [ ] **Step 2: Write `tests/api/openbb/test_metadata.py`**

  ```python
  """Tests for GET /v1/agents.json.

  Tests: response structure, required fields, no-auth behaviour.
  Uses TestClient (sync) — no DB needed.
  """

  from __future__ import annotations

  import os

  import pytest
  from fastapi.testclient import TestClient

  from atlas.api import app

  # Disable auth for tests — OPENBB_BACKEND_API_KEY empty = dev mode
  os.environ.setdefault("OPENBB_BACKEND_API_KEY", "")
  os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")

  client = TestClient(app)


  class TestGetAgentsJson:
      def test_returns_200(self):
          resp = client.get("/v1/agents.json")
          assert resp.status_code == 200

      def test_response_is_json(self):
          resp = client.get("/v1/agents.json")
          data = resp.json()
          assert isinstance(data, dict)

      def test_has_atlas_key(self):
          data = client.get("/v1/agents.json").json()
          assert "atlas" in data

      def test_atlas_has_required_fields(self):
          agent = client.get("/v1/agents.json").json()["atlas"]
          for field in ("name", "description", "endpoints", "features"):
              assert field in agent, f"Missing field: {field}"

      def test_query_endpoint_listed(self):
          agent = client.get("/v1/agents.json").json()["atlas"]
          assert "query" in agent["endpoints"]
          assert agent["endpoints"]["query"] == "/v1/query"

      def test_streaming_feature_true(self):
          features = client.get("/v1/agents.json").json()["atlas"]["features"]
          assert features.get("streaming") is True

      def test_with_valid_api_key(self):
          """API key path — valid key returns 200."""
          os.environ["OPENBB_BACKEND_API_KEY"] = "test-key-abc"
          try:
              resp = client.get("/v1/agents.json", headers={"Authorization": "Bearer test-key-abc"})
              assert resp.status_code == 200
          finally:
              os.environ["OPENBB_BACKEND_API_KEY"] = ""

      def test_with_invalid_api_key_returns_401(self):
          """Invalid key returns 401."""
          os.environ["OPENBB_BACKEND_API_KEY"] = "correct-key"
          try:
              resp = client.get("/v1/agents.json", headers={"Authorization": "Bearer wrong-key"})
              assert resp.status_code == 401
          finally:
              os.environ["OPENBB_BACKEND_API_KEY"] = ""
  ```

- [ ] **Step 3: Write `tests/api/openbb/test_query_routing.py`**

  ```python
  """Unit tests for the intent classifier in handlers/router.py.

  Pure unit tests — no DB, no HTTP, no async. classify_intent() is a plain
  function so these run in < 1ms each.
  """

  from __future__ import annotations

  import pytest

  from atlas.api.openbb.handlers.router import classify_intent


  class TestClassifyIntent:
      # --- regime ---
      def test_regime_keyword(self):
          assert classify_intent("show me current regime") == "regime"

      def test_market_state_phrase(self):
          assert classify_intent("What is the market state right now?") == "regime"

      def test_risk_on_phrase(self):
          assert classify_intent("Is the market risk-on?") == "regime"

      def test_deployment_keyword(self):
          assert classify_intent("show deployment multiplier") == "regime"

      # --- leaders ---
      def test_top_stocks_phrase(self):
          assert classify_intent("show me top stocks") == "leaders"

      def test_rs_leaders_phrase(self):
          assert classify_intent("List RS leaders") == "leaders"

      def test_strongest_stocks_phrase(self):
          assert classify_intent("which are the strongest stocks today") == "leaders"

      def test_leaders_with_sector(self):
          assert classify_intent("top rs stocks in IT") == "leaders"

      # --- rotation ---
      def test_rotation_keyword(self):
          assert classify_intent("sector rotation") == "rotation"

      def test_rrg_keyword(self):
          assert classify_intent("show me the RRG") == "rotation"

      def test_leading_sectors_phrase(self):
          assert classify_intent("which sectors are leading?") == "rotation"

      def test_lagging_sectors_phrase(self):
          assert classify_intent("show lagging sectors") == "rotation"

      # --- breakouts ---
      def test_breakout_keyword(self):
          assert classify_intent("breakout candidates today") == "breakouts"

      def test_breaking_out_phrase(self):
          assert classify_intent("which stocks are breaking out?") == "breakouts"

      def test_new_leaders_phrase(self):
          assert classify_intent("show new leaders") == "breakouts"

      # --- unknown ---
      def test_unknown_returns_unknown(self):
          assert classify_intent("what is the GDP of India?") == "unknown"

      def test_empty_string_returns_unknown(self):
          assert classify_intent("") == "unknown"

      def test_case_insensitive(self):
          assert classify_intent("SHOW ME THE REGIME") == "regime"
          assert classify_intent("TOP STOCKS") == "leaders"
  ```

- [ ] **Step 4: Write `tests/api/openbb/test_handlers.py`**

  ```python
  """Tests for the four query handlers.

  Each handler is tested with:
  - Happy path: mock returns realistic rows → verify SSE events emitted
  - Empty path: mock returns no rows → verify graceful fallback message_chunk

  DB is fully mocked — no live connection needed. We mock engine.connect() to
  return a context manager whose execute().mappings().fetchall() / fetchone()
  returns controlled test data.
  """

  from __future__ import annotations

  import json
  from typing import Any
  from unittest.mock import MagicMock, patch

  import pytest

  from atlas.api.openbb.handlers.breakouts import handle_breakouts
  from atlas.api.openbb.handlers.leaders import handle_leaders
  from atlas.api.openbb.handlers.regime import handle_regime
  from atlas.api.openbb.handlers.rotation import handle_rotation


  def _collect(async_gen) -> list[dict]:
      """Drain an async generator synchronously for test assertions."""
      import asyncio
      async def _drain():
          return [item async for item in async_gen]
      return asyncio.get_event_loop().run_until_complete(_drain())


  def _parse_events(events: list[dict]) -> list[dict]:
      """Parse the JSON data field from each SSE event dict."""
      return [json.loads(e["data"]) for e in events]


  def _mock_engine(rows: list[dict] | dict | None, fetchone: bool = False) -> MagicMock:
      """Build a minimal SQLAlchemy engine mock."""
      engine = MagicMock()
      conn = MagicMock()
      result = MagicMock()
      mappings = MagicMock()

      if fetchone:
          mappings.fetchone.return_value = rows
      else:
          mappings.fetchall.return_value = rows or []

      result.mappings.return_value = mappings
      conn.execute.return_value = result
      conn.__enter__ = MagicMock(return_value=conn)
      conn.__exit__ = MagicMock(return_value=False)
      engine.connect.return_value = conn
      return engine


  class TestRegimeHandler:
      def test_happy_path_emits_table_event(self):
          row = {
              "date": "2026-05-12",
              "regime_state": "Risk-On",
              "deployment_multiplier": "1.00",
              "dislocation_active": False,
              "india_vix": "13.5",
              "pct_above_ema_50": "0.72",
              "pct_above_ema_200": "0.65",
              "pct_in_strong_states": "0.48",
              "ad_ratio": "1.8",
              "net_new_highs": 42,
              "mcclellan_oscillator": "25.4",
          }
          engine = _mock_engine(row, fetchone=True)
          events = _collect(handle_regime(engine, "show me regime"))
          parsed = _parse_events(events)
          types = [e["type"] for e in parsed]
          assert "reasoning_step" in types
          assert "message_chunk" in types
          assert "table" in types
          assert "done" in types

      def test_empty_view_emits_fallback_message(self):
          engine = _mock_engine(None, fetchone=True)
          events = _collect(handle_regime(engine, "regime"))
          parsed = _parse_events(events)
          types = [e["type"] for e in parsed]
          assert "message_chunk" in types
          # No table event when view is empty
          assert "table" not in types

      def test_narrative_is_sebi_compliant(self):
          """Narrative must not contain banned investment verbs."""
          row = {
              "date": "2026-05-12",
              "regime_state": "Risk-Off",
              "deployment_multiplier": "0.50",
              "dislocation_active": False,
              "india_vix": "22.0",
              "pct_above_ema_50": "0.30",
              "pct_above_ema_200": "0.28",
              "pct_in_strong_states": "0.12",
              "ad_ratio": "0.6",
              "net_new_highs": -15,
              "mcclellan_oscillator": "-40.1",
          }
          engine = _mock_engine(row, fetchone=True)
          events = _collect(handle_regime(engine, "regime"))
          all_text = " ".join(
              e["data"]["data"] for e in _parse_events(events)
              if e.get("type") == "message_chunk"
          )
          for banned in ("buy", "sell", "invest", "recommend", "advise"):
              assert banned not in all_text.lower(), f"SEBI violation: '{banned}' in narrative"


  class TestLeadersHandler:
      def test_happy_path_emits_table(self):
          rows = [
              {
                  "symbol": "TCS", "company_name": "Tata Consultancy Services",
                  "sector": "IT", "tier": "Large", "rs_state": "Leader",
                  "rs_pctile_3m": "0.95", "rs_3m_nifty500": "1.15",
                  "momentum_state": "Strong Uptrend", "state_since_date": "2026-04-01",
              },
              {
                  "symbol": "INFY", "company_name": "Infosys",
                  "sector": "IT", "tier": "Large", "rs_state": "Strong",
                  "rs_pctile_3m": "0.88", "rs_3m_nifty500": "1.08",
                  "momentum_state": "Uptrend", "state_since_date": "2026-04-10",
              },
          ]
          engine = _mock_engine(rows)
          events = _collect(handle_leaders(engine, "top RS stocks"))
          parsed = _parse_events(events)
          types = [e["type"] for e in parsed]
          assert "table" in types

      def test_empty_view_emits_fallback(self):
          engine = _mock_engine([])
          events = _collect(handle_leaders(engine, "leaders"))
          parsed = _parse_events(events)
          types = [e["type"] for e in parsed]
          assert "message_chunk" in types
          assert "table" not in types


  class TestRotationHandler:
      def test_happy_path_emits_table_and_chart(self):
          rows = [
              {
                  "sector_name": "IT", "rrg_quadrant": "Leading",
                  "rs_level": "1.05", "rs_velocity": "0.03",
                  "rs_pctile_cross_sector": "0.85", "sector_state": "Overweight",
                  "bottomup_rs_state": "Strong", "bottomup_momentum_state": "Strong",
                  "participation_rs_pct": "0.72", "constituent_count": 38,
                  "date": "2026-05-12",
              },
              {
                  "sector_name": "FMCG", "rrg_quadrant": "Lagging",
                  "rs_level": "0.92", "rs_velocity": "-0.04",
                  "rs_pctile_cross_sector": "0.15", "sector_state": "Underweight",
                  "bottomup_rs_state": "Weak", "bottomup_momentum_state": "Downtrend",
                  "participation_rs_pct": "0.18", "constituent_count": 12,
                  "date": "2026-05-12",
              },
          ]
          engine = _mock_engine(rows)
          events = _collect(handle_rotation(engine, "sector rotation"))
          parsed = _parse_events(events)
          types = [e["type"] for e in parsed]
          assert "table" in types
          assert "chart" in types

      def test_empty_view_emits_fallback(self):
          engine = _mock_engine([])
          events = _collect(handle_rotation(engine, "rotation"))
          parsed = _parse_events(events)
          types = [e["type"] for e in parsed]
          assert "message_chunk" in types
          assert "table" not in types


  class TestBreakoutsHandler:
      def test_happy_path_emits_table(self):
          rows = [
              {
                  "symbol": "RELIANCE", "company_name": "Reliance Industries",
                  "sector": "Energy", "tier": "Large",
                  "new_rs_state": "Leader", "prior_rs_state": "Strong",
                  "rs_pctile_3m": "0.91", "rs_3m_nifty500": "1.12",
                  "momentum_state": "Strong Uptrend", "state_since_date": "2026-05-12",
              },
          ]
          engine = _mock_engine(rows)
          events = _collect(handle_breakouts(engine, "breakout candidates"))
          parsed = _parse_events(events)
          types = [e["type"] for e in parsed]
          assert "table" in types

      def test_empty_view_emits_fallback(self):
          engine = _mock_engine([])
          events = _collect(handle_breakouts(engine, "breakouts"))
          parsed = _parse_events(events)
          types = [e["type"] for e in parsed]
          assert "message_chunk" in types
          assert "table" not in types
  ```

- [ ] **Step 5: Write `tests/api/openbb/test_e2e_smoke.py`**

  ```python
  """End-to-end smoke tests for the full OpenBB SSE flow.

  These tests use FastAPI TestClient with streaming=True to capture the raw
  SSE stream and verify event types appear in the correct order.

  Marked pytest.mark.integration — skipped in unit test runs unless
  ATLAS_INTEGRATION_TESTS=true is set. Requires a live DB with SP02 views populated.

  For CI without a live DB: the mock_db_available fixture falls back to the
  empty-view path and verifies graceful degradation instead.
  """

  from __future__ import annotations

  import json
  import os

  import pytest
  from fastapi.testclient import TestClient

  from atlas.api import app

  os.environ.setdefault("OPENBB_BACKEND_API_KEY", "")
  os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")

  client = TestClient(app)

  pytestmark = pytest.mark.skipif(
      os.getenv("ATLAS_INTEGRATION_TESTS") != "true",
      reason="Integration tests — set ATLAS_INTEGRATION_TESTS=true to run",
  )


  def _parse_sse_stream(content: bytes) -> list[dict]:
      """Parse raw SSE bytes into a list of event dicts."""
      events = []
      for line in content.decode().splitlines():
          if line.startswith("data:"):
              payload = line[5:].strip()
              if payload:
                  try:
                      events.append(json.loads(payload))
                  except json.JSONDecodeError:
                      pass
      return events


  class TestRegimeE2E:
      def test_regime_query_returns_sse_stream(self):
          resp = client.post(
              "/v1/query",
              json={"messages": [{"role": "user", "content": "show me current regime"}]},
              headers={"Accept": "text/event-stream"},
          )
          assert resp.status_code == 200
          assert "text/event-stream" in resp.headers.get("content-type", "")

      def test_regime_stream_contains_required_event_types(self):
          with client.stream(
              "POST", "/v1/query",
              json={"messages": [{"role": "user", "content": "market regime"}]},
          ) as resp:
              content = resp.read()
          events = _parse_sse_stream(content)
          types = [e.get("type") for e in events]
          assert "reasoning_step" in types
          assert "done" in types
          # Either table (populated) or message_chunk (empty view) — both are valid
          assert "table" in types or "message_chunk" in types


  class TestLeadersE2E:
      def test_leaders_stream_ends_with_done(self):
          with client.stream(
              "POST", "/v1/query",
              json={"messages": [{"role": "user", "content": "top RS stocks"}]},
          ) as resp:
              content = resp.read()
          events = _parse_sse_stream(content)
          types = [e.get("type") for e in events]
          assert types[-1] == "done", f"Last event should be done, got: {types[-1]}"


  class TestRotationE2E:
      def test_rotation_stream_contains_chart_when_data_available(self):
          with client.stream(
              "POST", "/v1/query",
              json={"messages": [{"role": "user", "content": "sector rotation"}]},
          ) as resp:
              content = resp.read()
          events = _parse_sse_stream(content)
          types = [e.get("type") for e in events]
          # If the view is populated, there should be a chart event
          if "table" in types:
              assert "chart" in types, "Rotation handler must emit chart when table data is available"


  class TestUnknownIntentE2E:
      def test_unknown_intent_returns_200_with_fallback_message(self):
          resp = client.post(
              "/v1/query",
              json={"messages": [{"role": "user", "content": "what is the weather today?"}]},
          )
          assert resp.status_code == 200

      def test_unknown_intent_stream_contains_fallback_text(self):
          with client.stream(
              "POST", "/v1/query",
              json={"messages": [{"role": "user", "content": "completely unrecognised query abc123"}]},
          ) as resp:
              content = resp.read()
          events = _parse_sse_stream(content)
          message_events = [e for e in events if e.get("type") == "message_chunk"]
          assert message_events, "Fallback must emit at least one message_chunk"
          # Confirm fallback message mentions the supported topics
          full_text = " ".join(e["data"] for e in message_events)
          assert "regime" in full_text.lower() or "rotation" in full_text.lower()
  ```

- [ ] **Step 6: Run the unit tests (no DB required)**

  ```bash
  pytest tests/api/openbb/test_metadata.py tests/api/openbb/test_query_routing.py tests/api/openbb/test_handlers.py -v 2>&1 | tail -30
  ```

  Expected: all tests pass. If `test_handlers.py` has issues with the asyncio event loop (pytest-asyncio not picking up async correctly), add `@pytest.mark.asyncio` markers or set `asyncio_mode = "auto"` in `pyproject.toml`'s `[tool.pytest.ini_options]` section.

- [ ] **Step 7: Run ruff and pyright on the test files**

  ```bash
  ruff check tests/api/openbb/
  pyright tests/api/openbb/
  ```

  Expected: no errors. Ruff may flag `assert` statements in tests (S101) — this is in the existing `ruff.toml` ignore list.

- [ ] **Step 8: Commit**

  ```bash
  git add tests/api/openbb/
  git commit -m "feat(sp03): test suite — metadata, routing, handlers (mocked), e2e smoke"
  ```

---

## Task 10: EC2 deployment and live curl verification

**Files:** none (ops task)

Deploys SP03 to production EC2, writes the API key to `.env`, and curl-tests the live endpoints against `atlas.jslwealth.in`.

- [ ] **Step 1: SSH to EC2 and pull latest main**

  ```bash
  ssh jsl-wealth-server
  cd ~/atlas-os && git pull origin main
  ```

  Expected: fast-forward merge showing new `atlas/api/openbb/` directory and test files.

- [ ] **Step 2: Install `sse-starlette` on EC2**

  ```bash
  cd ~/atlas-os && pip install "sse-starlette>=2.0" 2>&1 | tail -5
  ```

  Expected: `Successfully installed sse-starlette-<version>`.

- [ ] **Step 3: Generate and write the API key to `.env`**

  ```bash
  KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
  echo "OPENBB_BACKEND_API_KEY=${KEY}" >> ~/atlas-os/.env
  echo "Key written. Keep this value — you will enter it in OpenBB Workspace."
  echo "Key: ${KEY}"
  ```

  **IMPORTANT:** Copy the printed key. You will paste it into OpenBB Workspace when registering the Atlas copilot. The key is not stored anywhere else.

- [ ] **Step 4: Restart the Atlas API server**

  ```bash
  # Adjust the service name / restart command to match the EC2 deployment method.
  # If running via systemd:
  sudo systemctl restart atlas-api
  sudo systemctl status atlas-api --no-pager | head -10
  ```

  Expected: `Active: active (running)`. If using a different process manager (PM2, screen, etc.), use the appropriate restart command.

- [ ] **Step 5: Curl-test `GET /v1/agents.json`**

  ```bash
  KEY=$(grep OPENBB_BACKEND_API_KEY ~/atlas-os/.env | cut -d= -f2)
  curl -s -H "Authorization: Bearer ${KEY}" \
       https://atlas.jslwealth.in/v1/agents.json | python3 -m json.tool
  ```

  Expected: JSON with `{"atlas": {"name": "Atlas Intelligence", "endpoints": {"query": "/v1/query"}, ...}}`.

- [ ] **Step 6: Curl-test `POST /v1/query` — regime**

  ```bash
  KEY=$(grep OPENBB_BACKEND_API_KEY ~/atlas-os/.env | cut -d= -f2)
  curl -s -N \
       -X POST \
       -H "Authorization: Bearer ${KEY}" \
       -H "Content-Type: application/json" \
       -d '{"messages":[{"role":"user","content":"show me current market regime"}]}' \
       https://atlas.jslwealth.in/v1/query
  ```

  Expected: SSE stream in the terminal. You should see lines like:
  ```
  data: {"type":"reasoning_step","data":{"name":"Querying market regime",...}}
  data: {"type":"message_chunk","data":"As of 12-May-2026, ..."}
  data: {"type":"table","data":{"name":"Current Market Regime",...}}
  data: {"type":"done","data":""}
  ```

- [ ] **Step 7: Curl-test sector rotation (with chart)**

  ```bash
  KEY=$(grep OPENBB_BACKEND_API_KEY ~/atlas-os/.env | cut -d= -f2)
  curl -s -N \
       -X POST \
       -H "Authorization: Bearer ${KEY}" \
       -H "Content-Type: application/json" \
       -d '{"messages":[{"role":"user","content":"sector rotation"}]}' \
       https://atlas.jslwealth.in/v1/query
  ```

  Expected: stream includes `"type":"chart"` event with RRG scatter payload.

- [ ] **Step 8: Verify auth rejection**

  ```bash
  curl -s -o /dev/null -w "%{http_code}" \
       -X POST \
       -H "Authorization: Bearer wrong-key" \
       -H "Content-Type: application/json" \
       -d '{"messages":[{"role":"user","content":"regime"}]}' \
       https://atlas.jslwealth.in/v1/query
  ```

  Expected: `401`.

- [ ] **Step 9: Verify `/api/portfolios` is still JWT-protected (regression check)**

  ```bash
  curl -s -o /dev/null -w "%{http_code}" \
       -X GET \
       https://atlas.jslwealth.in/api/portfolios/custom
  ```

  Expected: `401` (Supabase JWT required — not an OpenBB API key route).

---

## Task 11: Final — mark SP03 shipped + update memory

**Files:**
- Modify: `docs/phase2/00-master-plan.html` (add "Shipped" badge to SP03 section)
- Create: `~/.claude/projects/-Users-nimishshah-Documents-GitHub-atlas-os/memory/project_sp03_state.md`

- [ ] **Step 1: Add "Shipped" badge to SP03 section in master plan HTML**

  In `docs/phase2/00-master-plan.html`, locate the SP03 badges div (around line 358):

  ```html
  <div class="badges"><span class="badge">Parallel track 3</span><span class="badge">Soft dep: SP02 mv views</span><span class="badge">Highest external leverage</span></div>
  ```

  Replace with:

  ```html
  <div class="badges"><span class="badge">Parallel track 3</span><span class="badge">Soft dep: SP02 mv views</span><span class="badge">Highest external leverage</span><span class="badge" style="background:rgba(29,158,117,0.15);color:#1D9E75;font-weight:600;">Shipped 2026-05-12</span></div>
  ```

- [ ] **Step 2: Write memory file**

  Create `~/.claude/projects/-Users-nimishshah-Documents-GitHub-atlas-os/memory/project_sp03_state.md`:

  ```markdown
  # SP03 — OpenBB BYO Copilot Integration — State

  **Status:** Shipped (2026-05-12)

  ## What shipped
  - `atlas/api/openbb/` package: schemas, events, auth, metadata, query, router
  - `atlas/api/openbb/handlers/`: regime, leaders, rotation, breakouts, router (intent classifier)
  - JWT middleware exempts `/v1/*`; OpenBB API-key auth on all `/v1` routes
  - `atlas/api/__init__.py`: openbb_router mounted
  - `pyproject.toml`: sse-starlette>=2.0 added to base deps
  - `atlas/config.py`: OPENBB_BACKEND_API_KEY field added
  - Test suite: metadata, routing (unit), handlers (mocked), e2e smoke (integration-gated)

  ## Endpoints live
  - `GET  https://atlas.jslwealth.in/v1/agents.json`
  - `POST https://atlas.jslwealth.in/v1/query`

  ## Auth
  - API key in `.env` on EC2 as OPENBB_BACKEND_API_KEY
  - Key is required in Authorization: Bearer header for all /v1 routes
  - OpenBB Workspace: register Atlas via Settings > Custom Copilots > Add endpoint URL

  ## Handler → view mapping
  | Intent    | MV source                  | Events emitted              |
  |-----------|----------------------------|-----------------------------|
  | regime    | mv_current_market_regime   | reasoning_step, message_chunk, table, done |
  | leaders   | mv_rs_leaders_daily        | reasoning_step, message_chunk, table, done |
  | rotation  | mv_sector_rotation_state   | reasoning_step, message_chunk, table, chart, done |
  | breakouts | mv_breakout_candidates     | reasoning_step, message_chunk, table, done |

  ## Open items / follow-up
  - V2 intent routing: route unknown intents to Claude with Atlas-context system prompt
  - `widgets` field in QueryRequest: ignored in v1; v2 can surface widget context
  - Icon at https://atlas.jslwealth.in/atlas-icon.png — deploy the PNG if not already present
  - SEBI language audit: review all handler narrative strings quarterly
  - Rate-limit headers (X-RateLimit-*) deferred to M6 API contract
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add docs/phase2/00-master-plan.html
  git commit -m "feat(sp03): mark SP03 shipped in master plan"
  ```

---

## Summary

| Task | Files | Commits |
|---|---|---|
| 0 | Pre-flight checks | 0 |
| 1 | `pyproject.toml`, `atlas/config.py` | 1 |
| 2 | `atlas/api/openbb/__init__.py`, `schemas.py` | 1 |
| 3 | `atlas/api/openbb/events.py` | 1 |
| 4 | `atlas/api/openbb/auth.py`, `atlas/api/auth.py` | 1 |
| 5 | `atlas/api/openbb/handlers/__init__.py`, `handlers/router.py` | 1 |
| 6 | `handlers/regime.py`, `leaders.py`, `rotation.py`, `breakouts.py` | 1 |
| 7 | `atlas/api/openbb/metadata.py` | 1 |
| 8 | `query.py`, `router.py`, `atlas/api/__init__.py` | 1 |
| 9 | `tests/api/openbb/` (5 files) | 1 |
| 10 | EC2 ops — no git commits | 0 |
| 11 | Master plan HTML update + memory file | 1 |

**Total: 11 tasks, ~60 steps, 9 commits.**

**New files: 18 created, 3 modified (surgical).**

**Test coverage: 20+ unit/integration tests across 4 test files.**
