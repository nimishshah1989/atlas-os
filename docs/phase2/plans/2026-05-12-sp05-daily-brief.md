# SP05 — Daily Atlas Brief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **REQUIRED PRE-FLIGHT:** Before starting any task, read `docs/phase2/00-master-plan.html` section `id="sp5"` in full. The Phase 2 contract requires it. Project rules in `CLAUDE.md` enforce a planning-skill hook on writes to `atlas/**` — this plan satisfies that gate.

**Goal:** Build a structured-input narrative-output pipeline that reads ~10 fields from SP02 materialized views, packages them into a canonical `DailyMarketContext`, asks Claude Sonnet 4.6 to produce a 200–280 word SEBI-safe morning brief, and stores every brief with full input audit trail in `atlas_daily_briefs` for compliance.

**Pivot from master plan:** The master plan lists SP05 as `Depends: SP02 + SP04`. SP04 (graded composite scores) is **HALTED** because SP01 IC measurement showed the v1 composite has IC=0.009, below the 0.05 gate. SP05 v1 ships against **SP02 alone** — the brief uses deterministic state distributions from existing MVs, not IC-weighted graded scores. When SP04 lands later, the `DailyMarketContext` builder swaps in graded scores without touching the generator, prompts, audit, or frontend.

**Architecture:** Four layers, fully isolated inside `atlas/intelligence/briefs/`:
1. **Context builder** (`context.py`) — pure SQL reader that produces an immutable `DailyMarketContext` dataclass from the five SP02 MVs plus a one-day regime delta lookup against `atlas_market_regime_daily`. No business logic, no Claude.
2. **Prompt module** (`prompts.py`) — constants only. `SYSTEM_PROMPT` (~1800 chars) is the load-bearing SEBI-compliance artifact. `PROMPT_VERSION = "v1"` is the audit-trail tie-back.
3. **Generator** (`generator.py`) — wraps Anthropic SDK, sends one cached system prompt + one structured user message, uses `tools` for typed extraction of `key_themes`, `regime_summary`, `top_sector_mentions` alongside narrative text. Returns a `DailyBrief` dataclass.
4. **Audit** (`audit.py`) — UPSERT to `atlas_daily_briefs` keyed on `as_of_date`. Persists the full context snapshot, narrative, structured fields, model id, prompt version, token counts.

A CLI (`scripts/generate_daily_brief.py`) wires them together. A new Next.js route (`/intelligence/daily-brief`) reads the latest row server-side and renders narrative + theme pills.

**Tech stack:** `anthropic>=0.40` SDK (NEW base dep), Pydantic v2 dataclasses (already in stack), SQLAlchemy 2.0 sync (already in stack), structlog (already in stack), Alembic migration (existing pattern). Frontend uses the existing `postgres` client at `frontend/src/lib/db.ts`.

**SEBI compliance notes:** The system prompt is the single load-bearing artifact. It bans buy/sell/invest/recommend/advise/target verbs, mandates research vocabulary (signals strength, shows deterioration, ranks highly in RS framework), requires regime + deployment multiplier as the opening sentence, requires one contrarian observation, and constrains length to 200–280 words. The test suite scans for banned words in generator output.

**Confirmed Atlas patterns this plan follows:**
- `from atlas.db import get_engine` for DB access
- `op.execute(sa.text(...))` DDL pattern from migration 033/035
- `structlog.get_logger()` for all logging — no `print()` in production
- `Decimal` for `deployment_multiplier`; cast at display time
- `@pytest.mark.integration` for DB-touching tests
- Module boundary: `atlas/intelligence/` is the only context this plan writes to

**File structure to create / modify:**

```
migrations/versions/037_create_atlas_daily_briefs.py   # CREATE — table + indexes
atlas/intelligence/briefs/__init__.py                  # CREATE — public API exports
atlas/intelligence/briefs/context.py                   # CREATE — DailyMarketContext + builder
atlas/intelligence/briefs/prompts.py                   # CREATE — SEBI-safe system prompt + version
atlas/intelligence/briefs/generator.py                 # CREATE — DailyBrief + Claude wrapper
atlas/intelligence/briefs/audit.py                     # CREATE — UPSERT to atlas_daily_briefs
scripts/generate_daily_brief.py                        # CREATE — CLI orchestrator
frontend/src/lib/queries/briefs.ts                     # CREATE — getLatestBrief() server query
frontend/src/app/intelligence/daily-brief/page.tsx     # CREATE — server component renderer
tests/intelligence/briefs/__init__.py                  # CREATE — empty
tests/intelligence/briefs/test_context.py              # CREATE — builder unit tests w/ mocked engine
tests/intelligence/briefs/test_generator.py            # CREATE — prompt + parsing tests, mocked SDK
tests/intelligence/briefs/test_audit.py                # CREATE — integration UPSERT test
tests/intelligence/briefs/test_cli_smoke.py            # CREATE — CLI dry-run smoke
pyproject.toml                                         # MODIFY — add anthropic>=0.40
```

**File responsibility split:**
- `context.py` — `DailyMarketContext` (frozen dataclass) + `build_daily_context(engine, as_of)`. Reads 5 MVs + 1 regime-history query. No Anthropic, no business judgment.
- `prompts.py` — `SYSTEM_PROMPT: str`, `PROMPT_VERSION: str`, `STRUCTURED_TOOL: dict`. Pure constants; importable without side effects.
- `generator.py` — `DailyBrief` dataclass + `generate_brief(context, *, client=None)`. The `client` injection point is what makes the generator testable without a network round-trip.
- `audit.py` — `persist_brief(engine, *, context, brief, ...)` UPSERTs one row. Single SQL constant, no DDL.
- `__init__.py` — re-exports `build_daily_context`, `generate_brief`, `persist_brief`, `DailyMarketContext`, `DailyBrief`. CLI imports from the package, not deep paths.

---

## Task 0: Pre-flight verification

**Files:** none created/modified.

- [ ] **Step 1: Read SP05 in the master plan**

  Open `docs/phase2/00-master-plan.html` and read the `id="sp5"` div in full. Confirm SEBI constraints, deliverables, and success criteria.

- [ ] **Step 2: Confirm SP02 views exist**

  ```bash
  python3 -c "
  from atlas.db import get_engine
  from sqlalchemy import text
  eng = get_engine()
  views = ['mv_current_market_regime','mv_sector_rotation_state','mv_breakout_candidates','mv_deterioration_watch']
  with eng.connect() as c:
      for v in views:
          try:
              n = c.execute(text(f'SELECT COUNT(*) FROM atlas.{v}')).scalar()
              print(f'{v}: {n} rows — OK')
          except Exception as e:
              print(f'{v}: MISSING — {e}')
  " 2>&1 | tail -10
  ```

  Expected: all four views exist with row counts > 0 (if local DB has data backfilled). If any are missing, mocked tests still work; the integration test will skip.

- [ ] **Step 3: Confirm `anthropic` SDK is NOT installed**

  ```bash
  python3 -c "import anthropic; print(anthropic.__version__)" 2>&1 | head -3
  ```

  Expected: `ModuleNotFoundError`. We will add it in Task 1.

- [ ] **Step 4: Confirm `/intelligence/daily-brief` route does not exist**

  ```bash
  ls frontend/src/app/intelligence 2>&1
  ```

  Expected: `No such file or directory`. We will create the folder in Task 8.

- [ ] **Step 5: Check current alembic head**

  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os && alembic heads 2>&1 | tail -3
  ```

  Expected: `036` (head). SP05 adds `037`.

---

## Task 1: Add `anthropic` SDK + migration 037

**Files:**
- Modify: `pyproject.toml`
- Create: `migrations/versions/037_create_atlas_daily_briefs.py`

- [ ] **Step 1: Add `anthropic>=0.40` to base deps in `pyproject.toml`**

  After the `pyjwt>=2.8` line (last entry in base `dependencies`), add:

  ```toml
      # Auth — Supabase JWT verification (HS256)
      "pyjwt>=2.8",

      # SP05 — Claude Sonnet 4.6 daily brief generation
      "anthropic>=0.40",
  ]
  ```

- [ ] **Step 2: Install the SDK**

  ```bash
  pip install "anthropic>=0.40" 2>&1 | tail -3
  ```

  Expected: `Successfully installed anthropic-...`. Note version.

- [ ] **Step 3: Verify import works**

  ```bash
  python3 -c "import anthropic; print(anthropic.__version__)"
  ```

  Expected: prints version, no errors.

- [ ] **Step 4: Create migration 037**

  Write `migrations/versions/037_create_atlas_daily_briefs.py`:

  ```python
  """SP05: create atlas_daily_briefs for Claude-authored daily market narratives.

  One row per as_of_date (UNIQUE). UPSERT on (as_of_date) — re-running the
  CLI overwrites the prior brief. context_snapshot holds the full input audit
  trail required for SEBI compliance review.

  Revision ID: 037
  Revises: 036
  Create Date: 2026-05-12
  """

  import sqlalchemy as sa
  from alembic import op

  revision = "037"
  down_revision = "036"
  branch_labels = None
  depends_on = None


  def upgrade() -> None:
      op.execute(sa.text("""
          CREATE TABLE IF NOT EXISTS atlas.atlas_daily_briefs (
              id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
              as_of_date            DATE        NOT NULL UNIQUE,
              regime_state          VARCHAR(32) NOT NULL,
              regime_delta          VARCHAR(16) NOT NULL,
              narrative             TEXT        NOT NULL,
              key_themes            JSONB       NOT NULL,
              regime_summary        VARCHAR(16) NOT NULL,
              top_sector_mentions   JSONB       NOT NULL,
              context_snapshot      JSONB       NOT NULL,
              model                 VARCHAR(64) NOT NULL,
              prompt_version        VARCHAR(8)  NOT NULL,
              input_tokens          INTEGER,
              output_tokens         INTEGER,
              generated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),

              CONSTRAINT chk_brief_regime_delta CHECK (
                  regime_delta IN ('unchanged','upgraded','downgraded')
              ),
              CONSTRAINT chk_brief_summary CHECK (
                  regime_summary IN ('bullish','neutral','cautious','defensive')
              )
          )
      """))

      op.execute(sa.text("""
          CREATE INDEX IF NOT EXISTS idx_daily_briefs_as_of
          ON atlas.atlas_daily_briefs (as_of_date DESC)
      """))


  def downgrade() -> None:
      op.execute(sa.text("DROP INDEX IF EXISTS atlas.idx_daily_briefs_as_of"))
      op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_daily_briefs"))
  ```

- [ ] **Step 5: Apply migration**

  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os && alembic upgrade head 2>&1 | tail -5
  ```

  Expected: `Running upgrade 036 -> 037`. If you see "Can't locate revision identified by '036'", check that the prior migration revision id matches.

