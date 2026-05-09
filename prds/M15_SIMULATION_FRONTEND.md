# M15 — Simulation Frontend (Strategies + Custom Portfolios)

**Date:** 2026-05-10
**Status:** Spec — pending your approval (do not build until confirmed)
**Goal:** Surface the simulation backend (M7 — strategies, backtest, paper trading, custom portfolios) to the FM through a coherent web frontend. Two product surfaces ship: (1) a read-only dashboard for the 15 systematic strategies, (2) a custom portfolio builder with two flavors — Static (pick instruments + weights) and Rule-Based (define entry/exit rules including market breadth triggers).

---

## What ships

### Routes (8 new pages)
```
/strategies                  Systematic strategies dashboard (15 cards)
/strategies/[id]             Strategy detail (single long page)
/portfolios                  FM custom portfolios list
/portfolios/new              Builder (tabs: Static | Rule-Based)
/portfolios/[id]             Custom portfolio detail
```

### Backend extensions
- `atlas/simulation/custom/builder.py` — multi-asset universe validation (currently stocks-only)
- `atlas/simulation/custom/portfolio.py` — multi-asset price fetcher (de_etf_ohlcv, de_fund_nav_daily)
- `atlas/api/strategies.py` (NEW) — POST `/api/strategies/{id}/backtest` (re-run with date range + capital)
- `atlas/api/portfolios.py` (EXTENDED) — POST `/api/portfolios/rule-based` (FM-authored rule-based portfolios)
- `atlas/simulation/strategies/runner.py` — recognize `is_fm_authored=TRUE` configs for paper trading
- `atlas/simulation/backtest/engine.py` — accept multi-asset price series for static portfolios
- Migration 025 — `strategy_configs.is_fm_authored BOOLEAN DEFAULT FALSE` column

### What does NOT change
- Methodology lock, M13 thresholds, M14 decision policies — untouched.
- The 15 systematic `strategy_configs` rows — untouched (read-only on this UI).
- Paper trader for systematic strategies — same nightly job as today; just learns to handle `is_fm_authored=TRUE` rows.

---

## Architecture decisions (locked through your D1-D15 answers)

| # | Decision | Why |
|---|---|---|
| D1 | Strategies dashboard is the anchor (foundation) | Most-viewed surface; all other features link here |
| D2 | Scope = systematic strategies + backtest browser + custom portfolios; defer paper-trading dashboard + overlap heatmap to M16 | Tight scope discipline |
| D3 | Read-only systematic strategies + write surface for custom portfolios + Re-run Backtest button on systematic | FM views, doesn't author systematic; FM creates custom |
| D4 | Multi-asset picker (Stocks + ETFs + MFs) with type tab + state + sector + size + functional filters | FM intent stated explicitly |
| D5 | Custom portfolio weights = equal-weight default + custom % override | Simple UX; FM stays in control |
| D6 | Single long page per `/strategies/[id]` (no tabs) | Mirrors `/sectors/[name]`; least UI friction |
| D7 | Re-run backtest = modal with date-range + initial-capital input | Lets FM run "how would this have done in 2020 specifically?" |
| D8 | API approach = hybrid: postgres.js for reads + FastAPI for writes/long-ops | Matches existing pattern; minimum new boilerplate |
| D9 | Implementation approach = foundation-first vertical slice | DRY on visualization across 3+ pages; phase 2+ is ~40% cheaper |
| D10 | Mode = HOLD SCOPE (no expansion creep) | Locked scope is large; rigor over expansion |
| D11 | Multi-asset extension within M15 (not deferred) | FM said portfolios mix all 3 asset types |
| D12 | Single PR, autonomous build like M14 | Matches successful M13/M14 pattern |
| D13 | Both Static + Rule-Based portfolio builders ship in M15 | FM's market-breadth-triggers question made rule-based load-bearing |
| D14 | Rule expressivity = constrained form matching `strategy_configs` shape + market breadth gates | Reuses existing schema; no new rule engine |
| D15 | Paper trading enabled for FM-authored rule-based portfolios in M15 | Without paper trading, FM has no way to monitor authored rules |

### Auto-decided (not asked because the answer was forced by D-decisions)

