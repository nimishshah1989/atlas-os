# SP07 — Hermes-orchestrated Agent Runtime (v1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **REQUIRED PRE-FLIGHT:** Before starting any task, read `docs/phase2/00-master-plan.html` section `id="sp7"` in full and `docs/phase2/01-data-validator-agent.html` for Hermes background. The Phase 2 contract requires it. Project rules in `CLAUDE.md` enforce a planning-skill hook on writes to `atlas/**` — this plan satisfies that gate.

---

## Goal

Build four research-focused specialist agents (Sector Rotation Analyst, Stock Screener, Regime Watcher, Drift Detector) that compose Atlas's SP02 materialized views and SP05 daily-brief tables into SEBI-safe analyst-style narrative output. Specialists are tool-using LLMs: they reason, call typed read-only tools against atlas data, and emit a single ≤200-word prose response with a `data as-of` line.

Three surfaces: (a) `python scripts/run_agent.py --agent <name> --question "..."` CLI, (b) `POST /api/agents/invoke` REST endpoint behind JWT, (c) intent-routed orchestrator that picks the right specialist for free-form questions.

---

## Pivot from the master plan

The master plan lists SP07 as `Depends: SP04 + SP06`. **SP04 (graded composite scores) is HALTED** because SP01 IC measurement returned IC=0.009, below the 0.05 gate. SP07 cannot wait. v1 ships against the data layer that already exists:

- SP02 materialized views: `mv_current_market_regime`, `mv_rs_leaders_daily`, `mv_sector_rotation_state`, `mv_breakout_candidates`, `mv_deterioration_watch`
- SP05 daily briefs: `atlas_daily_briefs`
- Validator: `atlas_validator_findings`, `atlas_validator_runs`
- Pre-existing state tables: `atlas_market_regime_daily`, `atlas_sector_metrics_daily`

When SP04 lands, the tool registry adds one new tool (`get_composite_signal_score`) and the specialists get a one-line system-prompt update. The dataclasses and audit trail are unchanged.

---

## v1 simplification: skip the Hermes Agent runtime

The master plan calls for `NousResearch/hermes-agent` as the runtime. **For v1 we skip the full Hermes runtime** and build a thinner pattern on top of the OpenAI-compatible SDK already wired against Groq for SP05. Reasons:

1. Hermes is large, optionally-distributed Python with a model-server expectation. We do not need it for 4 specialists with 10-12 tools.
2. SP05 already proved Groq tool-calling (`emit_brief`) end-to-end. Reusing it cuts ~600 LOC and an EC2-side install from scope.
3. The specialist interface (`SpecialistAgent.invoke`) is the seam: SP07 v2 swaps the loop body for Hermes without touching tools, prompts, audit, or callers.

The agent loop is a deliberate ~60-line `while` that: calls Groq with the tool registry, executes any returned tool calls, appends results to messages, re-calls, and stops when the model returns a final non-tool message OR the iteration cap is hit. Iteration cap = 4 (covers a worst-case "regime → top sectors → top stocks → synthesize" plan).

---

## Architecture

Five layers, fully isolated inside `atlas/agents/specialists/` and `atlas/agents/tools/`:

```
                    ┌────────────────────────────────────────────────────┐
                    │  scripts/run_agent.py  /  POST /api/agents/invoke  │
                    └───────────────────┬────────────────────────────────┘
                                        │
                            ┌───────────▼──────────┐
                            │  Orchestrator (LLM   │
                            │  intent classifier   │
                            │  with keyword fast   │
                            │  path)               │
                            └───────────┬──────────┘
                                        │
        ┌──────────────┬────────────────┼────────────────┬──────────────┐
        ▼              ▼                ▼                ▼              ▼
  SectorRotation   StockScreener   RegimeWatcher   DriftDetector  (future agents)
       │               │                │                │
       └───────────────┴────────────────┴────────────────┘
                                │
                       ┌────────▼────────┐
                       │  Tool Registry  │  (10-12 read-only tools)
                       └────────┬────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
        SP02 MVs           SP05 briefs    Validator findings
```

### Layer 1: Tool registry (`atlas/agents/tools/`)