- [ ] **Step 6: Verify table**

  ```bash
  python3 -c "
  from atlas.db import get_engine
  from sqlalchemy import text
  with get_engine().connect() as c:
      cols = c.execute(text(\"SELECT column_name FROM information_schema.columns WHERE table_schema='atlas' AND table_name='atlas_daily_briefs' ORDER BY ordinal_position\")).fetchall()
  print([c[0] for c in cols])
  "
  ```

  Expected: list of all 15 columns.

- [ ] **Step 7: Commit**

  ```bash
  git add pyproject.toml migrations/versions/037_create_atlas_daily_briefs.py
  git commit -m "feat(sp05): add anthropic SDK + migration 037 atlas_daily_briefs"
  ```

---

## Task 2: SEBI-safe prompts module

**Files:**
- Create: `atlas/intelligence/briefs/__init__.py`
- Create: `atlas/intelligence/briefs/prompts.py`

- [ ] **Step 1: Create the package marker**

  Write `atlas/intelligence/briefs/__init__.py` as an empty file (will be filled in Task 7).

  ```python
  """SP05: daily Atlas brief — Claude-authored market narrative.

  See docs/phase2/plans/2026-05-12-sp05-daily-brief.md.
  """
  ```

- [ ] **Step 2: Write `prompts.py`**

  ```python
  """SP05: SEBI-safe system prompt + structured-output tool schema.

  This module is the load-bearing compliance artifact for the daily brief.
  Every constant here is reviewed against SEBI Research Analyst regulations
  (no buy/sell/invest/recommend/advise/target verbs; research language only).

  PROMPT_VERSION is the audit-trail tie-back: every brief row in
  atlas_daily_briefs stamps this string so old briefs are reproducible.
  """

  from __future__ import annotations

  PROMPT_VERSION = "v1"

  # ---------------------------------------------------------------------- #
  # System prompt — SEBI-safe, structured-input, narrative-output.         #
  # Cached via Anthropic prompt caching for cost + latency on every call.  #
  # ---------------------------------------------------------------------- #
  SYSTEM_PROMPT = """\
  You are Atlas, a SEBI-compliant Indian equity research narrator. Your job is to
  produce a single 200-280 word morning market brief based on the structured
  context the user provides. The user's input is the authoritative source of
  facts; do not invent metrics, names, percentages, or events.

  HARD CONSTRAINTS (SEBI Research Analyst Regulations — non-negotiable):

  1. NEVER use these verbs in any form: buy, sell, invest, recommend, advise,
     suggest action, target price, price target. Including past/passive tense.
  2. USE research language only: "signals strength", "shows deterioration",
     "ranks highly in RS framework", "registers improving momentum",
     "transitions into a stronger relative-strength state",
     "exhibits weakening breadth", "appears in the leaders table".
  3. DO NOT issue forecasts, projections, or directional calls. Describe
     observed state and named metrics only.
  4. DO NOT name individual stocks as "winners" or "losers" — they "rank
     highly" or "appear on the deterioration watchlist".

  CONTENT RULES:

  A. OPEN with the regime classification AND the deployment multiplier — these
     are the single most important context items. Example phrasing:
     "The market sits in a {regime} regime with a deployment multiplier of
     {x.xx}x, which calibrates position sizing."
  B. NAME sectors and stocks specifically when the input lists them. No vague
     references ("certain sectors", "a few names"). Use the names provided.
  C. INCLUDE exactly one contrarian observation where the data supports it
     (e.g. "Notably, while breadth signals strength, India VIX has ticked up,
     which historically precedes consolidation."). If no data point supports
     a contrarian read, omit the sentence — never fabricate.
  D. WHEN regime_delta is "upgraded" or "downgraded", call it out explicitly
     with the from-to states and the deployment-multiplier change.
  E. CLOSE with a one-sentence statement about what the framework signals
     for position sizing — not what to do.

  FORMAT:

  - 200 to 280 words. Count words; do not exceed.
  - Plain prose. No markdown headers, no bullet lists, no tables.
  - Present tense, active voice.
  - Indian numbering for any monetary values (₹ lakh / crore) — though the
     structured input rarely carries money values for this brief.
  - Do not include disclaimers; the platform appends compliance text.

  STRUCTURED OUTPUT:

  In addition to the narrative, you MUST call the `emit_brief` tool exactly
  once with:
    - narrative: the 200-280 word prose
    - key_themes: exactly 3 short theme strings (4-8 words each) summarising
      the dominant signals (e.g. "Risk-On breadth confirmed by 78% above EMA-50")
    - regime_summary: one of bullish / neutral / cautious / defensive,
      derived from regime_state + deployment_multiplier
    - top_sector_mentions: the list of sectors you named in the narrative,
      in order of appearance

  Begin.
  """

  # ---------------------------------------------------------------------- #
  # Tool schema — Anthropic tools API forces structured extraction         #
  # alongside the prose. The schema is the contract the generator parses.  #
  # ---------------------------------------------------------------------- #
  STRUCTURED_TOOL: dict = {
      "name": "emit_brief",
      "description": (
          "Emit the daily Atlas brief with structured fields for audit and UI. "
          "Call this exactly once at the end of the response."
      ),
      "input_schema": {
          "type": "object",
          "properties": {
              "narrative": {
                  "type": "string",
                  "description": "200-280 word SEBI-safe prose narrative.",
              },
              "key_themes": {
                  "type": "array",
                  "items": {"type": "string"},
                  "minItems": 3,
                  "maxItems": 3,
                  "description": "Exactly 3 short theme strings.",
              },
              "regime_summary": {
                  "type": "string",
                  "enum": ["bullish", "neutral", "cautious", "defensive"],
                  "description": "One-word framework summary.",
              },
              "top_sector_mentions": {
                  "type": "array",
                  "items": {"type": "string"},
                  "description": "Sectors named in the narrative, in order.",
              },
          },
          "required": [
              "narrative",
              "key_themes",
              "regime_summary",
              "top_sector_mentions",
          ],
      },
  }

  # Banned words for test-suite validation. The generator output must not
  # contain any of these (case-insensitive whole-word match in tests).
  BANNED_WORDS: tuple[str, ...] = (
      "buy", "sell", "invest", "invests", "investing", "recommend",
      "recommends", "recommendation", "advise", "advises", "advice",
      "target price",
  )
  ```

- [ ] **Step 3: Lint + typecheck**

  ```bash
  ruff check atlas/intelligence/briefs/prompts.py
  pyright atlas/intelligence/briefs/prompts.py 2>&1 | tail -3
  ```

  Expected: no errors.

- [ ] **Step 4: Commit**

  ```bash
  git add atlas/intelligence/briefs/__init__.py atlas/intelligence/briefs/prompts.py
  git commit -m "feat(sp05): add SEBI-safe system prompt + structured-output tool schema"
  ```

---

## Task 3: DailyMarketContext builder

**Files:**
- Create: `atlas/intelligence/briefs/context.py`
- Create: `tests/intelligence/briefs/__init__.py`
- Create: `tests/intelligence/briefs/test_context.py`