| # | Decision | Forced by |
|---|---|---|
| AD1 | FM-authored rule-based portfolios live in `strategy_configs` with new `is_fm_authored=TRUE` flag | D14 (constrained form) → reuses systematic-strategy schema |
| AD2 | Static custom portfolios continue in `strategy_fm_custom_portfolios` (unchanged) | D13 (both flavors) — keeps two shapes cleanly separated |
| AD3 | Paper trading for static portfolios = simple monthly rebalance to target weights | D15 + scope minimalism |
| AD4 | Backtest re-run concurrency = 409 if a backtest for same strategy+date_range is in-flight | M13 pattern (atlas_pipeline_runs soft check) |
| AD5 | Auth = existing site cookie gate | M13/M14 pattern |
| AD6 | All new pages live under existing top nav (add 2 entries: Strategies, Portfolios) | Matches M14's nav additions |
| AD7 | Tab default on `/portfolios/new` = Static flavor | Most discoverable; Rule-Based requires more thought |

---

## Sitemap with content per page

### `/strategies`
**Server-rendered list of 15 systematic strategies.**
- Top KPI band: average Sharpe, count by tier, count paper-active
- Filters: tier (Aggressive / Moderate / Passive), archetype (momentum_blend / sector_rotation / etc.), paper-active toggle
- Table:
  | Name | Archetype | Tier | Sharpe (latest BT) | Alpha vs N500 | Paper Active | Last Updated |
- Click row → `/strategies/[id]`

### `/strategies/[id]`
**Single long page, scroll sections.** All systematic strategies (read-only config).
1. **Header** — name + tier badge + archetype + paper-active dot
2. **KPI cards** — Sharpe, max drawdown, alpha vs N500, alpha vs naive Atlas baseline, walk-forward OOS Sharpe
3. **Action bar** — "Re-run Backtest" button → modal (start_date / end_date / initial_capital) — calls `POST /api/strategies/{id}/backtest`
4. **Equity curve** — paper performance line + latest backtest line + Nifty500 benchmark (Recharts LineChart)
5. **Drawdown chart** — Recharts AreaChart, peak-to-trough %
6. **Regime breakdown** — stacked bar showing alpha contribution per regime (Risk-On / Constructive / Cautious / Risk-Off)
7. **Backtest history table** — all rows in `strategy_backtest_results` for this strategy_id, sortable by created_at, click row for detail
8. **Recent paper trades** (only if `paper_trading_active=TRUE`) — latest 20 trades from `strategy_paper_trades`
9. **Config viewer** — read-only JSON of `strategy_configs.config`, with friendly labels (e.g., `state_filter: ["Leader","Strong"]` rendered as a checkbox group)

### `/portfolios`
**FM custom portfolios list.** Mixes Static (existing `strategy_fm_custom_portfolios`) + Rule-Based (`strategy_configs WHERE is_fm_authored=TRUE`).
- Top KPI band: count by type, count paper-active
- Action: "+ New Portfolio" → `/portfolios/new`
- Table:
  | Name | Type (Static / Rule-Based) | Composition (instrument count or rule summary) | Latest Sharpe | Paper Active | Created |

### `/portfolios/new`
**Tabs: `Static` | `Rule-Based`** (URL: `/portfolios/new?type=static` or `?type=rule-based`).

#### Static tab (Flavor A)
```
Step 1: Name your portfolio
Step 2: Pick instruments
  ├─ Tabs: Stocks | ETFs | Mutual Funds
  ├─ Filters per type:
  │    Stocks: sector, tier (Large/Mid/Small/Micro), rs_state, is_investable, search
  │    ETFs: theme (Broad/Sectoral/Thematic), linked_sector, search
  │    MFs: category (Large Cap, Mid Cap, etc.), search
  └─ Click row → adds to selection panel (right side, sticky)
Step 3: Set weights
  ├─ Equal-weight default (computed on add)
  ├─ Custom % per row, "Sums to X%" indicator
  └─ Auto-Normalize button
Step 4: Submit
  └─ "Create + Backtest" button → POST /api/portfolios/custom (existing API)
     → polling on backtest status → redirect to /portfolios/[id]
```