- `tools/registry.py` — central `Tool` dataclass + `TOOL_REGISTRY` dict. Pure Python; no DB binding. Converts to Groq tool format via `as_groq_tool()`.
- `tools/atlas_queries.py` — read-only `Engine`-bound functions (one per tool). Mirror the OpenBB handler SQL but return plain Python dicts/lists (not SSE events).

Ten tools v1:

| Tool name | Args | Backing source |
|---|---|---|
| `get_current_regime` | — | `mv_current_market_regime` |
| `get_regime_history` | n_days | `atlas_market_regime_daily` |
| `get_sector_rotation_quadrants` | — | `mv_sector_rotation_state` |
| `get_top_rs_stocks` | n, sector? | `mv_rs_leaders_daily` |
| `get_breakout_candidates` | n | `mv_breakout_candidates` |
| `get_deterioration_watch` | n | `mv_deterioration_watch` |
| `get_recent_findings` | severity?, n | `atlas_validator_findings` |
| `get_finding_summary` | n_days | aggregate `atlas_validator_findings` |
| `get_distribution_stats` | metric_column, table | distribution percentiles over recent state table |
| `get_latest_brief` | — | `atlas_daily_briefs` |

The tool registry is a `dict[str, Tool]`. Each `Tool` holds: `name`, `description`, `parameters` (JSON Schema), `fn` (`Callable[[Engine, ...], dict]`). Specialists are constructed with a subset of tool names.

### Layer 2: Base agent (`atlas/agents/specialists/base.py`)

`SpecialistAgent` ABC with:

- `name: str` — short identifier ("sector_rotation")
- `description: str` — one-line capability
- `system_prompt: str` — SEBI-safe research preamble + agent mission
- `tool_names: tuple[str, ...]` — which tools this specialist has access to
- `invoke(question: str, *, engine, client=None) -> AgentResult` — the loop

`AgentResult` dataclass: `narrative`, `tool_calls` (list of `{tool, args, result_keys}` for audit), `model`, `input_tokens`, `output_tokens`, `iterations`, `data_as_of` (extracted from the most recent date in any tool response).

`_run_loop()` (private):
1. Build messages = `[{system}, {user: question}]`
2. For up to `MAX_ITERS=4`:
   a. Call Groq with `tools=` registry subset, `tool_choice="auto"`.
   b. If response has no tool_calls → final narrative; break.
   c. Else execute each tool call, append `{tool_call_id, role:tool, name, content:json.dumps(result)}` to messages.
3. Banned-word scan on final narrative (lift `BANNED_WORDS` from `atlas/intelligence/briefs/prompts.py`).

### Layer 3: Specialists (one file each)

- `sector_rotation.py` — tools: `get_current_regime`, `get_sector_rotation_quadrants`, `get_top_rs_stocks`. System prompt: "Analyst that explains sector rotation by RRG quadrant and RS metrics".
- `stock_screener.py` — tools: `get_top_rs_stocks`, `get_breakout_candidates`, `get_deterioration_watch`, `get_current_regime`. System prompt: "Free-form criteria → ranked stock list with explanation".
- `regime_watcher.py` — tools: `get_current_regime`, `get_regime_history`, `get_latest_brief`. System prompt: "Reports current market regime, the delta from yesterday, and breadth context".
- `drift_detector.py` — tools: `get_recent_findings`, `get_finding_summary`, `get_distribution_stats`. System prompt: "Reports recent anomalies and distribution-check results".

Each system prompt:
- Lifts the SEBI safety preamble from `atlas/intelligence/briefs/prompts.py::SYSTEM_PROMPT` (first ~6 lines).
- Names the specialist ("I am the Sector Rotation Analyst…").
- Lists allowed tools.
- Mandates plain prose, 100–200 words, no markdown headers.
- Mandates a "Data as of {YYYY-MM-DD}" closing line.
- Forbids `BANNED_WORDS` (verified at runtime).

### Layer 4: Orchestrator (`atlas/agents/specialists/orchestrator.py`)

`route(question: str) -> str` returns the specialist name. Strategy:

1. Keyword fast path (extend SP03 `_KEYWORD_TABLE` pattern):
   - `regime|risk-on|risk-off|deployment` → `regime_watcher`
   - `rotation|quadrant|leading|lagging|improving|weakening|rrg` → `sector_rotation`
   - `drift|anomaly|finding|distribution|outlier` → `drift_detector`
   - everything else → `stock_screener` (default)
2. (Future v1.1): Groq classification fallback when no keyword matches and the question is genuinely ambiguous. v1 ships keyword-only — it covers the 4 specialists cleanly.

`invoke_routed(question, *, engine, client=None) -> AgentResult` does route → load specialist → invoke.

### Layer 5: Surfaces

- `scripts/run_agent.py` — argparse CLI: `--agent <name>`, `--question "..."`, `--list-agents`, `--no-route` (force specialist). Returns text to stdout + JSON summary on stderr if `--json`. Exit codes: 0 success, 2 invalid args, 4 missing `GROQ_API_KEY`.
- `atlas/api/agents.py` — FastAPI `APIRouter(prefix="/api/agents", tags=["agents"])`. `POST /api/agents/invoke` body `{agent: str | "auto", question: str}` → returns `AgentResult` JSON. One-line register in `atlas/api/__init__.py`. **Auth: NOT exempt** (drops through the existing JWTAuthMiddleware; ATLAS_AUTH_DISABLED in dev).

### Layer 6: Audit (migration 038)

`atlas.atlas_agent_invocations` table — one row per `invoke()`. Stores: `id`, `agent_name`, `question`, `narrative`, `tool_calls` (JSONB), `model`, `input_tokens`, `output_tokens`, `iterations`, `data_as_of`, `caller` ("cli" | "api"), `user_id` (nullable; populated when called via authenticated API), `created_at`. Audit-trail only — no enforcement reads.

---

## SEBI-safe prompt reuse

The four specialists are research narrators, not advisors. The constraints from `atlas/intelligence/briefs/prompts.py` apply verbatim:
- Banned verbs: `buy, sell, invest, recommend, advise, target price`
- Required vocabulary: "signals strength", "ranks highly", "shows deterioration", "appears on the watchlist"
- No forecasts, no directional calls, no "winners/losers"
- Closing line is a description, not an action

`BANNED_WORDS` and a small `SEBI_PREAMBLE` constant are exported from a new `atlas/agents/specialists/_sebi.py` (avoids cross-context import of `atlas.intelligence` from `atlas.agents`). The constants are duplicated by reference once; if the language drifts, prompts.py is still the source of truth and a follow-up unifies them.

---

## File structure to create / modify

```
migrations/versions/038_create_atlas_agent_invocations.py    # CREATE — audit table
atlas/agents/specialists/__init__.py                         # CREATE — exports
atlas/agents/specialists/_sebi.py                            # CREATE — BANNED_WORDS + SEBI_PREAMBLE
atlas/agents/specialists/base.py                             # CREATE — SpecialistAgent ABC + loop
atlas/agents/specialists/sector_rotation.py                  # CREATE
atlas/agents/specialists/stock_screener.py                   # CREATE
atlas/agents/specialists/regime_watcher.py                   # CREATE
atlas/agents/specialists/drift_detector.py                   # CREATE
atlas/agents/specialists/orchestrator.py                     # CREATE — keyword routing
atlas/agents/tools/__init__.py                               # CREATE — exports
atlas/agents/tools/registry.py                               # CREATE — Tool + TOOL_REGISTRY
atlas/agents/tools/atlas_queries.py                          # CREATE — read-only Engine fns
scripts/run_agent.py                                         # CREATE — CLI
atlas/api/agents.py                                          # CREATE — REST router
atlas/api/__init__.py                                        # MODIFY — register router (1 line)
tests/agents/specialists/__init__.py                         # CREATE — empty
tests/agents/specialists/test_base.py                        # CREATE — loop unit tests
tests/agents/specialists/test_sector_rotation.py             # CREATE — 2 tests
tests/agents/specialists/test_stock_screener.py              # CREATE — 2 tests
tests/agents/specialists/test_regime_watcher.py              # CREATE — 2 tests
tests/agents/specialists/test_drift_detector.py              # CREATE — 2 tests
tests/agents/specialists/test_orchestrator.py                # CREATE — routing tests
tests/agents/tools/__init__.py                               # CREATE — empty
tests/agents/tools/test_registry.py                          # CREATE — tool registry conversion
tests/agents/tools/test_atlas_queries.py                     # CREATE — query smoke
tests/agents/test_api_smoke.py                               # CREATE — FastAPI TestClient
```