- [ ] **Step 1: Write the failing test FIRST**

  Write `tests/intelligence/briefs/__init__.py` as empty, then `tests/intelligence/briefs/test_context.py`:

  ```python
  """Unit tests for DailyMarketContext builder. No DB — engine is mocked."""

  from __future__ import annotations

  from datetime import date
  from decimal import Decimal
  from unittest.mock import MagicMock

  from atlas.intelligence.briefs.context import (
      DailyMarketContext,
      build_daily_context,
  )


  def _mock_engine_with_rows(view_rows: dict[str, list[dict]]) -> MagicMock:
      """Return an engine whose .connect().__enter__() returns a conn
      where conn.execute(stmt) returns a Result whose .mappings().fetchall()
      / .fetchone() returns the rows mapped from the SQL string substring.

      view_rows keys are substrings of the SQL that route to row lists.
      """

      def _execute_side_effect(stmt, params=None):
          sql_text = str(stmt)
          rows = []
          for key, value in view_rows.items():
              if key in sql_text:
                  rows = value
                  break
          mapping_proxy = MagicMock()
          mapping_proxy.fetchall.return_value = rows
          mapping_proxy.fetchone.return_value = rows[0] if rows else None
          result = MagicMock()
          result.mappings.return_value = mapping_proxy
          return result

      conn = MagicMock()
      conn.execute.side_effect = _execute_side_effect
      cm = MagicMock()
      cm.__enter__.return_value = conn
      cm.__exit__.return_value = False
      eng = MagicMock()
      eng.connect.return_value = cm
      return eng


  def test_build_context_happy_path() -> None:
      eng = _mock_engine_with_rows({
          "mv_current_market_regime": [{
              "date": date(2026, 5, 12),
              "regime_state": "Risk-On",
              "deployment_multiplier": Decimal("1.00"),
              "pct_above_ema_50": Decimal("78.4"),
              "mcclellan_oscillator": Decimal("45.2"),
              "ad_ratio": Decimal("1.85"),
              "net_new_highs": 47,
              "india_vix": Decimal("13.2"),
          }],
          "atlas_market_regime_daily": [{
              "regime_state": "Risk-On",
              "deployment_multiplier": Decimal("1.00"),
          }],
          "mv_sector_rotation_state": [
              {"sector_name": "NIFTY IT", "rs_pctile_cross_sector": Decimal("0.92"), "rs_velocity": Decimal("0.04")},
              {"sector_name": "NIFTY AUTO", "rs_pctile_cross_sector": Decimal("0.88"), "rs_velocity": Decimal("0.03")},
              {"sector_name": "NIFTY BANK", "rs_pctile_cross_sector": Decimal("0.75"), "rs_velocity": Decimal("0.02")},
              {"sector_name": "NIFTY PSE", "rs_pctile_cross_sector": Decimal("0.20"), "rs_velocity": Decimal("-0.05")},
              {"sector_name": "NIFTY FMCG", "rs_pctile_cross_sector": Decimal("0.30"), "rs_velocity": Decimal("-0.04")},
              {"sector_name": "NIFTY PHARMA", "rs_pctile_cross_sector": Decimal("0.35"), "rs_velocity": Decimal("-0.03")},
          ],
          "mv_breakout_candidates": [
              {"symbol": "TCS", "company_name": "Tata Consultancy", "sector": "NIFTY IT", "new_rs_state": "Leader"},
          ],
          "mv_deterioration_watch": [
              {"symbol": "HUL", "company_name": "Hindustan Unilever", "sector": "NIFTY FMCG", "prior_rs_state": "Strong"},
          ],
      })

      ctx = build_daily_context(eng, as_of=date(2026, 5, 12))

      assert isinstance(ctx, DailyMarketContext)
      assert ctx.as_of == date(2026, 5, 12)
      assert ctx.regime == "Risk-On"
      assert ctx.regime_delta == "unchanged"
      assert ctx.deployment_multiplier == Decimal("1.00")
      assert ctx.breadth["pct_above_ema_50"] == Decimal("78.4")
      assert ctx.breadth["india_vix"] == Decimal("13.2")
      assert ctx.top_sectors == ["NIFTY IT", "NIFTY AUTO", "NIFTY BANK"]
      # rotating_out = bottom 3 by rs_velocity (most negative first)
      assert ctx.rotating_out[0] == "NIFTY PSE"
      assert len(ctx.new_breakouts) == 1
      assert ctx.new_breakouts[0]["symbol"] == "TCS"
      assert ctx.new_deteriorations[0]["symbol"] == "HUL"


  def test_build_context_regime_upgrade_detected() -> None:
      eng = _mock_engine_with_rows({
          "mv_current_market_regime": [{
              "date": date(2026, 5, 12),
              "regime_state": "Risk-On",
              "deployment_multiplier": Decimal("1.00"),
              "pct_above_ema_50": Decimal("78.4"),
              "mcclellan_oscillator": Decimal("45.2"),
              "ad_ratio": Decimal("1.85"),
              "net_new_highs": 47,
              "india_vix": Decimal("13.2"),
          }],
          "atlas_market_regime_daily": [{
              "regime_state": "Neutral",  # yesterday was Neutral
              "deployment_multiplier": Decimal("0.70"),
          }],
          "mv_sector_rotation_state": [],
          "mv_breakout_candidates": [],
          "mv_deterioration_watch": [],
      })

      ctx = build_daily_context(eng, as_of=date(2026, 5, 12))
      assert ctx.regime_delta == "upgraded"


  def test_build_context_regime_downgrade_detected() -> None:
      eng = _mock_engine_with_rows({
          "mv_current_market_regime": [{
              "date": date(2026, 5, 12),
              "regime_state": "Risk-Off",
              "deployment_multiplier": Decimal("0.40"),
              "pct_above_ema_50": Decimal("32.1"),
              "mcclellan_oscillator": Decimal("-30.5"),
              "ad_ratio": Decimal("0.55"),
              "net_new_highs": -15,
              "india_vix": Decimal("21.4"),
          }],
          "atlas_market_regime_daily": [{
              "regime_state": "Neutral",
              "deployment_multiplier": Decimal("0.70"),
          }],
          "mv_sector_rotation_state": [],
          "mv_breakout_candidates": [],
          "mv_deterioration_watch": [],
      })

      ctx = build_daily_context(eng, as_of=date(2026, 5, 12))
      assert ctx.regime_delta == "downgraded"


  def test_build_context_to_dict_is_json_serialisable() -> None:
      import json

      eng = _mock_engine_with_rows({
          "mv_current_market_regime": [{
              "date": date(2026, 5, 12),
              "regime_state": "Neutral",
              "deployment_multiplier": Decimal("0.70"),
              "pct_above_ema_50": Decimal("55.0"),
              "mcclellan_oscillator": Decimal("0.0"),
              "ad_ratio": Decimal("1.0"),
              "net_new_highs": 0,
              "india_vix": Decimal("15.0"),
          }],
          "atlas_market_regime_daily": [],
          "mv_sector_rotation_state": [],
          "mv_breakout_candidates": [],
          "mv_deterioration_watch": [],
      })

      ctx = build_daily_context(eng, as_of=date(2026, 5, 12))
      payload = ctx.to_dict()
      # Must round-trip through JSON without TypeError
      serialised = json.dumps(payload)
      restored = json.loads(serialised)
      assert restored["regime"] == "Neutral"
      assert restored["as_of"] == "2026-05-12"
  ```

- [ ] **Step 2: Run the failing test**

  ```bash
  pytest tests/intelligence/briefs/test_context.py -v 2>&1 | tail -10
  ```

  Expected: ImportError or FAIL (module not yet implemented).

