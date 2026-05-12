# Validator Phase C — Route Crawler & Frontend-Backend Diff

> **Required review gates per CLAUDE.md:** `/plan-eng-review` + `/plan-design-review` (data-lineage tag UX) before execution. `/review` + `/qa` after.

**Goal:** A nightly + on-demand crawler that walks every Atlas frontend route, extracts every numeric value rendered on each page, and diffs it against the SQL source-of-truth. Any mismatch beyond tolerance becomes a P0/P1 finding in `atlas_validator_findings`.

**Tech stack (per research agent recommendation):**
- **Crawlee for Python** + **Pydoll** engine (Chromium without WebDriver — lighter than Playwright, satisfies the "no Playwright" constraint)
- **Firecrawl** self-hosted Docker as optional LLM-extraction sidecar for natural-language probes
- Atlas existing `atlas.agents.validator` package (Phases A+B already shipped) extended with `route_crawler` sub-module

**Out-of-scope:** Phase D Calc Verifier (re-implements numeric primitives), Phase E Orchestrator + admin UI, Phase F hardening — each is its own plan.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ scripts/crawl_frontend.py  (nightly CLI)                │
└────────────────────┬────────────────────────────────────┘
                     │
              ┌──────▼─────────────────────────┐
              │ atlas/agents/validator/        │
              │   route_crawler/               │
              │     ├── crawl.py     ← Crawlee │
              │     ├── extract.py   ← parse   │
              │     │                  values  │
              │     ├── diff.py      ← compare │
              │     │                  vs SQL  │
              │     └── tolerances.yaml        │
              └──────┬─────────────────────────┘
                     │
                     ▼
        ┌────────────────────────────┐
        │ atlas.atlas_validator_     │
        │ findings (existing table)  │
        └────────────────────────────┘