Estimated 19 new files, 1 modified (one-line register). Each source file targets < 250 LOC.

---

## Hard rules (from caller)

1. New bounded context: `atlas.agents.specialists` and `atlas.agents.tools` live under `atlas.agents` (already in `CONTEXTS`).
2. Read-only DB access only. Tool functions use `engine.connect()`, never `engine.begin()`. The only writer is the audit-trail INSERT, which lives in `atlas/api/agents.py` (the API layer), not in `atlas/agents/`.
3. `GROQ_API_KEY` is the only LLM credential. SP05's `_make_client()` pattern is reused.
4. Conventional commit prefixes: `feat(sp07):`, `test(sp07):`, `chore(sp07):`. Co-author footer per CLAUDE.md.
5. `POST /api/agents/*` is behind JWT. DO NOT add `/api/agents` to `_EXEMPT_PREFIXES` in `atlas/api/auth.py`. In dev, `ATLAS_AUTH_DISABLED=true` bypasses (the existing pattern).
6. Pre-commit hooks must pass on every commit (`file-size-limit`, `module-boundaries`, `no-magic-thresholds`, `verify-decisions-chain`, ruff, mypy/pyright).
7. DO NOT push to GitHub — main session handles that.
8. DO NOT touch files outside `atlas/agents/`, `scripts/run_agent.py`, `atlas/api/agents.py` (created), `atlas/api/__init__.py` (one line), `migrations/versions/038_*.py`, and the test files listed above.

---

## Task 0: Pre-flight verification

**Files:** none created/modified.

- [ ] **Step 1: Confirm alembic head is 037**
  ```bash
  grep -l 'down_revision' migrations/versions/037_create_atlas_daily_briefs.py
  ```
  Expected: returns the file path. SP07 adds 038 on top.

- [ ] **Step 2: Confirm `openai` SDK is installed**
  ```bash
  python3 -c "import openai; print(openai.__version__)" 2>&1 | head -3
  ```
  Expected: prints a version (≥1.50). Already added by SP05.

- [ ] **Step 3: Confirm SP02 MVs are referenced by atlas/intelligence**
  ```bash
  grep -l "mv_current_market_regime\|mv_sector_rotation_state" atlas/intelligence/briefs/context.py
  ```
  Expected: matches.

- [ ] **Step 4: Confirm `atlas/agents/specialists/` does NOT exist**
  ```bash
  ls atlas/agents/specialists 2>&1
  ```
  Expected: `No such file or directory`.

- [ ] **Step 5: Confirm CONTEXTS includes `atlas.agents`**
  ```bash
  grep "atlas.agents" scripts/hooks/check_module_boundaries.py
  ```
  Expected: matches line ~35.

---

## Task 1: Migration 038 — atlas_agent_invocations

**Files:** Create `migrations/versions/038_create_atlas_agent_invocations.py`.

Mirror migration 037 structure. Table columns:
- `id UUID PK`
- `agent_name VARCHAR(64) NOT NULL`
- `question TEXT NOT NULL`
- `narrative TEXT NOT NULL`
- `tool_calls JSONB NOT NULL DEFAULT '[]'::jsonb`
- `model VARCHAR(64) NOT NULL`
- `input_tokens INTEGER`
- `output_tokens INTEGER`
- `iterations SMALLINT NOT NULL`
- `data_as_of DATE`
- `caller VARCHAR(16) NOT NULL CHECK (caller IN ('cli','api','test'))`
- `user_id TEXT` (nullable)
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Indexes:
- `(agent_name, created_at DESC)`
- `(created_at DESC)`