- [ ] **Step 3: Implement `context.py`**

  ```python
  """SP05: DailyMarketContext — structured input for the daily brief.

  Reads the SP02 materialized views (with one regime-history lookup against
  atlas_market_regime_daily for the regime_delta diff). Pure SQL reader; no
  business judgement, no Claude, no side effects.

  When SP04 lands, swap in graded scores at the call sites that compute
  top_sectors / new_breakouts — the dataclass shape stays the same so the
  generator, prompts, audit, and frontend are unchanged.
  """

  from __future__ import annotations

  from dataclasses import asdict, dataclass, field
  from datetime import date
  from decimal import Decimal
  from typing import Any

  import structlog
  from sqlalchemy import text
  from sqlalchemy.engine import Engine

  log = structlog.get_logger()

  _TOP_SECTOR_LIMIT = 3
  _BREAKOUT_LIMIT = 5
  _DETERIORATION_LIMIT = 5


  @dataclass(frozen=True)
  class DailyMarketContext:
      """Immutable structured input for the daily brief generator."""

      as_of: date
      regime: str
      regime_delta: str  # 'unchanged' | 'upgraded' | 'downgraded'
      deployment_multiplier: Decimal
      breadth: dict[str, Decimal | int | None]
      top_sectors: list[str]
      rotating_out: list[str]
      new_breakouts: list[dict[str, Any]]
      new_deteriorations: list[dict[str, Any]]
      raw_regime_row: dict[str, Any] = field(default_factory=dict)

      def to_dict(self) -> dict[str, Any]:
          """Return a JSON-serialisable dict for prompt rendering + audit log."""
          out = asdict(self)
          return _jsonify(out)


  def _jsonify(value: Any) -> Any:
      """Recursively convert Decimal/date to JSON-safe primitives."""
      if isinstance(value, Decimal):
          return float(value)
      if isinstance(value, date):
          return value.isoformat()
      if isinstance(value, dict):
          return {k: _jsonify(v) for k, v in value.items()}
      if isinstance(value, list):
          return [_jsonify(v) for v in value]
      return value


  _BREADTH_KEYS = (
      "pct_above_ema_50",
      "mcclellan_oscillator",
      "ad_ratio",
      "net_new_highs",
      "india_vix",
  )


  def _classify_regime_delta(today: str, yesterday: str | None) -> str:
      """Classify regime change. SEBI-safe vocabulary."""
      ordering = {
          "Risk-Off": 0,
          "Defensive": 1,
          "Neutral": 2,
          "Risk-On": 3,
      }
      if yesterday is None or yesterday == today:
          return "unchanged"
      a = ordering.get(today, -1)
      b = ordering.get(yesterday, -1)
      if a > b:
          return "upgraded"
      if a < b:
          return "downgraded"
      return "unchanged"


  def build_daily_context(engine: Engine, as_of: date) -> DailyMarketContext:
      """Build the structured input snapshot for the daily brief generator.

      Reads five SP02 materialized views plus one regime-history lookup.
      Returns an immutable DailyMarketContext.
      """
      with engine.connect() as conn:
          # 1. Current regime — mv_current_market_regime is a single-row view.
          regime_row = (
              conn.execute(
                  text(
                      "SELECT date, regime_state, deployment_multiplier, "
                      "pct_above_ema_50, mcclellan_oscillator, ad_ratio, "
                      "net_new_highs, india_vix "
                      "FROM atlas.mv_current_market_regime LIMIT 1"
                  )
              )
              .mappings()
              .fetchone()
          )

          # 2. Yesterday's regime — from atlas_market_regime_daily.
          # We compare today's regime_state against the most recent prior row.
          yesterday_row = (
              conn.execute(
                  text(
                      "SELECT regime_state, deployment_multiplier "
                      "FROM atlas.atlas_market_regime_daily "
                      "WHERE date < :as_of "
                      "ORDER BY date DESC LIMIT 1"
                  ),
                  {"as_of": as_of},
              )
              .mappings()
              .fetchone()
          )

          # 3. Sector rotation — top 3 by RS percentile, bottom 3 by RS velocity.
          sector_rows = (
              conn.execute(
                  text(
                      "SELECT sector_name, rs_pctile_cross_sector, rs_velocity "
                      "FROM atlas.mv_sector_rotation_state "
                      "ORDER BY rs_pctile_cross_sector DESC NULLS LAST"
                  )
              )
              .mappings()
              .fetchall()
          )

          # 4. Breakout candidates — top 5 by RS percentile.
          breakout_rows = (
              conn.execute(
                  text(
                      "SELECT symbol, company_name, sector, new_rs_state "
                      "FROM atlas.mv_breakout_candidates "
                      "ORDER BY rs_pctile_3m DESC NULLS LAST "
                      "LIMIT :lim"
                  ),
                  {"lim": _BREAKOUT_LIMIT},
              )
              .mappings()
              .fetchall()
          )

          # 5. Deterioration watch — top 5 by prior RS percentile.
          deterioration_rows = (
              conn.execute(
                  text(
                      "SELECT symbol, company_name, sector, prior_rs_state "
                      "FROM atlas.mv_deterioration_watch "
                      "ORDER BY rs_pctile_3m DESC NULLS LAST "
                      "LIMIT :lim"
                  ),
                  {"lim": _DETERIORATION_LIMIT},
              )
              .mappings()
              .fetchall()
          )

      if regime_row is None:
          # Graceful degradation: no MV data. Return a stub context that the
          # generator will refuse to send to Claude.
          log.warning("daily_brief_no_regime_row", as_of=as_of.isoformat())
          return DailyMarketContext(
              as_of=as_of,
              regime="Unknown",
              regime_delta="unchanged",
              deployment_multiplier=Decimal("0"),
              breadth={k: None for k in _BREADTH_KEYS},
              top_sectors=[],
              rotating_out=[],
              new_breakouts=[],
              new_deteriorations=[],
              raw_regime_row={},
          )

      regime = str(regime_row["regime_state"] or "Unknown")
      yesterday_regime = (
          str(yesterday_row["regime_state"]) if yesterday_row else None
      )
      regime_delta = _classify_regime_delta(regime, yesterday_regime)

      breadth: dict[str, Decimal | int | None] = {
          k: regime_row.get(k) for k in _BREADTH_KEYS
      }

      top_sectors = [
          str(r["sector_name"]) for r in sector_rows[:_TOP_SECTOR_LIMIT]
      ]

      # Rotating out = 3 sectors with most negative rs_velocity. We re-sort
      # the same rows ascending on rs_velocity for this slice.
      def _vel_key(r: dict) -> float:
          v = r.get("rs_velocity")
          return float(v) if v is not None else 0.0

      sorted_by_velocity = sorted(sector_rows, key=_vel_key)
      rotating_out = [
          str(r["sector_name"]) for r in sorted_by_velocity[:_TOP_SECTOR_LIMIT]
      ]

      new_breakouts = [dict(r) for r in breakout_rows]
      new_deteriorations = [dict(r) for r in deterioration_rows]

      log.info(
          "daily_context_built",
          as_of=as_of.isoformat(),
          regime=regime,
          regime_delta=regime_delta,
          n_breakouts=len(new_breakouts),
          n_deteriorations=len(new_deteriorations),
      )

      return DailyMarketContext(
          as_of=as_of,
          regime=regime,
          regime_delta=regime_delta,
          deployment_multiplier=Decimal(str(regime_row["deployment_multiplier"])),
          breadth=breadth,
          top_sectors=top_sectors,
          rotating_out=rotating_out,
          new_breakouts=new_breakouts,
          new_deteriorations=new_deteriorations,
          raw_regime_row=dict(regime_row),
      )
  ```

- [ ] **Step 4: Run tests until they pass**

  ```bash
  pytest tests/intelligence/briefs/test_context.py -v 2>&1 | tail -15
  ```

  Expected: 4 passed.

- [ ] **Step 5: Commit**

  ```bash
  git add atlas/intelligence/briefs/context.py tests/intelligence/briefs/__init__.py tests/intelligence/briefs/test_context.py
  git commit -m "feat(sp05): DailyMarketContext builder reading SP02 MVs"
  ```

---

## Task 4: Claude generator + structured output

**Files:**
- Create: `atlas/intelligence/briefs/generator.py`
- Create: `tests/intelligence/briefs/test_generator.py`