```

Data flow:
1. Crawlee with `SessionPool` logs into `/login` with `ATLAS_PASSWORD`, captures session cookie
2. Crawler enqueues routes from a `coverage_map.yaml` (already partial coverage from Phase B)
3. For each route: wait for `[data-validator-id]` selector to hydrate, then `eval_on_selector_all` to extract `{id, text}` tuples
4. `extract.py` parses each text → typed Decimal (handles ₹, %, +/-, indian-grouping)
5. `diff.py` looks up the expected value via a deterministic SQL given the `data-validator-id` (e.g. `data-validator-id="stock.PFOCUS.conviction"` → `SELECT conviction_score FROM mv_top_conviction_daily WHERE symbol='PFOCUS'`)
6. If `|frontend - backend| > tolerance` → write a `atlas_validator_findings` row with class=`accuracy_error`, severity=P1, finding payload including both values

---

## File Structure

**Backend (new):**
- `atlas/agents/validator/route_crawler/__init__.py`
- `atlas/agents/validator/route_crawler/crawl.py` — Crawlee + Pydoll, session pool, login flow
- `atlas/agents/validator/route_crawler/extract.py` — DOM → typed Decimal parser
- `atlas/agents/validator/route_crawler/diff.py` — frontend value vs SQL truth, tolerance-aware
- `atlas/agents/validator/route_crawler/sql_lookup.py` — `data-validator-id → SQL` mapping table (whitelist)
- `atlas/agents/validator/route_crawler/tolerances.yaml` — per-field tolerance (basis points for percentages, ₹0.01 for money, etc.)
- `scripts/crawl_frontend.py` — nightly CLI

**Backend (modify):**
- `atlas/agents/validator/coverage_map.yaml` — add `frontend_routes` section
- `atlas/agents/validator/persistence.py` — accept new finding_class `frontend_diff`

**Frontend (instrumentation — one-time):**
Add `data-validator-id` attributes to every numeric React element. Mechanical pass via codemod:
- `frontend/src/components/stocks/StockScreener.tsx` — each `<td>` rendering a Decimal
- `frontend/src/components/stocks/ConvictionCell.tsx` — score, backing_ic
- `frontend/src/components/stocks/ConvictionBreakdownPanel.tsx` — each signal's contribution
- `frontend/src/components/intelligence/TopConvictionSection.tsx`
- `frontend/src/components/admin/RealizedICSparkline.tsx`
- `frontend/src/components/sectors/*`
- `frontend/src/components/etfs/*`
- `frontend/src/components/funds/*`

Convention: `data-validator-id="<entity>.<key>.<field>"`, e.g. `data-validator-id="stock.PFOCUS.conviction_score"`, `data-validator-id="sector.IT.rs_velocity"`.

**Tests (new):**
- `tests/agents/validator/route_crawler/test_extract.py` — Decimal parsing (₹1,23,45,678 → Decimal('12345678.00'))
- `tests/agents/validator/route_crawler/test_diff.py` — tolerance bands, edge cases
- `tests/agents/validator/route_crawler/test_sql_lookup.py` — whitelist enforcement
- `tests/agents/validator/route_crawler/test_crawl_smoke.py` — full crawl against a local Next.js dev instance (CI-friendly; skips in prod-only test runs)

---

## Tasks (sequenced)

### Task 0: Pre-flight
- Verify `atlas.atlas_validator_findings` schema supports new finding_class
- Verify `ATLAS_PASSWORD` is reachable on the EC2 host (it powers the /login page)

### Task 1: Add Crawlee + Pydoll to dependencies
```
uv add crawlee[pydoll]
```
Test import + headless launch on EC2 t3.large. Memory footprint must stay under 1 GB during a crawl.

### Task 2: Frontend instrumentation — codemod for `data-validator-id`
Single PR that mechanically adds the attribute to every Decimal/percentage element. Convention from the design review. Aim for 80% coverage on first pass — Stage 4d can fill the rest.

### Task 3: `crawl.py` — login + route enqueue + extraction
- `SessionPool(max_pool_size=1, max_session_rotations=0)` — preserve auth cookie
- `PydollCrawler` (Chromium without WebDriver)
- Login flow as a special-case handler for `/login`
- After login, enqueue routes from `coverage_map.yaml.frontend_routes`
- For each: `await ctx.page.wait_for_selector("[data-validator-id]")` then extract

### Task 4: `extract.py` — typed parser
- Handle `₹1,23,45,678.50` → `Decimal("12345678.50")`
- Handle `+45.2%` → `Decimal("0.452")`
- Handle `+0.0511` / `−0.0325` (signed decimals)
- Handle em-dash `—` → None
- Strict mode: unparseable → finding (`extract_error`, P2)

### Task 5: `sql_lookup.py` — whitelist mapping
```python
LOOKUPS: dict[str, Callable[[str], str]] = {
    "stock.<symbol>.conviction_score": lambda s: (
        f"SELECT conviction_score FROM atlas.mv_top_conviction_daily "
        f"INNER JOIN atlas.atlas_universe_stocks u USING(instrument_id) "
        f"WHERE u.symbol = '{escape(s)}'"
    ),
    ...
}
```
Closed-set, no user-input concatenation. Atlas database role is `atlas_validator_readonly` (created in Phase A).

### Task 6: `diff.py` — tolerance-aware comparison
- Load `tolerances.yaml`: `{conviction_score: 1e-4, percentage: 1e-3, money_inr: 0.01, integer: 0}`
- For each (id, frontend_value, backend_value): compute diff, classify severity
- P0: > 10× tolerance or sign flip
- P1: > tolerance
- P2: between 0.5× and 1× tolerance (drift watch)
- P3: noise level, audit only

### Task 7: `scripts/crawl_frontend.py` CLI
```
python scripts/crawl_frontend.py [--routes stocks,intelligence] [--persist]
```
Default crawls all routes in `coverage_map.yaml.frontend_routes`. `--persist` writes findings.

### Task 8: Nightly orchestration wire-in
Add to `scripts/run_atlas_intelligence_nightly.sh` after the existing validator A+B chain:
```
run_step "validator_frontend_crawl"  python scripts/crawl_frontend.py --persist
```

### Task 9: Memory file + master plan badge
- `~/.claude/projects/.../memory/project_validator_phase_c_state.md`
- Update `00-master-plan.html` validator badge to "✓ A+B+C Shipped"
- Update `01-data-validator-agent.html` Phase C pill from "⏸ Not started" to "✓ Shipped"

---

## Eng review notes (inline)

- **Auth**: cookie-based, Atlas's existing `/login` flow with `ATLAS_PASSWORD`. No new auth surface. Bonus: the crawler's session is identical to an FM browser session, so any auth regression breaks the crawl loudly.
- **Tolerance bands** must come from a versioned YAML, not hardcoded — same pattern as `atlas_thresholds` for SQL but yaml here since these are frontend-rendering concerns.
- **Crawl frequency**: nightly + on-demand. Mid-day crawl (Phase F) gated on real value being seen.
- **SQL injection**: every lookup uses the closed `LOOKUPS` dict with `escape()` on the entity key. No free-form query construction.
- **t3.large fit**: Pydoll uses 1 chromium process (~200-300 MB resident). Crawlee adds ~50 MB. Well under the 8 GB limit even running alongside the FastAPI + Atlas nightly pipelines.

## Design review notes (inline)

- `data-validator-id` attributes are **invisible to users** — pure DOM metadata. No UX impact.
- Convention enforces predictability: every numeric element follows `<entity>.<key>.<field>`, every entity has a deterministic SQL lookup. Reviewers can verify coverage in 60 seconds.
- Findings flow into the existing `atlas_validator_findings` schema with no new table — Phase E admin UI (when built) renders them via the same surface as Phases A+B.

---

## Effort estimate

| Block | Effort |
|---|---|
| Tasks 1-3 (deps + frontend instrumentation + crawler core) | 2-3 hours |
| Tasks 4-6 (extract + lookup + diff with tolerances) | 1-2 hours |
| Tasks 7-9 (CLI + orchestration + docs) | 1 hour |
| **Total** | **4-6 hours** |

Realistic for one focused session. Frontend instrumentation is the longest tail — could ship Phase C without 100% coverage and fill in over time.