`revision = "038"`, `down_revision = "037"`. Use `op.execute(sa.text(...))` per existing migration style.

---

## Task 2: Tool registry + atlas_queries

**Files:**
- `atlas/agents/tools/__init__.py`
- `atlas/agents/tools/registry.py`
- `atlas/agents/tools/atlas_queries.py`

### Step 1: `registry.py`

```python
@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    fn: Callable[..., Any]

    def as_groq_tool(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def build_registry(engine: Engine) -> dict[str, Tool]:
    """Build the registry binding each tool to the live Engine."""
    ...
```

Why a builder (vs module-level dict): tests inject a fake engine without monkey-patching module state.

### Step 2: `atlas_queries.py`

Ten functions:
- `query_current_regime(engine: Engine) -> dict`
- `query_regime_history(engine: Engine, *, n_days: int = 5) -> list[dict]`
- `query_sector_rotation_quadrants(engine: Engine) -> dict` (returns `{quadrants: {Leading: [...], Improving: [...], ...}, as_of}`)
- `query_top_rs_stocks(engine: Engine, *, n: int = 10, sector: str | None = None) -> list[dict]`
- `query_breakout_candidates(engine: Engine, *, n: int = 10) -> list[dict]`
- `query_deterioration_watch(engine: Engine, *, n: int = 10) -> list[dict]`
- `query_recent_findings(engine: Engine, *, severity: str | None = None, n: int = 20) -> list[dict]`
- `query_finding_summary(engine: Engine, *, n_days: int = 7) -> dict`
- `query_distribution_stats(engine: Engine, *, metric_column: str, table: str) -> dict` — with strict allow-list on `metric_column` and `table` (whitelist constants).
- `query_latest_brief(engine: Engine) -> dict | None`

All SQL uses `text()` with bind params; the only f-string interpolation is for the whitelist-validated column/table identifiers in `query_distribution_stats`, with `# noqa: S608 — whitelisted constants`.

JSON Schema for each tool is co-located at the bottom of `registry.py` as `_PARAMETER_SCHEMAS: dict[str, dict]`.

---

## Task 3: SEBI constants + Base agent

**Files:**
- `atlas/agents/specialists/__init__.py`
- `atlas/agents/specialists/_sebi.py`
- `atlas/agents/specialists/base.py`

### `_sebi.py`

```python
BANNED_WORDS: tuple[str, ...] = (
    "buy", "sell", "invest", "invests", "investing",
    "recommend", "recommends", "recommendation",
    "advise", "advises", "advice",
    "target price",
)

SEBI_PREAMBLE = """\
You are a SEBI-compliant Indian equity research narrator. Describe observed
state and named metrics only. Use research language: "signals strength",
"ranks highly", "shows deterioration", "appears on the watchlist".

HARD CONSTRAINTS:
1. NEVER use these verbs: buy, sell, invest, recommend, advise, target price.
2. No forecasts, projections, or directional calls.
3. No stocks labeled "winners" or "losers".
4. Output plain prose, 100-200 words, no markdown.
5. Close with a single line: "Data as of {YYYY-MM-DD}".
"""
```

### `base.py`

```python
@dataclass(frozen=True)
class AgentResult:
    narrative: str
    tool_calls: list[dict]
    model: str
    input_tokens: int | None
    output_tokens: int | None
    iterations: int
    data_as_of: date | None


class SpecialistAgent(abc.ABC):
    name: str
    description: str
    tool_names: tuple[str, ...]

    @abc.abstractmethod
    def build_system_prompt(self) -> str: ...

    def invoke(
        self, question: str, *, engine: Engine, client: Any | None = None
    ) -> AgentResult:
        registry = build_registry(engine)
        my_tools = [registry[n] for n in self.tool_names]
        _client = client if client is not None else _make_groq_client()
        return _run_loop(
            client=_client,
            system_prompt=self.build_system_prompt(),
            user_question=question,
            tools=my_tools,
            model=_MODEL,
        )
```