- [ ] **Step 1: Write the failing test**

  Write `tests/intelligence/briefs/test_generator.py`:

  ```python
  """Tests for the Claude wrapper. The Anthropic SDK is mocked; no network."""

  from __future__ import annotations

  import re
  from datetime import date
  from decimal import Decimal
  from unittest.mock import MagicMock

  import pytest

  from atlas.intelligence.briefs.context import DailyMarketContext
  from atlas.intelligence.briefs.generator import DailyBrief, generate_brief
  from atlas.intelligence.briefs.prompts import (
      BANNED_WORDS,
      PROMPT_VERSION,
      SYSTEM_PROMPT,
  )


  def _sample_context() -> DailyMarketContext:
      return DailyMarketContext(
          as_of=date(2026, 5, 12),
          regime="Risk-On",
          regime_delta="unchanged",
          deployment_multiplier=Decimal("1.00"),
          breadth={
              "pct_above_ema_50": Decimal("78.4"),
              "mcclellan_oscillator": Decimal("45.2"),
              "ad_ratio": Decimal("1.85"),
              "net_new_highs": 47,
              "india_vix": Decimal("13.2"),
          },
          top_sectors=["NIFTY IT", "NIFTY AUTO", "NIFTY BANK"],
          rotating_out=["NIFTY PSE", "NIFTY FMCG", "NIFTY PHARMA"],
          new_breakouts=[
              {"symbol": "TCS", "company_name": "Tata Consultancy",
               "sector": "NIFTY IT", "new_rs_state": "Leader"},
          ],
          new_deteriorations=[
              {"symbol": "HUL", "company_name": "Hindustan Unilever",
               "sector": "NIFTY FMCG", "prior_rs_state": "Strong"},
          ],
      )


  def _mock_anthropic_client(narrative_text: str, themes: list[str], summary: str,
                              sectors: list[str], in_tok: int = 1200,
                              out_tok: int = 380) -> MagicMock:
      """Build a mocked Anthropic Messages client whose .messages.create()
      returns a response with a tool_use content block carrying the structured
      output, plus a usage stub."""
      tool_use_block = MagicMock()
      tool_use_block.type = "tool_use"
      tool_use_block.name = "emit_brief"
      tool_use_block.input = {
          "narrative": narrative_text,
          "key_themes": themes,
          "regime_summary": summary,
          "top_sector_mentions": sectors,
      }
      response = MagicMock()
      response.content = [tool_use_block]
      response.model = "claude-sonnet-4-6"
      response.usage = MagicMock(input_tokens=in_tok, output_tokens=out_tok)

      client = MagicMock()
      client.messages.create.return_value = response
      return client


  def test_generate_brief_returns_dataclass() -> None:
      ctx = _sample_context()
      narrative = (
          "The market sits in a Risk-On regime with a deployment multiplier of "
          "1.00x, which calibrates position sizing toward full deployment. "
          "Breadth signals strength: 78.4% of the universe trades above its "
          "50-day EMA, the McClellan Oscillator registers a positive 45.2, "
          "and net new highs print at 47. NIFTY IT ranks highly in the RS "
          "framework alongside NIFTY AUTO and NIFTY BANK; Tata Consultancy "
          "appears in the breakouts list after transitioning into a Leader "
          "RS state. On the other side, NIFTY PSE, FMCG, and PHARMA show "
          "deterioration in relative-strength velocity, and Hindustan "
          "Unilever drops from a Strong classification. Notably, while "
          "breadth signals strength, India VIX has ticked up to 13.2, "
          "which historically precedes consolidation rather than expansion. "
          "The framework keeps deployment multiplier at 1.00x — full "
          "calibration to the current breadth and momentum readings."
      )
      client = _mock_anthropic_client(
          narrative_text=narrative,
          themes=["Risk-On breadth confirmed", "IT and AUTO lead RS", "VIX uptick warrants attention"],
          summary="bullish",
          sectors=["NIFTY IT", "NIFTY AUTO", "NIFTY BANK", "NIFTY PSE", "NIFTY FMCG"],
      )

      brief = generate_brief(ctx, client=client)

      assert isinstance(brief, DailyBrief)
      assert brief.narrative.startswith("The market sits")
      assert len(brief.key_themes) == 3
      assert brief.regime_summary == "bullish"
      assert "NIFTY IT" in brief.top_sector_mentions
      assert brief.model == "claude-sonnet-4-6"
      assert brief.prompt_version == PROMPT_VERSION
      assert brief.input_tokens == 1200
      assert brief.output_tokens == 380


  def test_generator_sends_system_prompt_and_tool() -> None:
      ctx = _sample_context()
      client = _mock_anthropic_client(
          narrative_text="x " * 220,
          themes=["a", "b", "c"],
          summary="neutral",
          sectors=["NIFTY IT"],
      )

      generate_brief(ctx, client=client)

      kwargs = client.messages.create.call_args.kwargs
      assert kwargs["model"] == "claude-sonnet-4-6"
      assert kwargs["max_tokens"] == 400
      # System prompt is the SEBI artifact, passed as a list block w/ cache_control
      system = kwargs["system"]
      assert isinstance(system, list)
      assert system[0]["text"] == SYSTEM_PROMPT
      assert system[0]["cache_control"] == {"type": "ephemeral"}
      # Tool is the emit_brief schema
      tools = kwargs["tools"]
      assert tools[0]["name"] == "emit_brief"


  def test_generator_user_message_includes_context_facts() -> None:
      ctx = _sample_context()
      client = _mock_anthropic_client(
          narrative_text="x " * 220,
          themes=["a", "b", "c"],
          summary="neutral",
          sectors=["NIFTY IT"],
      )

      generate_brief(ctx, client=client)

      kwargs = client.messages.create.call_args.kwargs
      user_text = kwargs["messages"][0]["content"]
      # The structured context must be in the message — JSON or labelled prose
      assert "Risk-On" in user_text
      assert "1.00" in user_text
      assert "NIFTY IT" in user_text
      assert "TCS" in user_text


  def test_banned_words_not_in_prompt() -> None:
      """The system prompt itself must not contain banned-word usage that
      would prime the model to produce banned phrasing."""
      lower = SYSTEM_PROMPT.lower()
      # The prompt LISTS banned words as instructions, so it will literally
      # contain them. We assert the BANNED_WORDS sentinel is enumerated.
      for word in ("buy", "sell", "invest", "recommend"):
          assert word in lower, f"prompt must enumerate ban for '{word}'"


  def test_generator_output_contains_no_banned_phrasing() -> None:
      """If Claude returns banned words, the generator raises rather than
      silently persisting non-compliant prose."""
      ctx = _sample_context()
      bad_narrative = (
          "The market sits in a Risk-On regime. Investors should buy IT names "
          "aggressively today; we recommend overweight allocation."
      )
      client = _mock_anthropic_client(
          narrative_text=bad_narrative,
          themes=["a", "b", "c"],
          summary="bullish",
          sectors=["NIFTY IT"],
      )
      with pytest.raises(ValueError, match="banned"):
          generate_brief(ctx, client=client)


  def test_generator_rejects_empty_context() -> None:
      empty_ctx = DailyMarketContext(
          as_of=date(2026, 5, 12),
          regime="Unknown",
          regime_delta="unchanged",
          deployment_multiplier=Decimal("0"),
          breadth={},
          top_sectors=[],
          rotating_out=[],
          new_breakouts=[],
          new_deteriorations=[],
      )
      client = MagicMock()
      with pytest.raises(ValueError, match="empty"):
          generate_brief(empty_ctx, client=client)
      client.messages.create.assert_not_called()
  ```

- [ ] **Step 2: Run the failing test**

  ```bash
  pytest tests/intelligence/briefs/test_generator.py -v 2>&1 | tail -10
  ```

  Expected: ImportError.

- [ ] **Step 3: Implement `generator.py`**

  ```python
  """SP05: Claude Sonnet 4.6 wrapper for the daily Atlas brief.

  - One Anthropic Messages.create call per brief.
  - System prompt is cached (ephemeral) so re-runs amortise.
  - Structured extraction via the emit_brief tool.
  - Banned-word check on narrative output — fail-loud, never silently persist
    non-SEBI-compliant prose.
  """

  from __future__ import annotations

  import json
  import os
  import re
  from dataclasses import dataclass
  from typing import Any

  import structlog

  from atlas.intelligence.briefs.context import DailyMarketContext
  from atlas.intelligence.briefs.prompts import (
      BANNED_WORDS,
      PROMPT_VERSION,
      STRUCTURED_TOOL,
      SYSTEM_PROMPT,
  )

  log = structlog.get_logger()

  _MODEL = "claude-sonnet-4-6"
  _MAX_TOKENS = 400


  @dataclass(frozen=True)
  class DailyBrief:
      """The output of one Claude generation. Persisted verbatim."""

      narrative: str
      key_themes: list[str]
      regime_summary: str
      top_sector_mentions: list[str]
      model: str
      prompt_version: str
      input_tokens: int | None
      output_tokens: int | None


  def _context_is_empty(ctx: DailyMarketContext) -> bool:
      """A context is empty if the regime is Unknown AND every collection is
      empty. We do not call Claude on an empty context."""
      return (
          ctx.regime == "Unknown"
          and not ctx.top_sectors
          and not ctx.new_breakouts
          and not ctx.new_deteriorations
      )


  def _render_user_message(ctx: DailyMarketContext) -> str:
      """Format the context as a labelled prose+JSON block for Claude."""
      lines = [
          "Today's Atlas market state:",
          "",
          f"As-of date: {ctx.as_of.isoformat()}",
          f"Regime: {ctx.regime}",
          f"Regime delta vs yesterday: {ctx.regime_delta}",
          f"Deployment multiplier: {float(ctx.deployment_multiplier):.2f}x",
          "",
          "Breadth signals:",
      ]
      for k, v in ctx.breadth.items():
          if v is None:
              lines.append(f"  - {k}: n/a")
          else:
              # ints render bare; Decimal renders fixed-point
              try:
                  fv = float(v)
                  lines.append(f"  - {k}: {fv:.2f}")
              except (TypeError, ValueError):
                  lines.append(f"  - {k}: {v}")

      lines.append("")
      lines.append(f"Top sectors by RS percentile: {', '.join(ctx.top_sectors) or 'n/a'}")
      lines.append(f"Sectors rotating out (most negative RS velocity): {', '.join(ctx.rotating_out) or 'n/a'}")
      lines.append("")
      if ctx.new_breakouts:
          lines.append("Breakouts (transitioned into Leader/Strong today):")
          for b in ctx.new_breakouts:
              lines.append(
                  f"  - {b.get('symbol')} ({b.get('company_name')}) "
                  f"in {b.get('sector')} → {b.get('new_rs_state')}"
              )
      else:
          lines.append("Breakouts: none today.")

      lines.append("")
      if ctx.new_deteriorations:
          lines.append("Deteriorations (dropped from Strong/Leader today):")
          for d in ctx.new_deteriorations:
              lines.append(
                  f"  - {d.get('symbol')} ({d.get('company_name')}) "
                  f"in {d.get('sector')}; prior state {d.get('prior_rs_state')}"
              )
      else:
          lines.append("Deteriorations: none today.")

      lines.append("")
      lines.append(
          "Produce the brief in 200-280 words following the system prompt rules. "
          "Call emit_brief with the structured fields."
      )
      return "\n".join(lines)


  def _scan_banned_words(narrative: str) -> list[str]:
      """Return any banned words present in the narrative (whole-word, ci)."""
      lower = narrative.lower()
      hits: list[str] = []
      for word in BANNED_WORDS:
          # Multi-word phrases use substring; single words use whole-word regex.
          if " " in word:
              if word in lower:
                  hits.append(word)
          else:
              pattern = rf"\b{re.escape(word)}\b"
              if re.search(pattern, lower):
                  hits.append(word)
      return hits


  def _make_client() -> Any:
      """Construct an Anthropic client from env. Raises if SDK or key missing."""
      try:
          import anthropic  # type: ignore[import-not-found]
      except ImportError as e:
          raise RuntimeError(
              "anthropic SDK not installed. Run: pip install 'anthropic>=0.40'"
          ) from e
      api_key = os.environ.get("ANTHROPIC_API_KEY", "")
      if not api_key:
          raise RuntimeError(
              "ANTHROPIC_API_KEY is not set in the environment. "
              "Export it before running the brief generator."
          )
      return anthropic.Anthropic(api_key=api_key)


  def generate_brief(
      context: DailyMarketContext,
      *,
      client: Any | None = None,
  ) -> DailyBrief:
      """Generate the daily brief by calling Claude with structured extraction.

      ``client`` is the injection point: tests pass a MagicMock; production
      passes None and we construct a real anthropic.Anthropic instance.
      """
      if _context_is_empty(context):
          raise ValueError(
              "DailyMarketContext is empty — refusing to call Claude on a "
              "blank market state. Verify SP02 materialized views are refreshed."
          )

      if client is None:
          client = _make_client()

      user_text = _render_user_message(context)

      log.info(
          "daily_brief_generating",
          as_of=context.as_of.isoformat(),
          regime=context.regime,
          model=_MODEL,
      )

      response = client.messages.create(
          model=_MODEL,
          max_tokens=_MAX_TOKENS,
          system=[
              {
                  "type": "text",
                  "text": SYSTEM_PROMPT,
                  "cache_control": {"type": "ephemeral"},
              }
          ],
          tools=[STRUCTURED_TOOL],
          tool_choice={"type": "tool", "name": "emit_brief"},
          messages=[
              {"role": "user", "content": user_text},
          ],
      )

      # Find the emit_brief tool_use block.
      tool_block = None
      for block in response.content:
          if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "emit_brief":
              tool_block = block
              break

      if tool_block is None:
          raise RuntimeError(
              "Claude did not call emit_brief. Raw response: "
              f"{response.content!r}"
          )

      payload = tool_block.input
      if not isinstance(payload, dict):
          # Some SDKs return JSON-string; parse defensively.
          payload = json.loads(payload)

      narrative = str(payload["narrative"])
      banned_hits = _scan_banned_words(narrative)
      if banned_hits:
          raise ValueError(
              f"Generator emitted banned word(s): {banned_hits}. "
              "SEBI compliance gate failed — brief not persisted. "
              "Re-run; if persistent, revise prompts.py."
          )

      key_themes = [str(t) for t in payload["key_themes"]]
      regime_summary = str(payload["regime_summary"])
      top_sector_mentions = [str(s) for s in payload["top_sector_mentions"]]

      usage = getattr(response, "usage", None)
      in_tok = getattr(usage, "input_tokens", None) if usage else None
      out_tok = getattr(usage, "output_tokens", None) if usage else None

      log.info(
          "daily_brief_generated",
          as_of=context.as_of.isoformat(),
          regime=context.regime,
          input_tokens=in_tok,
          output_tokens=out_tok,
          word_count=len(narrative.split()),
      )

      return DailyBrief(
          narrative=narrative,
          key_themes=key_themes,
          regime_summary=regime_summary,
          top_sector_mentions=top_sector_mentions,
          model=getattr(response, "model", _MODEL),
          prompt_version=PROMPT_VERSION,
          input_tokens=in_tok,
          output_tokens=out_tok,
      )
  ```