#### Rule-Based tab (Flavor B)
```
Step 1: Name + brief description
Step 2: Universe definition (which instruments are eligible)
  ├─ Asset class toggle: ☑ Stocks ☑ ETFs ☐ MFs
  ├─ Stock filters: tier, sector, baseline RS state floor (e.g., must be ≥ Average)
Step 3: Entry rules — when to BUY
  ├─ Card: "Stock state filter" — multi-select rs_state ∈ [Leader, Strong, Emerging, Consolidating]
  ├─ Card: "Momentum filter" — multi-select momentum_state
  ├─ Card: "Risk filter" — multi-select risk_state
  ├─ Card: "Volume filter" — multi-select volume_state
  ├─ Card: "Sector filter" — multi-select sector_state
  ├─ Card: "Regime gate" — multi-select regime_state
  └─ Card: "Market breadth gate" (NEW vocabulary — your D-question)
       ├─ pct_above_ema_50 ≥ X (slider 0-100)
       ├─ ad_ratio ≥ X (slider 0-3)
       ├─ new_high_low_ratio ≥ X (slider 0-5)
       ├─ pct_in_strong_states ≥ X (slider 0-1)
       └─ Each independently optional (toggle to enable)
Step 4: Exit rules — when to SELL
  ├─ Same vocabulary as entry, with NEGATED meaning
  ├─ Plus: drawdown_per_position > X% (per-name stop loss, slider)
  └─ Plus: holding_period_max (days, slider, default 0 = none)
Step 5: Position sizing
  ├─ position_sizing: equal_weight | vol_target | market_cap (radio)
  ├─ max_positions: slider 5-50
  └─ max_sector_pct: slider 10-50
Step 6: Rebalance trigger
  └─ rebalance_trigger: signal_change | weekly | monthly (radio)
Step 7: Submit
  └─ "Create + Backtest" → POST /api/portfolios/rule-based
     → server validates rule shape against schema
     → INSERT into strategy_configs with is_fm_authored=TRUE
     → kicks off backtest via runner.py
     → polling, redirect to /portfolios/[id]
```