`_run_loop()` is the ~60-line driver. `_MODEL = "llama-3.3-70b-versatile"`. `MAX_ITERS = 4`. Final narrative passes through `_scan_banned_words()` (copy of SP05 helper). On banned hit: raise `SEBIComplianceError`. The data_as_of date is extracted by scanning tool results for the most recent `date` / `as_of` / `state_since_date` field.

---

## Task 4: Specialist agents (4 files)

**Files:**
- `atlas/agents/specialists/sector_rotation.py`
- `atlas/agents/specialists/stock_screener.py`
- `atlas/agents/specialists/regime_watcher.py`
- `atlas/agents/specialists/drift_detector.py`

Each file is ~60 LOC: subclass `SpecialistAgent`, set `name`, `description`, `tool_names`, implement `build_system_prompt()` that concatenates `SEBI_PREAMBLE` + agent-specific mission paragraph.

Example for `sector_rotation.py`:

```python
class SectorRotationAnalyst(SpecialistAgent):
    name = "sector_rotation"
    description = "Analyzes sector RRG quadrants and RS metrics."
    tool_names = ("get_current_regime", "get_sector_rotation_quadrants",
                   "get_top_rs_stocks")

    def build_system_prompt(self) -> str:
        return SEBI_PREAMBLE + """

I am the Sector Rotation Analyst. I read the RRG quadrant assignments and
RS metrics for all NIFTY sectors and explain which sectors are Leading,
Improving, Weakening, or Lagging. When asked about specific sectors I name
them. I call tools to ground every claim in current data.

Available tools:
- get_current_regime: the market regime context
- get_sector_rotation_quadrants: full quadrant assignment for all sectors
- get_top_rs_stocks: leading stocks (optionally filtered by sector)

Workflow: usually start with get_sector_rotation_quadrants, then pull
get_current_regime for the macro overlay. Use get_top_rs_stocks only when
the question explicitly asks about leaders inside a sector.
"""
```

---

## Task 5: Orchestrator + intent classifier

**Files:** `atlas/agents/specialists/orchestrator.py`

Pattern from `atlas/api/openbb/handlers/router.py`. Keyword table:

```python
_INTENT_TABLE: list[tuple[str, tuple[str, ...]]] = [
    ("drift_detector", ("drift", "anomaly", "anomalies", "finding", "findings",
                         "distribution", "outlier", "sensibility", "violation")),
    ("regime_watcher", ("regime", "risk-on", "risk on", "risk-off", "risk off",
                         "deployment", "market state", "dislocation")),
    ("sector_rotation", ("rotation", "quadrant", "rrg", "leading sectors",
                          "lagging sectors", "weakening", "improving sectors",
                          "sectors")),
    # default fallthrough → stock_screener
]
```

```python
def classify_specialist(question: str) -> str:
    lower = question.lower()
    for name, triggers in _INTENT_TABLE:
        if any(t in lower for t in triggers):
            return name
    return "stock_screener"  # default


def get_specialist(name: str) -> SpecialistAgent:
    return _REGISTRY[name]


def invoke_routed(
    question: str, *, engine: Engine, client: Any | None = None
) -> tuple[str, AgentResult]:
    name = classify_specialist(question)
    agent = get_specialist(name)
    result = agent.invoke(question, engine=engine, client=client)
    return name, result
```

`_REGISTRY` is a module-level dict mapping name → instantiated specialist.

---

## Task 6: CLI (`scripts/run_agent.py`)

argparse:
- `--agent` (one of: sector_rotation, stock_screener, regime_watcher, drift_detector, auto). Default: `auto`.
- `--question` (required).
- `--list-agents` flag to print names + descriptions and exit.
- `--json` print raw JSON of AgentResult to stdout instead of formatted text.
- `--persist` write a row to `atlas_agent_invocations` (default off).

Exit codes:
- 0 success
- 2 invalid args
- 4 missing `GROQ_API_KEY`
- 5 banned-word compliance failure

Behavior follows `scripts/generate_daily_brief.py` structure: import path setup, get_engine, route or pick specialist, invoke, format output. The 10-line snippet target in the example output:

```
[Sector Rotation Analyst]
{narrative_text}

Tool calls:
  - get_sector_rotation_quadrants() -> 14 sectors classified
  - get_current_regime() -> Risk-On

Tokens: in=820 out=240   Iterations: 2
Data as of: 2026-05-08
```