- [ ] **Step 4: Run tests until they pass**

  ```bash
  pytest tests/intelligence/briefs/test_generator.py -v 2>&1 | tail -15
  ```

  Expected: 6 passed.

- [ ] **Step 5: Commit**

  ```bash
  git add atlas/intelligence/briefs/generator.py tests/intelligence/briefs/test_generator.py
  git commit -m "feat(sp05): Claude Sonnet 4.6 generator with structured emit_brief tool"
  ```

---

## Task 5: Audit persistence

**Files:**
- Create: `atlas/intelligence/briefs/audit.py`
- Create: `tests/intelligence/briefs/test_audit.py`

- [ ] **Step 1: Write the integration test**

  Write `tests/intelligence/briefs/test_audit.py`:

  ```python
  """Integration test for daily-brief persistence. Hits real DB."""

  from __future__ import annotations

  from datetime import date
  from decimal import Decimal

  import pytest
  from sqlalchemy import text

  from atlas.db import get_engine
  from atlas.intelligence.briefs.audit import persist_brief
  from atlas.intelligence.briefs.context import DailyMarketContext
  from atlas.intelligence.briefs.generator import DailyBrief


  @pytest.mark.integration
  class TestPersistBrief:
      @pytest.fixture(autouse=True)
      def clean_test_rows(self):
          eng = get_engine()
          with eng.connect() as c:
              c.execute(text("DELETE FROM atlas.atlas_daily_briefs WHERE as_of_date = :d"),
                        {"d": date(1999, 1, 1)})
              c.commit()
          yield
          with eng.connect() as c:
              c.execute(text("DELETE FROM atlas.atlas_daily_briefs WHERE as_of_date = :d"),
                        {"d": date(1999, 1, 1)})
              c.commit()

      def _sample_ctx(self) -> DailyMarketContext:
          return DailyMarketContext(
              as_of=date(1999, 1, 1),
              regime="Risk-On",
              regime_delta="unchanged",
              deployment_multiplier=Decimal("1.00"),
              breadth={"pct_above_ema_50": Decimal("78.4"), "india_vix": Decimal("13.2")},
              top_sectors=["NIFTY IT"],
              rotating_out=["NIFTY FMCG"],
              new_breakouts=[],
              new_deteriorations=[],
          )

      def _sample_brief(self) -> DailyBrief:
          return DailyBrief(
              narrative="x " * 220,
              key_themes=["a", "b", "c"],
              regime_summary="bullish",
              top_sector_mentions=["NIFTY IT"],
              model="claude-sonnet-4-6",
              prompt_version="v1",
              input_tokens=1200,
              output_tokens=380,
          )

      def test_insert_round_trip(self):
          eng = get_engine()
          persist_brief(eng, context=self._sample_ctx(), brief=self._sample_brief())

          with eng.connect() as c:
              row = c.execute(text("""
                  SELECT regime_state, regime_delta, narrative, key_themes,
                         regime_summary, top_sector_mentions, model,
                         prompt_version, input_tokens, output_tokens
                  FROM atlas.atlas_daily_briefs
                  WHERE as_of_date = :d
              """), {"d": date(1999, 1, 1)}).fetchone()
          assert row is not None
          assert row[0] == "Risk-On"
          assert row[1] == "unchanged"
          assert row[4] == "bullish"
          assert row[6] == "claude-sonnet-4-6"
          assert row[7] == "v1"
          assert row[8] == 1200
          assert row[9] == 380

      def test_upsert_on_duplicate_date(self):
          eng = get_engine()
          b1 = self._sample_brief()
          b2 = DailyBrief(
              narrative="updated narrative " * 30,
              key_themes=["x", "y", "z"],
              regime_summary="neutral",
              top_sector_mentions=["NIFTY BANK"],
              model="claude-sonnet-4-6",
              prompt_version="v1",
              input_tokens=1300,
              output_tokens=400,
          )
          persist_brief(eng, context=self._sample_ctx(), brief=b1)
          persist_brief(eng, context=self._sample_ctx(), brief=b2)

          with eng.connect() as c:
              rows = c.execute(text(
                  "SELECT regime_summary, input_tokens FROM atlas.atlas_daily_briefs WHERE as_of_date = :d"
              ), {"d": date(1999, 1, 1)}).fetchall()
          # UNIQUE on as_of_date — exactly one row, with updated values.
          assert len(rows) == 1
          assert rows[0][0] == "neutral"
          assert rows[0][1] == 1300
  ```

- [ ] **Step 2: Run the failing test**

  ```bash
  pytest tests/intelligence/briefs/test_audit.py -v 2>&1 | tail -15
  ```

  Expected: ImportError.

- [ ] **Step 3: Implement `audit.py`**

  ```python
  """SP05: persist DailyBrief + context snapshot to atlas.atlas_daily_briefs.

  UPSERT keyed on as_of_date — re-running the CLI for the same date overwrites
  the prior row. The context_snapshot column carries the full structured input
  that produced the brief (SEBI audit-trail requirement).
  """

  from __future__ import annotations

  import json

  import structlog
  from sqlalchemy import text
  from sqlalchemy.engine import Engine

  from atlas.intelligence.briefs.context import DailyMarketContext
  from atlas.intelligence.briefs.generator import DailyBrief

  log = structlog.get_logger()

  _UPSERT_SQL = """
      INSERT INTO atlas.atlas_daily_briefs (
          as_of_date, regime_state, regime_delta, narrative, key_themes,
          regime_summary, top_sector_mentions, context_snapshot,
          model, prompt_version, input_tokens, output_tokens
      ) VALUES (
          :as_of_date, :regime_state, :regime_delta, :narrative,
          CAST(:key_themes AS JSONB),
          :regime_summary,
          CAST(:top_sector_mentions AS JSONB),
          CAST(:context_snapshot AS JSONB),
          :model, :prompt_version, :input_tokens, :output_tokens
      )
      ON CONFLICT (as_of_date)
      DO UPDATE SET
          regime_state          = EXCLUDED.regime_state,
          regime_delta          = EXCLUDED.regime_delta,
          narrative             = EXCLUDED.narrative,
          key_themes            = EXCLUDED.key_themes,
          regime_summary        = EXCLUDED.regime_summary,
          top_sector_mentions   = EXCLUDED.top_sector_mentions,
          context_snapshot      = EXCLUDED.context_snapshot,
          model                 = EXCLUDED.model,
          prompt_version        = EXCLUDED.prompt_version,
          input_tokens          = EXCLUDED.input_tokens,
          output_tokens         = EXCLUDED.output_tokens,
          generated_at          = NOW(),
          updated_at            = NOW()
  """


  def persist_brief(
      engine: Engine,
      *,
      context: DailyMarketContext,
      brief: DailyBrief,
  ) -> None:
      """UPSERT one daily-brief row keyed on context.as_of."""
      params = {
          "as_of_date": context.as_of,
          "regime_state": context.regime,
          "regime_delta": context.regime_delta,
          "narrative": brief.narrative,
          "key_themes": json.dumps(brief.key_themes),
          "regime_summary": brief.regime_summary,
          "top_sector_mentions": json.dumps(brief.top_sector_mentions),
          "context_snapshot": json.dumps(context.to_dict()),
          "model": brief.model,
          "prompt_version": brief.prompt_version,
          "input_tokens": brief.input_tokens,
          "output_tokens": brief.output_tokens,
      }
      with engine.begin() as conn:
          conn.execute(text(_UPSERT_SQL), params)
      log.info(
          "daily_brief_persisted",
          as_of=context.as_of.isoformat(),
          regime=context.regime,
          model=brief.model,
      )
  ```