### `/portfolios/[id]`
- Header: name + Type badge (Static / Rule-Based) + paper-active dot
- KPI cards: Sharpe, drawdown, alpha vs N500
- Composition view:
  - Static → instrument table with weights
  - Rule-Based → narrative ("Holds stocks where rs_state ∈ {Leader, Strong} AND regime ∈ {Risk-On, Constructive} AND pct_above_ema_50 ≥ 60") + current holdings derived from rules (today's snapshot from paper trader)
- Equity curve + drawdown
- Backtest history table
- Toggle: **Activate Paper Trading** (writes `paper_trading_active=TRUE` on the source row)
- Action: "Re-run Backtest" → same modal as systematic

---

## Component foundation (Phase 1)

Built once in Phase 1, reused across `/strategies/[id]` + `/portfolios/[id]` + future M16 paper-trading dashboard.

```
frontend/src/components/charts/
  EquityCurveChart.tsx       Recharts LineChart with benchmark overlay
  DrawdownChart.tsx          Recharts AreaChart inverted
  RegimeBreakdownChart.tsx   Stacked bar
  KPICard.tsx                Reusable Sharpe/Drawdown/Alpha tile
frontend/src/components/portfolio/
  InstrumentPicker.tsx       Multi-asset picker with filters (used in Static + Rule-Based universe step)
  WeightTable.tsx            Editable %, sum indicator, normalize button
frontend/src/components/strategy/
  RuleCard.tsx               One per state filter / breadth gate
  RuleBuilderForm.tsx        Composes 6 RuleCards into a complete strategy_config payload
  ConfigJSONViewer.tsx       Friendly labels for strategy config JSON
  BacktestSummaryCard.tsx    KPI band + last-run timestamp + re-run button
  BacktestHistoryTable.tsx   Sortable table
  ReRunBacktestModal.tsx     Date range + initial capital + submit
frontend/src/lib/queries/
  strategies.ts              SELECT helpers
  portfolios.ts              SELECT helpers
  backtests.ts               SELECT helpers
  paper_perf.ts              SELECT helpers
frontend/src/lib/api/
  internal.ts                fetch wrappers for new FastAPI endpoints
```

---

## Backend extensions

### Migration 025
```sql
ALTER TABLE atlas.strategy_configs
  ADD COLUMN is_fm_authored BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN created_by VARCHAR(64);

CREATE INDEX idx_strategy_configs_fm_authored
  ON atlas.strategy_configs (is_fm_authored, created_at DESC)
  WHERE is_fm_authored = TRUE;
```
Adds an audit trigger parallel to M13 (UPDATE → atlas.atlas_strategy_history) — same `current_setting('atlas.change_reason', true)` GUC pattern.

### `atlas/api/strategies.py` (NEW)
- `POST /api/strategies/{id}/backtest`
  - Body: `{start_date, end_date, initial_capital}`
  - 409 if same strategy has an in-flight backtest
  - Spawns backtest run via `runner.py` (subprocess + atlas_pipeline_runs entry)
  - Returns `{compute_run_id, status: 'running'}`

### `atlas/api/portfolios.py` (EXTENDED)
- Existing endpoints unchanged (used by Static flavor).
- `POST /api/portfolios/rule-based` (NEW)
  - Body: `{name, description, config (matching strategy_configs.config schema), universe_filter}`
  - Server validates config against allowlist of state values + breadth field names
  - INSERT into `strategy_configs` with `is_fm_authored=TRUE`, `created_by='fund-manager'`
  - Triggers initial backtest
  - Returns `{strategy_id, compute_run_id}`
- `PATCH /api/portfolios/{id}/paper-trading` — toggle paper_trading_active

### `atlas/simulation/custom/builder.py` (EXTENDED)
- `_validate_universe_membership` learns to handle `instrument_type='etf'` (queries `atlas_universe_etfs` by ticker) and `'fund'` (queries `atlas_universe_funds` by mstar_id).

### `atlas/simulation/custom/portfolio.py` (EXTENDED)
- Price fetcher branches by `instrument_type`:
  - `stock` → `de_ohlcv_daily.adj_close`
  - `etf` → `de_etf_ohlcv.close` (verify column name)
  - `fund` → `de_fund_nav_daily.nav`

### `atlas/simulation/strategies/runner.py` (EXTENDED)
- Loads BOTH `is_fm_authored=FALSE` (systematic, daily cron) AND `is_fm_authored=TRUE` (FM-authored, only when `paper_trading_active=TRUE` on the corresponding portfolio row).

### Concurrency
- Re-run backtest endpoint guards against duplicate via `atlas_pipeline_runs WHERE script_name='backtest' AND status='running' AND started_at > NOW() - INTERVAL '30 minutes'`.

### Logfile capture
- All new long-running compute (backtest, rule-based portfolio create) writes stdout/stderr to `/var/log/atlas/backtest-{strategy_id}-{run_id}.log` — same pattern as M13 internal_recompute.

---

## Phase plan (lean — D16 right-size)

6 phases. Estimated **~14-15 hr CC** across **~5-6 wallclock hr** with subagents — same shape as M13 (6 hr) and M14 (6 hr).

| # | Phase | Deliverables | Hours CC |
|---|---|---|---|
| 0 | Plan-eng-review | Architecture review on this spec, surface backend schema gaps | 1 |
| 1 | Backend extensions | Migration 025 + multi-asset builder.py validation (3 type branches) + multi-asset price fetcher (3 SQL branches) + 1 new endpoint `POST /api/strategies/{id}/backtest` + 1 new endpoint `POST /api/portfolios/rule-based` + ~12 unit tests | 2-3 |
| 2 | Read-only pages | `/strategies` + `/strategies/[id]` long-scroll page + queries lib + chart components built inline (Recharts is declarative — no foundation phase needed) + tests | 3 |
| 3 | Static portfolio builder | `/portfolios` list + `/portfolios/[id]` detail + `/portfolios/new?type=static` (reuses M14's EditGatePolicyModal checkbox pattern + InstrumentPicker built inline) + tests | 3 |
| 4 | Rule-based portfolio builder | `/portfolios/new?type=rule-based` (RuleBuilderForm copy-pastes M14's GatePoliciesTab card structure + adds 4 breadth-gate sliders) + paper-trading toggle (greyed unless backend extension landed; greyed = OK for v0) + tests | 3 |
| 5 | Re-run backtest UX | Button on `/strategies/[id]` + tiny date-range modal (~80 LOC) + reuses M13's RecomputePanel polling pattern + 1 new test | 1 |
| 6 | Deploy + smoke + ship | Migration on .214 + frontend rebuild on .196 + end-to-end smoke (create static portfolio + rule-based portfolio + re-run a systematic backtest) + PR | 1 |

### Why ~14 hr not ~50 hr (the reuse story)

| What I would have built fresh | What we actually reuse |
|---|---|
| Foundation phase: 5 charts + picker + table built upfront (~8 hr) | Build charts inline as needed (~3 hr); refactor to shared if pain emerges in M16 |
| Re-run modal + new patterns (~4 hr) | M13's RecomputePanel polling is the same pattern with one different button label (~1 hr) |
| Rule builder form from scratch (~6 hr) | M14's GatePoliciesTab + EditGatePolicyModal already implement checkbox groups with diff preview + audit + reason — we copy that file structure (~3 hr) |
| Paper-trader extension for FM-authored rules (~5 hr) | Defer the actual nightly hookup to M16; ship a greyed-out toggle in M15 (~0.5 hr) |
| ~50 tests per M13's bar (~6 hr) | ~25 tests; mostly read-only paths, fewer audit-chain assertions (~3 hr) |
| Custom modals for everything (~4 hr) | Reuse M13/M14's modal scaffolding (role=dialog + Escape + label-input pairs) (~1 hr) |

**Total saved: ~30 hr by reusing M13/M14 patterns.**

---

## Tests

Boil-the-lake — same bar as M13/M14. ~50-60 tests total.

### Backend
- Migration 025 unit + integration tests (parallel to M13/M14 patterns)
- `_validate_universe_membership` for stock + etf + fund
- Price fetcher per asset class (mocked)
- `POST /api/strategies/{id}/backtest` — 401, 400 (bad date range), 409 (in-flight), 202 (happy path)
- `POST /api/portfolios/rule-based` — config validation, state-value allowlist, breadth-field allowlist
- `PATCH /api/portfolios/{id}/paper-trading` — happy path + auth
- `runner.py` reads `is_fm_authored=TRUE` rows when paper-trading is active

### Frontend
- All Server Actions: empty input rejection, validation, sql.begin transaction wrapper (parallel to M14's actions tests)
- InstrumentPicker filters: by sector, tier, state, search
- WeightTable: equal-weight on add, sum-indicator, normalize
- RuleBuilderForm: composes valid `strategy_configs.config` payload from form state
- 3 Playwright E2E (skipped without ATLAS_E2E_BASE_URL):
  1. Login → /strategies → click first → see KPI cards + equity curve
  2. /portfolios/new?type=static → pick 3 stocks + weights → Create → see new entry in /portfolios list
  3. /portfolios/new?type=rule-based → set state_filter + breadth gate → Create → see rule narrative on /portfolios/[id]

---

## Failure modes

| Failure | Test? | Handled? | UX |
|---|---|---|---|
| Backtest takes >5 min (long history) | ✓ | Polling continues; UI shows "Still running…" | Polling pattern |
| Concurrent re-run of same strategy | ✓ | 409 + existing run_id surfaced | Toast: "Already running, run_id=X" |
| Multi-asset price-fetcher: ticker not in `de_etf_ohlcv` | ✓ | builder.py validation rejects pre-DB | Modal inline error |
| Rule-based config rejected by allowlist (FM tries to use unknown breadth field) | ✓ | Server Action validation rejects | Form inline error |
| FM creates rule-based portfolio with empty state_filter | ✓ | Allowed but warned: "No instruments will match" | Yellow banner |
| Paper trading on FM-authored strategy starts but signal_adapter has no historical signals for it | ✓ | runner.py logs and skips that day | Logged; no crash |
| InstrumentPicker rendering 750+100+592 = 1,442 rows | ✓ | Virtualized list (react-window or use the existing pattern) | Smooth scroll |

---

## NOT in scope (deferred, written to TODOS)

- Paper-trading dashboard at `/paper-trading` (D2 deferral)
- Strategy overlap heatmap at `/strategies/overlap` (D2 deferral)
- Optimizer routes `/optimizer` and `/optimizer/[study_id]` (Phase 4 backend not built)
- Side-by-side strategy compare (D10 deferral)
- Save backtest run as named scenario (D10 deferral)
- Export backtest as PDF (D10 deferral)
- Constrained-weight optimization in Static flavor (D5 deferral — no PyPortfolioOpt suggestion button in M15)
- Sector cap / asset-class cap constraints in Static flavor (D5 deferral)
- Live "what-if" simulation overlay (M16+)
- Strategy-versioning (V1 vs V2 performance comparison) — deferred per M7 plan
- Multi-period optimization across regimes simultaneously — deferred per M7 plan
- Threshold A/B testing on live paper portfolios — deferred per M7 plan

---

## Success criteria

1. FM logs in at `/strategies`, sees 15 systematic strategies with KPI band + filters
2. FM clicks one → drills into single-page detail with equity curve + drawdown + regime breakdown + backtests
3. FM clicks Re-run Backtest, sets date range 2022-01-01 to 2024-12-31 with ₹10L capital, submits → polling → results appear
4. FM goes to `/portfolios/new?type=static`, picks 3 stocks + 1 ETF + 1 MF, sets weights, submits → backtest runs → portfolio appears at `/portfolios/[id]`
5. FM goes to `/portfolios/new?type=rule-based`, defines rules including a market-breadth gate (`pct_above_ema_50 ≥ 60`), submits → strategy_configs row created with `is_fm_authored=TRUE` → backtest runs
6. FM toggles paper trading on the rule-based portfolio → next nightly run, paper_trader.py executes the rules → trades + perf snapshots accumulate
7. Public dashboards (`/sectors`, `/stocks`) untouched and unbroken

---

## Plan-eng-review — auto-decisions (2026-05-10)

Per user's standing directive ("make the calls, document the decisions"). All decisions logged here.

### Architecture findings

1. **`de_mf_nav_daily` partition pruning.** Year-partitioned (`_y2006` … `_y2034`). Auto-decide: price-fetcher SQL must include `WHERE nav_date >= :start AND nav_date <= :end` early so Postgres uses partition pruning. Test: query plan check on 5-year backtest touches only the relevant partitions.
2. **`is_fm_authored` BOOLEAN column on `strategy_configs`** (not separate table). Single query path for runner.py + paper_trader; index `(is_fm_authored, created_at DESC) WHERE is_fm_authored=TRUE`.
3. **`/portfolios/[id]` empty state for rule-based** when paper trader hasn't run yet (M16). UI shows "Holdings will appear after first nightly run (M16)" + rule narrative + last-backtest snapshot. Not a defect; documented gap.
4. **Backtest re-run uses `script_name='backtest_engine'`** for the `atlas_pipeline_runs` row + 6-hour soft check. Endpoint inserts row at start of run; soft check filters on `script_name='backtest_engine' AND status='running' AND started_at > NOW() - INTERVAL '30 minutes'`.
5. **Audit trigger on `strategy_configs`** fires on UPDATE when `config IS DISTINCT FROM` OR `is_active IS DISTINCT FROM`. Other column changes (`updated_at`) don't audit.

### Code quality findings

1. **InstrumentPicker filter state resets on tab switch.** Each asset class has its own filter shape (rs_state for stocks, theme for ETFs, category_name for MFs). URL param `?asset=stocks&filter=...` tracks active state for shareable URLs.
2. **`ConfigJSONViewer` renders as tag chips for set-valued fields**, `key: value` for scalar. Read-only — no checkbox widgets. Different shape than M14's GatePoliciesTab (which is editable).
3. **Rule cards copy M14's `GatePoliciesTab` + `EditGatePolicyModal` structure verbatim**, swap data source from `atlas_decision_policy` reads to local form-state. ~3 hr saved.

### Test critical gap (must fix in spec)

**Security validation on `POST /api/portfolios/rule-based`:** the endpoint accepts arbitrary JSON config. Auto-decide: add explicit allowlist module `atlas/api/_rule_allowlist.py`:
```python
ALLOWED_BREADTH_FIELDS = frozenset({
    "pct_above_ema_50", "ad_ratio", "new_high_low_ratio",
    "pct_in_strong_states", "pct_weinstein_pass",
})
ALLOWED_GATE_KEYS = frozenset({
    "rs_state_filter", "momentum_state_filter", "risk_state_filter",
    "volume_state_filter", "sector_state_filter", "regime_state_filter",
})
ALLOWED_SIZING_KEYS = frozenset({"position_sizing", "max_positions", "max_sector_pct"})
ALLOWED_REBALANCE = frozenset({"signal_change", "weekly", "monthly"})
```
The endpoint validates every key in the incoming config against these allowlists; rejects with 400 + structured error envelope. **CRITICAL test** — fails the build if it doesn't pass.

### Performance findings

1. **InstrumentPicker default filter = `is_investable=TRUE today` for stocks tab** (~30-100 names instead of 750). ETF/MF tabs lazy-load on click. Reduces first-paint cost.
2. **Equity curve at 1,250 points = no caching layer needed for v0.** Recharts handles. Revisit if FM tests >5-year backtests on 50-name portfolios.
3. **Multi-asset price load over 5 years** is bounded: 50 instruments × 1,250 days = 62K rows fetched. Acceptable.

### Test plan

Total: ~40 paths in coverage diagram. Test breakdown:
- 9 unit tests for migration 025 trigger (parallel to M13's pattern)
- 6 unit tests for `_validate_universe_membership` (3 type branches × happy + miss)
- 5 unit tests for `_fetch_prices` (3 branches + partition pruning + empty-data)
- 8 unit tests for new endpoints (auth, validation, happy path, 409)
- 1 CRITICAL: rule-config security validation (allowlist enforcement)
- 5 unit tests for `RuleBasedBuilder` form validation (state_filter, breadth gate bounds, payload shape)
- 4 unit tests for `StaticBuilder` (weight sum, normalize, instrument validation)
- 2 unit tests for `ReRunBacktestModal` (date validation, capital min)
- 3 Playwright E2E (skipped without ATLAS_E2E_BASE_URL):
  1. Login → /strategies → click → see equity curve
  2. /portfolios/new?type=static → pick mixed assets → submit → see /portfolios/[id]
  3. /portfolios/new?type=rule-based → set rules + breadth gate → submit → see rule narrative
- ~5 regression tests (auth, /strategies render, etc.)

Total: **~48 tests.** Boil-the-lake bar matched.

### Deployment

Same as M13/M14:
1. Migration 025 on .214 (alembic upgrade head)
2. Frontend rebuild on .196 (npm install + build + pm2 restart)
3. Smoke test: `/strategies` returns 200, `/portfolios/new?type=static` returns 200, FastAPI new endpoints respond
4. PR after smoke passes

### NOT in scope (deferred to M16+)

- Paper-trading dashboard at `/paper-trading`
- Strategy overlap heatmap at `/strategies/overlap`
- Optimizer routes (Phase 4 backend not built)
- Side-by-side strategy compare
- Save backtest run as named scenario
- Export backtest as PDF
- Constrained-weight optimization in Static flavor (no PyPortfolioOpt suggestion button)
- Sector cap / asset-class cap constraints in Static flavor
- Live "what-if" simulation overlay
- Strategy-versioning (V1 vs V2 perf comparison)
- Multi-period optimization across regimes
- Threshold A/B testing on live paper portfolios
- Paper trader recognizing `is_fm_authored=TRUE` for nightly runs (toggle ships greyed-out in M15)

### Worktree parallelization

| Step | Modules | Depends |
|---|---|---|
| 1: Backend extensions (multi-asset + new endpoints + migration 025) | atlas/api/, atlas/simulation/custom/, migrations/ | — |
| 2: Frontend foundation + queries | frontend/src/lib/, frontend/src/components/charts/ | — |
| 3: /strategies pages | frontend/src/app/strategies/ | step 2 (charts) |
| 4: /portfolios pages | frontend/src/app/portfolios/ | step 2 (charts + InstrumentPicker), step 1 (rule-based endpoint) |
| 5: Re-run backtest UX | frontend/src/app/strategies/[id]/, atlas/api/strategies.py | step 1 (endpoint), step 3 (page) |

**Parallel lanes:** Lane A (step 1 backend) and Lane B (step 2 frontend foundation) launch in parallel via subagents. After both merge, steps 3-5 sequential. Saves ~1.5 hr wallclock.

### Engineering completion summary

- Step 0 Scope Challenge: scope accepted as-is (35-file complexity is structural, not invented)
- Architecture Review: 5 issues found, all auto-decided + patched into spec
- Code Quality Review: 3 issues found, all auto-decided + patched
- Test Review: 40-path diagram produced, ~48 tests planned, 1 critical security gap closed via allowlist module
- Performance Review: 3 issues found, all addressed in spec
- Outside voice: skipped (M13/M14 pattern reuse means novel surface is small)
- Parallelization: 2 parallel lanes save ~1.5 hr wallclock
- Lake Score: 11/11 (every choice picked the complete option)

### Unresolved decisions

None. All eng-review questions auto-decided per user's standing directive.

---

## Plan-design-review — auto-decisions (2026-05-10)

App UI rule set (internal FM tool, not marketing). M6/M13/M14 pages are the de facto design system. All findings auto-decided per user directive.

**Initial rating: 6/10 → Final: 9/10**

### Pass 1 — Information Architecture (7→9)
- `/strategies/[id]` adds in-page anchor nav at top (jumps to Equity / Backtests / Paper / Config) — same pattern as `/sectors/[name]`.

### Pass 2 — Interaction State Coverage (4→9)

| Feature | Loading | Empty | Error | Success | Partial |
|---|---|---|---|---|---|
| /strategies table | skeleton 15 rows `animate-pulse` | n/a | retry button | rendered | n/a |
| /strategies/[id] equity curve | skeleton chart | "No backtests yet" + Re-run CTA | "Couldn't load — Retry" | rendered | "Backtest in progress" w/ pulse dot |
| /strategies/[id] paper trades | skeleton rows | "Paper trading not active" + activate hint | inline error | rendered | n/a |
| /portfolios list | skeleton rows | "No portfolios yet" + "+ New Portfolio" CTA | retry | rendered | n/a |
| /portfolios/new picker | skeleton chips | "No matches — try fewer filters" | inline error | rendered | n/a |
| /portfolios/new submit | "Creating…" disabled | n/a | inline form error | redirect w/ "Backtest running" badge | n/a |
| Re-run backtest button | "Running…" + spinner | n/a | error toast | results refresh | "Polling… (3m)" w/ elapsed |

### Pass 3 — User Journey & Emotional Arc (6→9)

- /strategies: 5s "system alive" → 5m "drill into top performer" → 5y "compare quarters"
- /portfolios/new Static: 5s "asset tabs" → 5m "filter sector + state, weight" → 5y "see what worked"
- /portfolios/new Rule-Based: 5s "rule cards visible" → 5m "compose rules + breadth gate" → 5y "iterate, paper-trade winners (M16)"

### Pass 4 — AI Slop Risk (8→9)

App UI rules — already disciplined. CTAs use `bg-accent` (existing deep blue), no purple anywhere.

### Pass 5 — Design System Alignment (8→10)

Tokens to reuse:

| Token | Use |
|---|---|
| `bg-paper` | Page background |
| `border-paper-rule rounded-[2px]` | Cards/tables/modals |
| `text-ink-primary` / `text-ink-secondary` / `text-ink-tertiary` | Text hierarchy |
| `text-signal-pos` (green) / `text-signal-neg` (red) / `text-signal-warn` (amber) | Returns + states |
| `bg-accent` (deep blue) | CTAs |
| `font-serif` (Source_Serif_4) | Headings |
| `font-sans` (Inter) | Body |
| `font-mono` (JetBrains_Mono) | Numbers, tickers, JSON |

Components to reuse: M14's `EditGatePolicyModal` (rule cards), M13's `RecomputePanel` (polling), M14's `formatThreshold` + `formatIST` (display).

### Pass 6 — Responsive & Accessibility (5→9)

Mobile breakpoint **768px**:
- Tables → stacked cards
- Multi-tab pickers stack vertically
- Charts shrink 500×300 → 320×200, lose secondary lines
- Side drawers → full-screen modals

A11y:
- **44×44 touch targets** on all clickable rows + checkboxes
- **Keyboard**: Escape closes modals, Tab cycles, Enter submits (M14 pattern)
- **WCAG AA** color contrast — paper/ink-primary at 11.4:1 confirmed
- **ARIA**: every modal `role=dialog aria-modal aria-labelledby`; every chart has `sr-only` data-table fallback

### Pass 7 — Resolved design decisions

| Decision | Auto-pick |
|---|---|
| Equity curve y-axis | % return (comparable across strategies) |
| Drawdown fill | `bg-signal-neg/50` |
| Regime breakdown colors | Risk-On=`signal-pos/20`, Constructive=`accent/15`, Cautious=`signal-warn/15`, Risk-Off=`signal-neg/20` |
| InstrumentPicker tabs | Horizontal pill tabs: `Stocks (750) · ETFs (100) · Mutual Funds (592)` |
| Re-run modal default dates | Last 5 years |
| WeightTable sum indicator | Inline: green `✓ Sums to 100%` or amber `⚠ 87% allocated` |
| Empty rule-based holdings | "Holdings will appear after the first nightly run (M16)" + greyed paper toggle |
| Loading skeleton style | `animate-pulse` on `bg-paper-rule/30 rounded-[2px]` |
| Error retry button | `text-accent underline decoration-dotted` |

### Design completion

- Initial: 6/10 → Final: 9/10
- 18 decisions added to spec
- 0 decisions deferred
- 0 mockups (App UI alignment to existing system)