---

## Task 7: REST endpoint (`atlas/api/agents.py`)

```python
class InvokeRequest(BaseModel):
    agent: str = "auto"  # "auto" | "sector_rotation" | ... | etc.
    question: str = Field(min_length=1, max_length=2000)


class InvokeResponse(BaseModel):
    agent: str
    narrative: str
    tool_calls: list[dict]
    model: str
    input_tokens: int | None
    output_tokens: int | None
    iterations: int
    data_as_of: str | None


router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.post("/invoke")
def invoke_agent(
    body: InvokeRequest,
    request: Request,
    engine: Engine = Depends(get_engine),
) -> InvokeResponse:
    user_id = getattr(getattr(request.state, "user", None), "user_id", None)
    if body.agent == "auto":
        name, result = invoke_routed(body.question, engine=engine)
    else:
        agent = get_specialist(body.agent)  # raises KeyError → 400
        result = agent.invoke(body.question, engine=engine)
        name = body.agent
    _persist_invocation(engine, name, body.question, result, caller="api",
                         user_id=user_id)
    return InvokeResponse(...)
```

Single one-line register in `atlas/api/__init__.py`:

```python
from atlas.api.agents import router as agents_router
...
app.include_router(agents_router)
```

`_EXEMPT_PREFIXES` in `auth.py` is NOT modified. `/api/agents/*` flows through the JWT middleware (or is bypassed when `ATLAS_AUTH_DISABLED=true`).

---

## Task 8: Tests

Each specialist has 2 tests (happy path + empty data). Pattern from `tests/intelligence/briefs/test_generator.py`:
- Mock the OpenAI client to return tool_calls then a final message.
- Mock the engine via `unittest.mock.MagicMock` or an in-memory dict-backed fake.
- Assert: returned `AgentResult.narrative` non-empty, no banned words, expected `tool_calls` invoked.

### Test files

- `test_base.py`: loop terminates on first non-tool message; loop hits MAX_ITERS cap; banned-word raises `SEBIComplianceError`.
- `test_sector_rotation.py`: (1) sample quadrants → narrative names sectors; (2) empty MV → narrative says "data unavailable" without crashing.
- `test_stock_screener.py`: (1) sample top stocks → returns ranked names; (2) empty → "no candidates".
- `test_regime_watcher.py`: (1) Risk-On regime → narrative mentions deployment multiplier; (2) Unknown regime → fallback message.
- `test_drift_detector.py`: (1) findings present → narrative summarizes by severity; (2) zero findings → "no anomalies detected today".
- `test_orchestrator.py`: each keyword bucket routes correctly; default falls through to screener; case-insensitive.
- `test_registry.py`: `as_groq_tool()` produces valid OpenAI/Groq schema; build_registry returns 10 tools.
- `test_atlas_queries.py`: each query function compiles and returns the expected dict shape (mocked engine via SQLAlchemy `Mock`); enforces whitelist in `query_distribution_stats`.
- `test_api_smoke.py`: FastAPI TestClient hits `POST /api/agents/invoke` with mocked specialist; returns 200 with InvokeResponse shape.

Target: ≥18 tests total. Run via `pytest tests/agents/` — all green.

---

## Task 9: Smoke test

After all commits pass pre-commit, run end-to-end against live data.

- [ ] **Step 1:** Verify `GROQ_API_KEY` is set in env (or `.env`).
- [ ] **Step 2:** `python scripts/run_agent.py --agent regime_watcher --question "What is the current market regime?"`
- [ ] **Step 3:** Capture stdout. Confirm narrative is one paragraph naming the regime and breadth, ending with "Data as of …".
- [ ] **Step 4:** `python scripts/run_agent.py --agent sector_rotation --question "Which sectors are rotating?"`
- [ ] **Step 5:** Capture stdout. Confirm narrative names quadrants and sectors.
- [ ] **Step 6:** Note total tokens consumed across both runs.