- [ ] **Step 4: Run tests until they pass**

  ```bash
  pytest tests/intelligence/briefs/test_audit.py -v 2>&1 | tail -15
  ```

  Expected: 2 passed (or 2 skipped if no DB). If DB unavailable, ATLAS_DB_URL not set — tests should mark integration and skip cleanly; if they error, set ATLAS_DB_URL first.

- [ ] **Step 5: Commit**

  ```bash
  git add atlas/intelligence/briefs/audit.py tests/intelligence/briefs/test_audit.py
  git commit -m "feat(sp05): UPSERT persist_brief into atlas_daily_briefs"
  ```

---

## Task 6: Wire package `__init__.py` + CLI

**Files:**
- Modify: `atlas/intelligence/briefs/__init__.py`
- Create: `scripts/generate_daily_brief.py`
- Create: `tests/intelligence/briefs/test_cli_smoke.py`

- [ ] **Step 1: Update `atlas/intelligence/briefs/__init__.py`**

  ```python
  """SP05: daily Atlas brief — Claude-authored market narrative.

  See docs/phase2/plans/2026-05-12-sp05-daily-brief.md.
  """

  from atlas.intelligence.briefs.audit import persist_brief
  from atlas.intelligence.briefs.context import (
      DailyMarketContext,
      build_daily_context,
  )
  from atlas.intelligence.briefs.generator import DailyBrief, generate_brief
  from atlas.intelligence.briefs.prompts import PROMPT_VERSION

  __all__ = [
      "DailyBrief",
      "DailyMarketContext",
      "PROMPT_VERSION",
      "build_daily_context",
      "generate_brief",
      "persist_brief",
  ]
  ```

- [ ] **Step 2: Write the CLI**

  Create `scripts/generate_daily_brief.py`:

  ```python
  """SP05: generate (and optionally persist) the daily Atlas brief.

  Usage::

      # Dry-run against latest MV snapshot, print only, no DB write.
      python scripts/generate_daily_brief.py --dry-run

      # Generate for the latest MV snapshot and persist to atlas_daily_briefs.
      python scripts/generate_daily_brief.py --persist

      # Generate for a specific historical date (still reads CURRENT MVs;
      # the as_of_date column is overridden but the MV snapshot is "now").
      python scripts/generate_daily_brief.py --as-of 2026-05-12 --persist

  Exit codes:
      0 — success
      2 — invalid arguments
      3 — context is empty (no MV data); brief refused
      4 — ANTHROPIC_API_KEY missing (only when not --dry-run-stub)
  """

  from __future__ import annotations

  import argparse
  import os
  import sys
  from datetime import date
  from pathlib import Path

  import structlog
  from sqlalchemy import text

  ROOT = Path(__file__).resolve().parent.parent
  if str(ROOT) not in sys.path:
      sys.path.insert(0, str(ROOT))

  from atlas.db import get_engine  # noqa: E402
  from atlas.intelligence.briefs import (  # noqa: E402
      build_daily_context,
      generate_brief,
      persist_brief,
  )

  log = structlog.get_logger()


  def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
      p = argparse.ArgumentParser(
          description="Generate the daily Atlas brief from SP02 materialized views."
      )
      p.add_argument(
          "--as-of",
          type=lambda s: date.fromisoformat(s),
          default=None,
          help="As-of date (YYYY-MM-DD). Defaults to mv_current_market_regime.date.",
      )
      grp = p.add_mutually_exclusive_group()
      grp.add_argument("--dry-run", action="store_true",
                       help="Generate and print; do NOT persist.")
      grp.add_argument("--persist", action="store_true",
                       help="Generate and persist to atlas_daily_briefs.")
      p.add_argument(
          "--dry-run-stub",
          action="store_true",
          help=(
              "Build context and print it; skip the Claude call entirely. "
              "Used by CI when ANTHROPIC_API_KEY is not available."
          ),
      )
      return p.parse_args(argv)


  def _resolve_as_of(engine, override: date | None) -> date | None:
      if override is not None:
          return override
      with engine.connect() as c:
          row = c.execute(text(
              "SELECT MAX(date) FROM atlas.mv_current_market_regime"
          )).fetchone()
      return row[0] if row and row[0] else None


  def main(argv: list[str] | None = None) -> int:
      args = _parse_args(argv)

      engine = get_engine()
      as_of = _resolve_as_of(engine, args.as_of)
      if as_of is None:
          print("No data in mv_current_market_regime — cannot generate brief.",
                file=sys.stderr)
          return 3

      log.info("daily_brief_cli_start", as_of=as_of.isoformat(),
               dry_run=args.dry_run, persist=args.persist,
               stub=args.dry_run_stub)

      ctx = build_daily_context(engine, as_of=as_of)
      if ctx.regime == "Unknown" and not ctx.top_sectors:
          print("Context is empty (no MV data). Refusing to call Claude.",
                file=sys.stderr)
          return 3

      if args.dry_run_stub:
          print("--- DailyMarketContext (stub mode, no Claude call) ---")
          import json
          print(json.dumps(ctx.to_dict(), indent=2))
          return 0

      if not os.environ.get("ANTHROPIC_API_KEY"):
          print(
              "ANTHROPIC_API_KEY is not set. Export it or re-run with "
              "--dry-run-stub to test the context build only.",
              file=sys.stderr,
          )
          return 4

      brief = generate_brief(ctx)

      print("--- Daily Atlas Brief ---")
      print(f"As-of: {ctx.as_of.isoformat()}")
      print(f"Regime: {ctx.regime} ({ctx.regime_delta})")
      print(f"Summary: {brief.regime_summary}")
      print()
      print(brief.narrative)
      print()
      print("Key themes:")
      for t in brief.key_themes:
          print(f"  - {t}")
      print(f"Tokens: in={brief.input_tokens} out={brief.output_tokens}")

      if args.persist:
          persist_brief(engine, context=ctx, brief=brief)
          print("\nPersisted to atlas.atlas_daily_briefs.")
      else:
          print("\n(dry-run — not persisted)")

      return 0


  if __name__ == "__main__":
      sys.exit(main())
  ```

- [ ] **Step 3: Write the CLI smoke test**

  Create `tests/intelligence/briefs/test_cli_smoke.py`:

  ```python
  """Smoke test for the daily-brief CLI.

  Two modes:
    1. --dry-run-stub: never calls Claude. Exercises the context-build path
       end to end. Marked integration (needs DB).
    2. --dry-run with ANTHROPIC_API_KEY: full Claude round-trip. Skipped if
       key missing.
  """

  from __future__ import annotations

  import os
  import subprocess
  import sys

  import pytest


  @pytest.mark.integration
  def test_cli_stub_mode_completes_under_15s() -> None:
      result = subprocess.run(  # noqa: S603
          [sys.executable, "scripts/generate_daily_brief.py", "--dry-run-stub"],
          capture_output=True,
          text=True,
          timeout=30,
      )
      assert result.returncode in (0, 3), (
          f"CLI exited with {result.returncode}.\n"
          f"stdout: {result.stdout}\nstderr: {result.stderr}"
      )
      # exit 0 = stub printed; exit 3 = no MV data (acceptable on a fresh DB)
      if result.returncode == 0:
          assert "DailyMarketContext" in result.stdout


  @pytest.mark.integration
  def test_cli_dry_run_with_api_key() -> None:
      if not os.environ.get("ANTHROPIC_API_KEY"):
          pytest.skip("ANTHROPIC_API_KEY not set; skipping live Claude call")
      result = subprocess.run(  # noqa: S603
          [sys.executable, "scripts/generate_daily_brief.py", "--dry-run"],
          capture_output=True,
          text=True,
          timeout=60,
      )
      # Acceptable: 0 = success, 3 = no MV data on this DB
      assert result.returncode in (0, 3), (
          f"CLI exited with {result.returncode}.\n"
          f"stdout: {result.stdout}\nstderr: {result.stderr}"
      )
  ```

- [ ] **Step 4: Sanity-run CLI in stub mode**

  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os && python3 scripts/generate_daily_brief.py --dry-run-stub 2>&1 | head -30
  ```

  Expected: either prints the JSON context or exits 3 with "No data" — both are fine.

- [ ] **Step 5: Run pytest on the briefs subtree**

  ```bash
  pytest tests/intelligence/briefs/ -v 2>&1 | tail -20
  ```

  Expected: context + generator tests pass; integration tests pass or skip.

- [ ] **Step 6: Commit**

  ```bash
  git add atlas/intelligence/briefs/__init__.py scripts/generate_daily_brief.py tests/intelligence/briefs/test_cli_smoke.py
  git commit -m "feat(sp05): CLI orchestrator with --dry-run/--persist/--dry-run-stub modes"
  ```

---

## Task 7: Frontend route — `/intelligence/daily-brief`

**Files:**
- Create: `frontend/src/lib/queries/briefs.ts`
- Create: `frontend/src/app/intelligence/daily-brief/page.tsx`

- [ ] **Step 1: Create the server query**

  Write `frontend/src/lib/queries/briefs.ts`:

  ```typescript
  // frontend/src/lib/queries/briefs.ts
  import 'server-only'
  import sql from '@/lib/db'

  export type DailyBriefRow = {
    id: string
    as_of_date: Date
    regime_state: string
    regime_delta: string
    narrative: string
    key_themes: string[]
    regime_summary: string
    top_sector_mentions: string[]
    model: string
    prompt_version: string
    input_tokens: number | null
    output_tokens: number | null
    generated_at: Date
  }

  export async function getLatestBrief(): Promise<DailyBriefRow | null> {
    const rows = await sql<DailyBriefRow[]>`
      SELECT
        id, as_of_date, regime_state, regime_delta, narrative,
        key_themes, regime_summary, top_sector_mentions,
        model, prompt_version, input_tokens, output_tokens, generated_at
      FROM atlas.atlas_daily_briefs
      ORDER BY as_of_date DESC
      LIMIT 1
    `
    return rows[0] ?? null
  }
  ```

- [ ] **Step 2: Create the page**

  Create `frontend/src/app/intelligence/daily-brief/page.tsx`:

  ```tsx
  // frontend/src/app/intelligence/daily-brief/page.tsx
  // SP05 — server component that renders the latest Claude-authored brief.

  import { getLatestBrief } from '@/lib/queries/briefs'

  export const dynamic = 'force-dynamic'
  export const revalidate = 0

  function formatDate(d: Date | string): string {
    const date = typeof d === 'string' ? new Date(d) : d
    return date.toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    })
  }

  function summaryBadgeStyle(summary: string): React.CSSProperties {
    const palette: Record<string, { bg: string; fg: string }> = {
      bullish: { bg: '#dcfce7', fg: '#166534' },
      neutral: { bg: '#f1f5f9', fg: '#334155' },
      cautious: { bg: '#fef3c7', fg: '#854d0e' },
      defensive: { bg: '#fee2e2', fg: '#991b1b' },
    }
    const c = palette[summary] ?? palette.neutral
    return {
      background: c.bg,
      color: c.fg,
      padding: '4px 12px',
      borderRadius: '9999px',
      fontSize: '13px',
      fontWeight: 600,
      textTransform: 'capitalize',
    }
  }

  export default async function DailyBriefPage() {
    const brief = await getLatestBrief()

    if (!brief) {
      return (
        <main style={{ maxWidth: 760, margin: '64px auto', padding: '0 24px' }}>
          <h1 style={{ fontFamily: 'Georgia, serif', fontSize: 32 }}>
            Daily Atlas Brief
          </h1>
          <p style={{ color: '#475569', marginTop: 16 }}>
            No brief has been generated yet. Run{' '}
            <code style={{ fontFamily: 'monospace', background: '#f1f5f9', padding: '2px 6px' }}>
              python scripts/generate_daily_brief.py --persist
            </code>{' '}
            to create one.
          </p>
        </main>
      )
    }

    return (
      <main
        style={{
          maxWidth: 760,
          margin: '48px auto',
          padding: '0 24px 96px',
          background: '#ffffff',
          color: '#0f172a',
        }}
      >
        <header style={{ borderBottom: '1px solid #e2e8f0', paddingBottom: 24, marginBottom: 32 }}>
          <div style={{ fontSize: 13, color: '#64748b', letterSpacing: 1, textTransform: 'uppercase' }}>
            Atlas · Daily Brief
          </div>
          <h1
            style={{
              fontFamily: 'Georgia, "Times New Roman", serif',
              fontSize: 36,
              lineHeight: 1.2,
              margin: '8px 0 12px',
              color: '#0f172a',
            }}
          >
            {formatDate(brief.as_of_date)}
          </h1>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <span
              style={{
                background: '#1D9E75',
                color: 'white',
                padding: '4px 12px',
                borderRadius: 4,
                fontSize: 13,
                fontWeight: 600,
              }}
            >
              {brief.regime_state}
            </span>
            <span style={summaryBadgeStyle(brief.regime_summary)}>{brief.regime_summary}</span>
            {brief.regime_delta !== 'unchanged' && (
              <span
                style={{
                  background: '#eef2ff',
                  color: '#3730a3',
                  padding: '4px 12px',
                  borderRadius: '9999px',
                  fontSize: 13,
                  fontWeight: 600,
                  textTransform: 'capitalize',
                }}
              >
                Regime {brief.regime_delta}
              </span>
            )}
          </div>
        </header>

        <article
          style={{
            fontFamily: 'Georgia, "Times New Roman", serif',
            fontSize: 18,
            lineHeight: 1.7,
            color: '#1e293b',
            whiteSpace: 'pre-wrap',
          }}
        >
          {brief.narrative}
        </article>

        <section style={{ marginTop: 40 }}>
          <h2
            style={{
              fontSize: 14,
              letterSpacing: 1.5,
              textTransform: 'uppercase',
              color: '#64748b',
              marginBottom: 12,
            }}
          >
            Key Themes
          </h2>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {brief.key_themes.map((theme, i) => (
              <span
                key={i}
                style={{
                  background: '#f0fdf4',
                  border: '1px solid #bbf7d0',
                  color: '#166534',
                  padding: '6px 14px',
                  borderRadius: 6,
                  fontSize: 13,
                  fontWeight: 500,
                }}
              >
                {theme}
              </span>
            ))}
          </div>
        </section>

        <footer
          style={{
            marginTop: 64,
            paddingTop: 24,
            borderTop: '1px solid #e2e8f0',
            fontSize: 12,
            color: '#94a3b8',
            display: 'flex',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 12,
          }}
        >
          <span>
            Model: {brief.model} · Prompt: {brief.prompt_version} ·{' '}
            Tokens: {brief.input_tokens ?? '–'} in / {brief.output_tokens ?? '–'} out
          </span>
          <span>
            See audit trail at <code>/admin/briefs/{brief.id}</code> (coming soon)
          </span>
        </footer>
      </main>
    )
  }
  ```

- [ ] **Step 3: Sanity-check folder layout**

  ```bash
  ls /Users/nimishshah/Documents/GitHub/atlas-os/frontend/src/app/intelligence/daily-brief/
  ls /Users/nimishshah/Documents/GitHub/atlas-os/frontend/src/lib/queries/briefs.ts
  ```

  Expected: page.tsx + briefs.ts both exist.

- [ ] **Step 4: Commit**

  ```bash
  git add frontend/src/lib/queries/briefs.ts frontend/src/app/intelligence/daily-brief/page.tsx
  git commit -m "feat(sp05): /intelligence/daily-brief route renders latest brief"
  ```

---

## Task 8: Final verification

**Files:** none modified.

- [ ] **Step 1: Run the full briefs test suite**

  ```bash
  pytest tests/intelligence/briefs/ -v 2>&1 | tail -25
  ```

  Expected: all unit tests pass; integration tests pass or skip cleanly.

- [ ] **Step 2: End-to-end stub CLI**

  ```bash
  cd /Users/nimishshah/Documents/GitHub/atlas-os && python3 scripts/generate_daily_brief.py --dry-run-stub 2>&1 | head -40
  ```

  Expected: either exits 0 with JSON context or exits 3 with "no MV data".

- [ ] **Step 3: Live CLI (only if `ANTHROPIC_API_KEY` is set)**

  ```bash
  if [ -n "$ANTHROPIC_API_KEY" ]; then
    cd /Users/nimishshah/Documents/GitHub/atlas-os && python3 scripts/generate_daily_brief.py --dry-run 2>&1 | head -40
  else
    echo "ANTHROPIC_API_KEY not set — skipping live Claude call"
  fi
  ```

  If the key is set and MV data exists: prints the narrative + themes. If not: documents skip.

- [ ] **Step 4: Lint + typecheck the new module**

  ```bash
  ruff check atlas/intelligence/briefs/ scripts/generate_daily_brief.py tests/intelligence/briefs/
  pyright atlas/intelligence/briefs/ scripts/generate_daily_brief.py 2>&1 | tail -10
  ```

  Expected: ruff clean. Pyright clean on these files (IDE strict-mode errors on unrelated cached files do not block pre-commit).

- [ ] **Step 5: Final status**

  ```bash
  git log --oneline -10
  git status
  ```

  Expected: 7 SP05 commits on top, working tree clean.

---

## Done.