If the live DB is unreachable from the local machine, the smoke runs on EC2:
```bash
ssh ubuntu@13.206.34.214 'cd ~/atlas-os && GROQ_API_KEY=... python scripts/run_agent.py --agent regime_watcher --question "..."'
```

---

## Commit cadence

8–10 commits expected:

1. `feat(sp07): add migration 038 atlas_agent_invocations`
2. `feat(sp07): tool registry + read-only atlas queries`
3. `feat(sp07): SEBI preamble + base SpecialistAgent loop`
4. `feat(sp07): 4 specialists (sector rotation, screener, regime, drift)`
5. `feat(sp07): keyword orchestrator + invoke_routed`
6. `feat(sp07): scripts/run_agent.py CLI`
7. `feat(sp07): POST /api/agents/invoke endpoint`
8. `test(sp07): specialist + orchestrator + tool + API tests`
9. (if needed) `chore(sp07): pyright/ruff fixes`
10. (if needed) `feat(sp07): smoke-test verified — paste outputs into commit body`

Each commit includes the Co-Authored-By footer per CLAUDE.md.

---

## NOT in scope

- Full Hermes Agent runtime (deferred to SP07 v2 once 4 specialists are battle-tested).
- Local Llama mode for DPDP-sensitive queries (deferred; SP07 v2).
- Scheduled cron invocations (deferred — invoke via CLI or REST only in v1).
- Frontend `/intelligence/agents` chat UI (deferred — REST contract stabilizes first).
- Per-agent persistent memory ("rotation has been brewing for 3 weeks" pattern) — deferred to v2.
- Streaming SSE output. v1 is request/response. SSE can be added behind a new endpoint without touching specialists.
- `get_signal_ic`, `get_threshold_proposals`, `run_signal_validation`, `explain_state_transition` tools — these require SP04 graded scores or SP08 infrastructure that does not exist yet.

## What already exists

- **OpenBB handlers** (`atlas/api/openbb/handlers/*.py`) read the same MVs and produce SSE events. SP07 reuses the SQL shape but returns plain dicts (no SSE).
- **Groq + tool-calling integration** (`atlas/intelligence/briefs/generator.py`) — copied pattern for `_make_groq_client()` and the tool-call response parser.
- **SEBI banned words** (`atlas/intelligence/briefs/prompts.py::BANNED_WORDS`) — duplicated once into `_sebi.py` to keep `atlas.agents` from importing `atlas.intelligence` (bounded-context rule).
- **JWT auth middleware** (`atlas/api/auth.py`) — `/api/agents/*` automatically flows through it; no new code.
- **Validator findings table** (`atlas_validator_findings`) — already populated by the Phase A validator agent; drift_detector reads it.

## Failure modes

- **Groq rate limit / 5xx:** specialist invoke surfaces a `RuntimeError`. CLI exits non-zero. API returns 502 with an error envelope. Test: mocked client raises → assertion that loop does not swallow.
- **Tool function raises (e.g., bad SQL):** `_run_loop` catches the exception, formats it into a tool-result message, and lets the model re-plan or apologise. The exception is logged structlog `agent_tool_error`. Test: tool fn raises → final narrative contains "tool error" or graceful fallback.
- **Empty MV / Unknown regime:** specialist short-circuits with a fallback message (no Groq call needed if every tool returns empty). Test: empty fixtures → narrative says "data unavailable".
- **Banned word in final narrative:** `_scan_banned_words()` hits → `SEBIComplianceError` raised; CLI exit 5; API 500. Audit row is NOT persisted.
- **MAX_ITERS exceeded:** loop returns the most recent assistant message even if it still wanted a tool call. Logged structlog `agent_max_iters`.
- **Auth disabled in prod:** caller's responsibility; no defense in this PR. The auth middleware exists; production config is the gate.

## Worktree parallelization

Sequential implementation — every task either depends on the previous (Tasks 3 → 4 → 5) or is too small to warrant a worktree split. No parallelization recommended.

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | NO REVIEWS YET (PLAN) | inline plan, agentic exec |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

VERDICT: NO REVIEWS YET — agentic execution per caller instructions; the plan itself satisfies the planning-skill PreToolUse hook on `atlas/**` writes.
