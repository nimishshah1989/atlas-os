# Atlas v6 — Frontend Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to dispatch each task to a fresh implementer subagent. Each task is independently dispatchable; tasks within a Phase run in parallel ONLY when the dependency graph permits. Strict serial gate between Phase A and Phases B+.

| Field | Value |
|---|---|
| **Date** | 2026-05-26 |
| **Branch** | `feat/v6-deep-search-all-cells` |
| **Goal** | Ship the v6 frontend — 14 priority pages + 17 components + portfolio-awareness layer + 2 missing pages — to `atlas.jslwealth.in` |
| **Inputs** | `docs/v6/design-application.md` (canonical design lock) · `~/.gstack/projects/atlas-os/eng-plans/2026-05-26-v6-design-build-eng-review.md` (40-task spine) · `~/.gstack/projects/atlas-os/design-plans/2026-05-26-v6-fund-manager-critique.md` (6 critical FM-lens fixes) · `CONTEXT.md` (canonical v6 vocabulary) |
| **Architecture** | Phase-gated build. Phase A (shared primitives + skeletons + 5 new query modules) is a SERIAL prerequisite. Phase B (portfolio-awareness data + components) lands before page composites so pages can wire it in. Phase C (page composites) parallelizes across page owners. Phase D (FM-critic new components) fills the 6 critical gaps + 2 missing pages. Phase E (audit trail + methodology). Phase F (QA + ship). |
| **Tech stack** | Next.js 15.3.9 App Router (RSC + client components) · React 19 · postgres-js 3.4.5 (session-mode Supabase pooler) · Tailwind v4 `@theme` tokens · Recharts 3.8 · D3 v7 (tree-shaken) · Radix Tooltip · `@tanstack/react-virtual` (NEW) · Vitest + Testing Library · Playwright + axe-core for E2E + a11y |

## Verdict at a glance

Design lock is shipable. Eng review's 40-task spine is correct on sequencing and data-layer scope. FM critic's 6 criticals add a portfolio-awareness LAYER (not a single component) — handled here as a dedicated Phase B with 8 net-new tasks (5 data, 3 component) that every page composite consumes. Total: **60 discrete tasks across 6 phases** (post-adversarial reconciliation + ground-truth migration scan: +A.0 data pre-flight, +A.10 decimal utility, +B.4 split into B.4a/B.4b), **58 AFK + 2 HITL** (the 2 HITLs are F.3 performance-on-Indian-latency + F.6 design-review judgement; the data-decision HITLs both reviewers raised resolved autonomously via ground-truth migration scan to the obvious technical default), parallelizable to ~9-14 calendar passes with 3-4 concurrent implementer subagents.

## Patches applied (adversarial review reconciliation 2026-05-26)

Two independent adversarial reviewers (Opus 4.7 fresh-context + superpowers:code-reviewer) ran on this plan after v1 was written. Both verdicts: **SHIP_WITH_FIXES**. Patches applied below — implementers MUST work from this patched version, not any earlier copy.

**CRITICAL fixes applied:**

1. **Data availability pre-flight** — NEW task `A.0` added. Ground-truth check against `migrations/versions/` found **3 missing tables** (NOT 5 as initial reviews implied — both reviewers had partial errors): `atlas_universe_snapshot`, `atlas_sector_breadth_daily`, `atlas_fund_holdings_history` do NOT exist. `atlas_mf_switch_rules` DOES exist (migration 085 — Opus correct, code-reviewer wrong). `atlas_ledger` exists (NOT `atlas_ledger_public` as design lock implied — single name, no `_public` suffix). A.0 is the gate: either derive missing data from existing tables OR land migration 094.
2. **`drift_status` enum literals corrected** — actual values per migration 080 are `{healthy, drift_warn, deprecated}`, NOT `{clean, drift_warn, drift_confirmed}` as v1 stated. Vocabulary lock updated below.
3. **`predicted_excess` column source corrected** — column exists on `atlas_signal_calls` + `atlas_etf_scorecard` + `atlas_drift_event_log`, but NOT on `atlas_cell_definitions`. Tasks reading it must source from `atlas_signal_calls.predicted_excess` joined per (cell_id, AS_OF).
4. **`atlas_universe_snapshot` → `atlas_universe_stocks`** — replaced everywhere; the former is vaporware per migration 081z comment.
5. **`atlas_fund_holdings_history` → `atlas_fund_scorecard.top_holdings` JSONB** — replaced in B.3 acceptance.
6. **`atlas_ledger_public` → `atlas_ledger`** — actual table per migration 083; corrected in D.10.
7. **Autonomous A.0 resolution** — given the ground-truth check, the migration-vs-rewrite decisions resolve as follows (no need to wait on Nimish for these — recommended technical defaults applied):
   - `atlas_universe_snapshot` → rewrite to `atlas_universe_stocks` (canonical)
   - `atlas_sector_breadth_daily` → derive on-the-fly from `atlas_scorecard_daily.features` JSONB (`ema_distance_20/50/200` already present per migration 080) — no new table needed for v6.0
   - `atlas_fund_holdings_history` → use `atlas_fund_scorecard.top_holdings` JSONB (already decided in B.3)
   - `atlas_mf_switch_rules` → table exists in migration 085; only seed data may need to be added (separate seed migration if rules aren't already populated)
   - `atlas_ledger_public` → rename references to `atlas_ledger`
   - Benchmark sector weights (B.2) → derive from `de_index_constituents` weighted by sector (table exists per `atlas/preflight.py`)
   - Position sizing (B.5) → implementer greps for v2 `computeSizing`; if zero matches, escalate back to HITL
8. **File-conflict serialization** — C.17, D.1, D.2, D.12 all mutate `app/v6/today/page.tsx`. Co-ownership matrix added (see end of Phase D). All four assigned to ONE implementer in a single batch.
9. **PortfolioBadge wiring** — D.4, D.5, D.6, D.7, D.8 acceptance criteria updated with explicit PortfolioBadge wiring (closes FM-critic §1.7 critical gap #1).
10. **Decimal transport utility** — NEW task `A.10` added. `lib/v6/decimal.ts` with `toNumber()` helper for postgres-js Decimal-as-string → chart number conversion. Lint gate added in F.4.

**HIGH fixes applied:**

11. **AuditTrailTab Section 4 promoted back to v6.0** — data already loaded by C.1 + C.3; deferral was kicking the audit tab's strongest moment. Section 6 deferral stands (genuinely v6.1 — needs ensemble per-stock evaluation).
12. **B.4 split** — `getMatrixDiff()` + `getBookDiff()` (universe vs portfolio concerns separated).
13. **HITL re-classification** — B.2, B.3, B.5, D.5, D.10 moved from AFK to HITL pending Nimish decisions.
14. **Page-shell rule clarified** — C.16, D.6, D.8, D.10 `page.tsx` files MUST remain ≤250 LOC thin wrappers; all logic lives in `*Client.tsx` siblings.
15. **AMC-leaderboard-for-ETFs** — moved into Vocabulary lock as explicit override of design-lock §6.5 (per FM-critic §1.5).

**MEDIUM fixes applied:**

16. **C.14 → E.4 dependency** added (both modify CellMatrix tile chip rendering).
17. **D.12 serialized after D.1** (D.12 extends DiffSinceYesterdayPanel created in D.1).
18. **A.4 "allow-large permitted" pre-authorization removed** — force 600-LOC budget; data splits into JSON if needed.
19. **E.2 pre-split** into `ClosedLoopDiagram.tsx` + `ClosedLoopNodeDrawer.tsx`.
20. **Tighter acceptance criteria** for A.4 (archetype-keyword fixtures), A.5 (DOM-mirror snapshot test), C.4 (<250ms p95 + no Seq Scan), C.7 (numeric attribution string), C.10 (concentration badge class+copy fixtures), C.14 (failed-gate microcopy truth table), F.2 (axe-core rule set + viewport).

Full critique files: `~/.gstack/projects/atlas-os/eng-plans/2026-05-26-v6-plan-opus-adversarial-review.md` (Opus 4.7), `~/.gstack/projects/atlas-os/eng-plans/2026-05-26-v6-plan-code-reviewer-pass.md` (code-reviewer).

## Vocabulary lock (CONTEXT.md authoritative)

When the eng review or design lock conflicts with CONTEXT.md, **CONTEXT.md wins**. Implementers MUST use canonical terms from CONTEXT.md:

- Cell state vocabulary: `POSITIVE` / `NEUTRAL` / `NEGATIVE` (NOT BUY/HOLD/AVOID). Display labels (`BUY`/`ACCUMULATE`/`WATCH`/`HOLD`/`AVOID`/`SELL`) are **rendered in the UI based on ownership**. The design lock §4 ThesisBullets `action` field stores the display label; the underlying signal is the 3-state enum.
- `signal_call_id` — UUID per INACTIVE→ACTIVE trigger, NOT per daily snapshot.
- `cell_id` — `atlas_cell_definitions.cell_id` (e.g., `Mid_12m_Pullback`). The eng review uses `/matrix/[cell]` for the cell detail route; the FM critic introduced `/v6/cells/[cell_id]`. **Decision: use `/v6/cells/[cell_id]`** (alias `/matrix/[cell]` redirects there) — namespaced under `/v6/` for consistency with rest of the v6 surface.
- `drift_status` ∈ {`healthy`, `drift_warn`, `deprecated`} — **per migration 080 `DRIFT_STATUS` enum** (verified 2026-05-26). NOT `{clean, drift_warn, drift_confirmed}` as design lock implied. Drift is **advisory** in v6 (CONTEXT.md F3 revision). UI surfaces `drift_warn` within 24h. Implementers MUST use these exact literal values in TypeScript discriminated unions and SQL filter predicates.
- `deployment_multiplier` — regime-derived sizing scalar (0.5x / 1.0x / 1.5x). Hero number on `/regime`.
- SWITCH semantics — same-category only at v6 launch (CONTEXT.md Q11/D5). Q3/Q4 → Q1/Q2, ≥6mo consistency, tie-break expense.
- Cap-tier binding rule — position exits per the cell it triggered into, not its current tier. UI must label "triggered as Mid" even if the stock now reads Large.
- Universe count — **727 today**, rises to **~737-739 post-Phase-0.5a**. Don't hardcode "750"; read from `atlas_universe_stocks` (canonical table per migration 002; `atlas_universe_snapshot` does NOT exist).
- **`predicted_excess` source** — column lives on `atlas_signal_calls` (migration 080) + `atlas_etf_scorecard` (migration 085) + `atlas_drift_event_log` (migration 088). NOT on `atlas_cell_definitions`. Cell-level `predicted_excess` must be sourced from the latest signal call (`SELECT predicted_excess FROM atlas_signal_calls WHERE cell_id = ? AND status='ACTIVE' ORDER BY entry_date DESC LIMIT 1`).
- **AMC leaderboard scope override**: design-lock §6.5 says "AMC leaderboard (funds only)". v6 launch implements it for **funds AND ETFs** per FM-critic §1.5 critical gap #3. This is a documented override.

Flagged mismatches:
- Eng review §7 calls the cell detail route `/matrix/[cell]`. FM critic uses `/v6/cells/[cell_id]`. Resolved above in favor of FM critic + redirect.
- Design lock §4 action enum includes `TRIM` and `BUY`/`AVOID`. CONTEXT.md replaced `TRIM` with `SELL`. **Implementers use CONTEXT.md.** Display-label table in ThesisBullets must encode the ownership-aware rendering rule.

## Architectural rules (hook-enforced)

- 600 LOC source / 800 LOC tests / **250 LOC page shells** (`app/**/page.tsx`). When a page would exceed 250 LOC, factor its body into a sibling `*Client.tsx` or split into composite components.
- No cross-context imports between `atlas/` packages — frontend has no equivalent boundary but each `components/v6/<Component>.tsx` imports from `lib/v6/`, `lib/queries/v6/`, `lib/eli5/`, or v2 reused components only. No reaching across page directories.
- Decimal for money in TS: use `string` for transport (Postgres NUMERIC stringifies) and `Intl.NumberFormat('en-IN')` for display. Never `Number()` on a currency value.
- Tz-aware datetimes: every "as-of" timestamp comes from `atlas_provenance_log` or `getLatestSnapshotDate()`; never `new Date()` on the render path.
- `next.config.js`-level `force-dynamic` retained on every `/v6/*` route — server components own data fetch + Suspense streams the chrome.

---

## Phase A — Shared primitives (SERIAL — must land before any other phase)

**Prerequisites:** None.
**Exit gate:** all 9 Phase A tasks complete, tests pass, primitives merged to `feat/v6-deep-search-all-cells`. Phase B+ are GATED on this.
**Why serial:** every composite component and page composite binds to TenureToggle / BenchmarkToggle / ColumnChooser. Building consumers first triggers a refactor wave (eng review §1 risk #1).

### Task A.0 — Data availability pre-flight + data-source map (AFK with seed-data check)
- **Goal**: Verify every table referenced in `lib/queries/v6/` actually exists in `migrations/versions/`, write the data-source map, verify `atlas_mf_switch_rules` is seeded with rules. Per ground-truth check 2026-05-26, the autonomous decisions are pre-resolved in the patch header above; A.0 verifies them in code and confirms seed data.
- **Files**:
  - Create `scripts/v6_data_availability_audit.py` — greps every `lib/queries/v6/*.ts` for `FROM\s+(\w+)` + `JOIN\s+(\w+)`, asserts each appears in `migrations/versions/*.py` as `op.create_table(...)`
  - Create `docs/v6/data-source-map.md` — every component → query module → source table mapping, machine-checkable
  - Run `SELECT COUNT(*) FROM atlas_mf_switch_rules` against Supabase atlas-os — if zero, escalate (seed via a small migration 094 or inline INSERT)
- **Depends on**: none (gate task)
- **AFK / HITL**: AFK (autonomous decisions pre-applied; only seed-data check is gated)
- **Spec ref**: Opus adversarial review §1, code-reviewer adversarial review §1; ground-truth corrections per 2026-05-26 migration scan
- **Acceptance**:
  - [ ] `scripts/v6_data_availability_audit.py` runs green: zero unresolved table references (after the autonomous renames in the patch header are applied to query modules)
  - [ ] `docs/v6/data-source-map.md` covers all 14 query modules with explicit source table per query, references migration file where applicable
  - [ ] `atlas_mf_switch_rules` seed count verified ≥1 (if zero, write `migrations/versions/094_v6_mf_switch_rules_seed.py` populating sensible defaults: Q3→Q1 same-category, ≥6mo consistency, expense tie-break)
  - [ ] `atlas_ledger` row count verified — confirms it's the right source for D.10 "realized outcomes per signal_call"
- **Tests**: `tests/scripts/test_v6_data_availability_audit.py` (3 cases: missing table detected, all-resolved passes, seed-data check)
- **Complexity**: M

### Task A.1 — TenureToggle + useTenurePreference hook
- **Goal**: Shared [1m 3m 6m 12m] segmented control with URL-param-primary + localStorage-seed persistence.
- **Files**:
  - Create `frontend/src/lib/v6/persistence.ts` (exports `useTenurePreference`, `useBenchmarkPreference`)
  - Create `frontend/src/components/v6/TenureToggle.tsx`
  - Create `frontend/src/components/v6/__tests__/TenureToggle.test.tsx`
- **Depends on**: none
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §3.1, eng-review §3 (state mgmt fix #1), eng-review decision #1 (URL+LS hybrid)
- **Acceptance**:
  - [ ] Default tenure is `6m`
  - [ ] URL `?tenure=3m` overrides localStorage; localStorage seeds when URL absent
  - [ ] Click writes BOTH URL and localStorage under key `v6.tenure.<pageKey>`
  - [ ] 4 segments rendered, ARIA `role="radiogroup"`, keyboard-navigable (←/→)
  - [ ] Suspense-safe (uses `useSearchParams` inside a client component wrapped at the page level)
  - [ ] Unit tests cover: URL-truth, LS-seed, click writes both, default 6m, keyboard nav
- **Tests**: `TenureToggle.test.tsx` (5 cases)
- **Complexity**: S

### Task A.2 — Gold availability query + BenchmarkToggle
- **Goal**: Shared [Nifty 50 / Nifty 500 / Gold] toggle. Gold pill hidden when `de_index_prices` lacks a GOLD series.
- **Files**:
  - Create `frontend/src/lib/queries/v6/gold_availability.ts`
  - Create `frontend/src/lib/queries/v6/__tests__/gold_availability.test.ts`
  - Create `frontend/src/components/v6/BenchmarkToggle.tsx`
  - Create `frontend/src/components/v6/__tests__/BenchmarkToggle.test.tsx`
- **Depends on**: A.1 (extends `useBenchmarkPreference` in same module)
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §3.2, eng-review §2 (data flow fix #6), eng-review edge case #4
- **Acceptance**:
  - [ ] `isGoldAvailable(): Promise<boolean>` runs `SELECT EXISTS(SELECT 1 FROM de_index_prices WHERE benchmark_code = 'GOLD' LIMIT 1)`, memoized per request via `React.cache()`
  - [ ] Default benchmark is `nifty500`
  - [ ] When Gold unavailable, only 2 pills render (Nifty 50, Nifty 500)
  - [ ] Same URL+LS persistence pattern as A.1
  - [ ] Unit + integration tests
- **Tests**: `BenchmarkToggle.test.tsx` (6 cases incl. gold-hide), `gold_availability.test.ts` (2 cases)
- **Complexity**: S

### Task A.3 — ColumnChooser + useColumnPreferences hook
- **Goal**: Per-table column visibility manager with grouped checkboxes, per-page key, reset-to-default.
- **Files**:
  - Create `frontend/src/lib/v6/useColumnPreferences.ts`
  - Create `frontend/src/components/v6/ColumnChooser.tsx`
  - Create `frontend/src/components/v6/__tests__/ColumnChooser.test.tsx`
- **Depends on**: none
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §3.3, eng-review §1 fix (extend existing `ColumnToggle.tsx`)
- **Acceptance**:
  - [ ] 5 column groups supported: Returns / Risk / Technicals / Atlas signals / Benchmarks
  - [ ] Per-page key namespacing (`v6.columns.<pageKey>`) — switching pages doesn't leak preferences
  - [ ] "Reset to default" button restores `defaults` prop
  - [ ] Selection persists to localStorage; SSR-safe (initial render uses defaults, hydration patches in)
  - [ ] Settings-icon trigger top-right of any table; modal closes on outside-click + Esc
  - [ ] Unit tests cover: per-page isolation, reset, persistence, modal a11y
- **Tests**: `ColumnChooser.test.tsx` (6 cases)
- **Complexity**: S

### Task A.4 — Thesis registry (lib/eli5/thesis.ts) — 19 archetypes
- **Goal**: Pure-function library that maps `(archetype, cap_tier, tenure, direction, …features) → ThesisBullets`. Zero component imports.
- **Files**:
  - Create `frontend/src/lib/eli5/thesis.ts` (300-450 LOC; allow-large permitted)
  - Create `frontend/src/lib/eli5/__tests__/thesis.test.ts` (parameterized)
- **Depends on**: none
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §4 (full archetype table), CONTEXT.md cell-state vocabulary
- **Acceptance**:
  - [ ] Exports `type ThesisBullets = { action: ActionVerb; bullets: string[] }` where `ActionVerb` is the 6-label union per CONTEXT.md (BUY/ACCUMULATE/HOLD/WATCH/AVOID/SELL — NOT TRIM)
  - [ ] Exports `generateThesis(input: ThesisInput): ThesisBullets`
  - [ ] All 19 archetypes implemented with POSITIVE + NEGATIVE variants where the table specifies them (14 POSITIVE + 5 NEGATIVE archetypes)
  - [ ] Each thesis is 3-5 bullets, 10-25 words each, `**N%**` markdown for bolded numerics
  - [ ] `direction` argument from `{POSITIVE, NEGATIVE}` (matches CONTEXT.md cell state)
  - [ ] Display-label derivation: if `is_held === true` POSITIVE→ACCUMULATE, NEUTRAL→HOLD, NEGATIVE→SELL; else POSITIVE→BUY, NEUTRAL→WATCH, NEGATIVE→AVOID
  - [ ] Parameterized test covers all 19 archetypes × 2 directions × {held, not-held} edge cases — fails if any combination throws or returns < 3 bullets
- **Tests**: `thesis.test.ts` (76 cases via vitest `test.each`)
- **Complexity**: L

### Task A.5 — Skeleton library (10 per-page skeletons)
- **Goal**: One `Skeleton<PageName>.tsx` per v6 page. No data deps. Used by `loading.tsx` files.
- **Files**:
  - Create `frontend/src/components/v6/skeletons/SkeletonMatrix.tsx`
  - Create `frontend/src/components/v6/skeletons/SkeletonToday.tsx`
  - Create `frontend/src/components/v6/skeletons/SkeletonStocks.tsx`
  - Create `frontend/src/components/v6/skeletons/SkeletonStockDetail.tsx`
  - Create `frontend/src/components/v6/skeletons/SkeletonSectors.tsx`
  - Create `frontend/src/components/v6/skeletons/SkeletonSectorDetail.tsx`
  - Create `frontend/src/components/v6/skeletons/SkeletonFunds.tsx`
  - Create `frontend/src/components/v6/skeletons/SkeletonFundDetail.tsx`
  - Create `frontend/src/components/v6/skeletons/SkeletonETFs.tsx`
  - Create `frontend/src/components/v6/skeletons/SkeletonETFDetail.tsx`
  - Create `frontend/src/components/v6/skeletons/SkeletonRegime.tsx`
  - Create `frontend/src/components/v6/skeletons/SkeletonMethodology.tsx`
  - Create `frontend/src/components/v6/skeletons/SkeletonCellDetail.tsx`
  - Create `frontend/src/components/v6/skeletons/SkeletonScreener.tsx`
- **Depends on**: none
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §8 (state coverage), eng-review §3 fix #3
- **Acceptance**:
  - [ ] 14 skeleton components, each <100 LOC, no async, no external imports beyond Tailwind classnames + a single shared `<Shimmer/>` primitive
  - [ ] Each skeleton mirrors its page's gross layout (header strip + body grid)
  - [ ] No `aria-busy="true"` flicker — skeletons are decorative; the Suspense boundary handles announcement
- **Tests**: snapshot tests for each (`SkeletonMatrix.test.tsx`, etc.) — 14 trivial tests
- **Complexity**: M

### Task A.6 — InfoTooltip extension (deterministic-translation slot)
- **Goal**: Extend existing v2 InfoTooltip to support a 2-line variant: definition + "↳ in plain English" deterministic translation.
- **Files**:
  - Modify `frontend/src/components/ui/InfoTooltip.tsx` (verify path; if absent, create `frontend/src/components/v6/InfoTooltip.tsx`)
  - Update `frontend/src/components/ui/__tests__/InfoTooltip.test.tsx` (or create new)
- **Depends on**: none
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §1 ("Every number has an InfoTooltip"), §13 acceptance criteria
- **Acceptance**:
  - [ ] New prop `translation?: string` renders a second line prefixed with `↳ ` in ink-3
  - [ ] Backward-compatible: existing single-line callers unchanged
  - [ ] ARIA-described association preserved
- **Tests**: 3 cases (single-line, with-translation, keyboard activation)
- **Complexity**: S

### Task A.7 — GradeChip component
- **Goal**: AAA/AA/A/BBB/BB/B/failed-gate chip with DESIGN.md grade-chip styling, 0.14em letter-spacing.
- **Files**:
  - Create `frontend/src/components/v6/GradeChip.tsx`
  - Create `frontend/src/components/v6/__tests__/GradeChip.test.tsx`
- **Depends on**: none
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §6.1 cell tile, DESIGN.md grade-chips
- **Acceptance**:
  - [ ] Renders 7 variants: AAA / AA / A / BBB / BB / B / failed-gate
  - [ ] Color tokens from `signal-*` palette (NOT new tokens)
  - [ ] `aria-label="Atlas grade <variant>"`
  - [ ] Failed-gate variant uses paper-deep + ink-4 (design-app §6.1)
- **Tests**: 7 variant render cases + a11y label
- **Complexity**: S

### Task A.8 — State persistence contract README
- **Goal**: Document URL+LS contract for downstream implementers.
- **Files**:
  - Create `frontend/src/components/v6/STATE.md`
- **Depends on**: A.1, A.2, A.3
- **AFK / HITL**: AFK
- **Spec ref**: eng-review §3 fix #4
- **Acceptance**:
  - [ ] Documents URL params: `tenure`, `benchmark`, `sector_filter`, `tier_filter`, `cell_id`
  - [ ] Documents LS keys: `v6.tenure.<pageKey>`, `v6.benchmark.<pageKey>`, `v6.columns.<pageKey>`
  - [ ] Includes a "do not introduce a new state manager" rule (eng-review decision #11)
- **Tests**: n/a (docs)
- **Complexity**: S

### Task A.10 — Decimal transport utility + lint gate
- **Goal**: Postgres `NUMERIC` columns return as `string` through postgres-js. Recharts/D3 chart props require `number`. Without an explicit conversion boundary, charts silently render at width 0 when a stringified Decimal hits a numeric prop. Build the utility once + gate it via lint.
- **Files**:
  - Create `frontend/src/lib/v6/decimal.ts` — exports `toNumber(s: string | null | undefined): number | null`, `toNumberOr(s, fallback): number`, `formatINR(s, opts?)`, `formatPct(s, opts?)`, `signedPct(s, opts?)`
  - Create `frontend/src/lib/v6/__tests__/decimal.test.ts`
  - Update `frontend/.eslintrc.cjs` — add a custom rule (or `no-restricted-syntax` matcher) that flags `Number(x)` calls on values typed `string | null` inside `components/v6/**` and `lib/queries/v6/**` (proposes `toNumber(x)` instead)
- **Depends on**: none
- **AFK / HITL**: AFK
- **Spec ref**: Opus adversarial review §6 ("#1 risk other reviewers missed")
- **Acceptance**:
  - [ ] `toNumber("123.45") === 123.45`; `toNumber(null) === null`; `toNumber("not-a-number")` throws TypeError (fast-fail, not silent NaN)
  - [ ] `formatINR("12345.67")` returns `"₹12,345.67"` using `Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' })`
  - [ ] `formatPct("0.183")` returns `"+18.3%"` (default 1 decimal, signed when positive); negative renders `"-14.6%"`
  - [ ] `signedPct("0.183", { compact: false })` returns `"+18.30%"`
  - [ ] Lint rule fires on `Number(x)` patterns in `components/v6/**`; CI fails on violation
  - [ ] All existing v6 chart components (audit + grep for `Recharts` + `BarChart` + `Tooltip` props on numeric axes) updated to use `toNumber()` — covered as a Phase F.4 sweep
  - [ ] Unit tests cover: null pass-through, valid numeric, invalid string throws, currency format, percent signed format
- **Tests**: `decimal.test.ts` (8 cases)
- **Complexity**: S

### Task A.9 — Per-page Suspense + loading.tsx wiring
- **Goal**: Wrap each `/v6/*` route in Suspense; create `loading.tsx` sibling referencing the appropriate skeleton from A.5.
- **Files**:
  - Create `frontend/src/app/v6/today/loading.tsx`
  - Create `frontend/src/app/v6/stocks/loading.tsx`
  - Create `frontend/src/app/v6/stocks/[iid]/loading.tsx`
  - Create `frontend/src/app/v6/sectors/loading.tsx`
  - Create `frontend/src/app/v6/sectors/[name]/loading.tsx`
  - Create `frontend/src/app/v6/funds/loading.tsx`
  - Create `frontend/src/app/v6/funds/[code]/loading.tsx`
  - Create `frontend/src/app/v6/etfs/loading.tsx`
  - Create `frontend/src/app/v6/etfs/[iid]/loading.tsx`
  - Create `frontend/src/app/regime/loading.tsx`
  - Create `frontend/src/app/methodology/loading.tsx`
  - Create `frontend/src/app/matrix/loading.tsx`
  - Create `frontend/src/app/v6/cells/[cell_id]/loading.tsx`
  - Create `frontend/src/app/v6/screening/loading.tsx`
- **Depends on**: A.5
- **AFK / HITL**: AFK
- **Spec ref**: eng-review §3 fix #2
- **Acceptance**:
  - [ ] 14 loading.tsx files, each <20 LOC, re-export the matching skeleton
  - [ ] Each interactive `*Client.tsx` (created in later phases) is wrapped in `<Suspense fallback={<Skeleton.../>}>`
- **Tests**: covered by E2E (E1) — visual verification that chrome paints before data
- **Complexity**: S

---

## Phase B — Portfolio awareness layer (FM critic's #1 gap — gates page composites)

**Prerequisites:** Phase A complete (signed off on `feat/v6-deep-search-all-cells`).
**Exit gate:** all 8 Phase B tasks complete. Phase C (page composites) consumes the portfolio-awareness primitives.
**Why this phase exists:** FM critic §2 recurring weakness #1 — "Portfolio-awareness is bolted-on, not woven in." Building this BEFORE page composites means pages wire it once, not refactor later.

### Task B.1 — Portfolio aggregation query (book-state by holding)
- **Goal**: Return per-iid book state: portfolios holding the iid, weight range, aggregate book weight, last-add date. Same shape consumed by all "held-in-N-portfolios" UI.
- **Files**:
  - Create `frontend/src/lib/queries/v6/portfolio_holdings.ts`
  - Create `frontend/src/lib/queries/v6/__tests__/portfolio_holdings.test.ts`
- **Depends on**: none (Phase B can begin in parallel with Phase A merge)
- **AFK / HITL**: AFK
- **Spec ref**: FM-critic §1.4 critical gap #1, §5 critical fix #1
- **Acceptance**:
  - [ ] Exports `getHoldingState(iid: string): Promise<HoldingState | null>` where `HoldingState = { portfolio_count: number; weight_range: [string, string]; aggregate_weight: string; last_add_date: string | null }`
  - [ ] Exports `getHeldIidSet(): Promise<Set<string>>` — fast lookup for list-page row badges (memoized per request via `React.cache()`)
  - [ ] Reads from `atlas_paper_portfolio` (NOT `atlas_user_lots` — paper book is v6 launch scope)
  - [ ] Returns null when user holds zero portfolios
  - [ ] Decimal values stringified (no float)
- **Tests**: 4 cases (multi-portfolio, single-portfolio, no-holding, decimal precision)
- **Complexity**: M

### Task B.2 — Sector book exposure query
- **Goal**: Per-sector aggregate book weight vs Nifty 500 weight (overweight/underweight).
- **Files**:
  - Create `frontend/src/lib/queries/v6/sector_book_exposure.ts`
  - Create `frontend/src/lib/queries/v6/__tests__/sector_book_exposure.test.ts`
- **Depends on**: A.0
- **AFK / HITL**: AFK — autonomous decision applied: benchmark weights derived from `de_index_constituents` weighted aggregation by sector (table exists per `atlas/preflight.py`)
- **Spec ref**: FM-critic §1.9 critical gap #1, §1.10 critical gap #1; Opus review §1 hidden coupling #2
- **Acceptance**:
  - [ ] Exports `getSectorBookExposure(sector_name?: string): Promise<SectorBookExposure[]>` — overload accepts optional sector filter so detail pages don't round-trip 30 rows for one
  - [ ] Each row = `{ sector_name: string; book_weight: string; benchmark_weight: string; delta_pp: string; holding_count: number }`
  - [ ] Book sector mapping uses `atlas_paper_portfolio` → `atlas_universe_stocks.sector` join (paper portfolio stores instrument_id only; sector lookup MUST go through universe table)
  - [ ] Benchmark weight derived from `SELECT sector, SUM(weight) FROM de_index_constituents WHERE index_code='NIFTY500' AND is_active GROUP BY sector` (current snapshot only — historical weights deferred to v6.1)
  - [ ] Stringified Decimals, signed delta
- **Tests**: 4 cases (overweight, underweight, no-holding, single-sector filter)
- **Complexity**: M

### Task B.3 — Funds holding stock query
- **Goal**: For a stock iid, list mutual funds with material exposure (top 10 by AUM, with each fund's Atlas grade).
- **Files**:
  - Create `frontend/src/lib/queries/v6/funds_holding_stock.ts`
  - Create `frontend/src/lib/queries/v6/__tests__/funds_holding_stock.test.ts`
- **Depends on**: A.0
- **AFK / HITL**: AFK — autonomous decision applied: use `atlas_fund_scorecard.top_holdings` JSONB (current top-N snapshot). Historical holdings deferred to v6.1; FM-critic Scene 7 ask is satisfied by current-snapshot data.
- **Spec ref**: FM-critic §1.4 critical gap #1, §4 Scene 7 fix; Opus review §4 critical fix #2; code-reviewer §B.3 critical
- **Acceptance**:
  - [ ] Exports `getFundsHoldingStock(iid: string): Promise<FundHolding[]>` where each row = `{ fund_code: string; fund_name: string; aum_cr: string; weight_pct: string; atlas_grade: string }`
  - [ ] Limit 10, sorted by AUM desc
  - [ ] Excludes funds where weight < 0.5% (immaterial)
  - [ ] Reads from `atlas_fund_scorecard` cross-join lateral `jsonb_to_recordset(top_holdings) AS h(instrument_id uuid, weight_pct numeric)` filtered to the target iid (NOT from `atlas_fund_holdings_history` which does not exist)
  - [ ] Includes a comment in the SQL noting the migration 093 source of `top_holdings`
- **Tests**: 3 cases (multi-fund, few-funds, no-funds) + 1 JSONB-shape regression test
- **Complexity**: M

### Task B.4 — Diff-since-yesterday query (SPLIT into B.4a + B.4b)

Per code-reviewer adversarial review: original single B.4 mixed universe-level and portfolio-level concerns. Split so failure of one doesn't break both panels.

#### Task B.4a — Matrix diff (universe-level)
- **Goal**: Returns matrix diff: which cells started firing, went dormant, gained drift_warn overnight.
- **Files**:
  - Create `frontend/src/lib/queries/v6/matrix_diff.ts`
  - Create `frontend/src/lib/queries/v6/__tests__/matrix_diff.test.ts`
- **Depends on**: A.0
- **AFK / HITL**: AFK
- **Spec ref**: FM-critic §1.1 critical gap #1
- **Acceptance**:
  - [ ] Exports `getMatrixDiff(): Promise<MatrixDiff>` where `MatrixDiff = { new_cells_firing: CellSummary[]; cells_dormant: CellSummary[]; new_drift_warns: CellSummary[] }`
  - [ ] Compares `atlas_signal_calls` + `atlas_drift_event_log` at `D` vs `D-1` (handles weekend/holiday gaps via `getLatestSnapshotDate()`)
  - [ ] `new_drift_warns` filters on `drift_status='drift_warn'` (per corrected enum literal)
- **Tests**: 4 cases (typical-day, weekend-rollover, no-flips, all-flipped)
- **Complexity**: M

#### Task B.4b — Book diff (portfolio-level)
- **Goal**: Returns portfolio-level diff: which held stocks flipped state overnight.
- **Files**:
  - Create `frontend/src/lib/queries/v6/book_diff.ts`
  - Create `frontend/src/lib/queries/v6/__tests__/book_diff.test.ts`
- **Depends on**: B.1
- **AFK / HITL**: AFK
- **Spec ref**: FM-critic §1.1 critical gap #1, §5 critical fix #3
- **Acceptance**:
  - [ ] Exports `getBookDiff(): Promise<BookDiff>` where `BookDiff = { held_iids_flipped: StockFlip[]; held_drift_warns: StockFlip[] }`
  - [ ] Cross-references B.1's `getHeldIidSet()` then joins to `atlas_scorecard_daily` at `D` vs `D-1`
  - [ ] Returns empty arrays (not null) when no held flips
- **Tests**: 4 cases (some-flipped, none-flipped, no-book, multi-flip)
- **Complexity**: M

### Task B.5 — Position sizing recommendation function
- **Goal**: Pure function `computeSizing(input) → SizingRec`. Restores v2 regression. Reads `deployment_multiplier`, current book weight, sector gap.
- **Files**:
  - Create `frontend/src/lib/v6/sizing.ts`
  - Create `frontend/src/lib/v6/__tests__/sizing.test.ts`
- **Depends on**: B.1, B.2
- **AFK / HITL**: AFK-with-escalation — implementer greps for v2 `computeSizing`; if exactly one canonical implementation surfaces, port it. If multiple inconsistent versions exist OR zero matches, BLOCK and escalate to Nimish via task notes. Do NOT invent sizing logic — sizing controls real positions.
- **Spec ref**: FM-critic §1.4 critical gap #2 (v6 regression), §5 critical fix #2
- **Acceptance**:
  - [ ] grep -rn "computeSizing\|computeSizing" frontend/src/ archived/ ../atlas-*/ documented in task notes
  - [ ] Exports `computeSizing(input: SizingInput): SizingRec` — PURE function, no DB calls
  - [ ] `SizingInput = { current_weight_pct: number; max_per_stock_pct: number; deployment_multiplier: number; sector_gap_pp: number; cell_conviction_depth: number /* 0..5 */ }`
  - [ ] `SizingRec = { suggested_add_pct: number; binding_constraint: 'max_per_stock' | 'deployment_cap' | 'sector_cap' | 'conviction_floor'; rationale: string }`
  - [ ] All numeric inputs cross the `lib/v6/decimal.ts` boundary at the CALLER (B.8 widget reads stringified weight_pct from B.1 and calls `toNumber()` before passing to `computeSizing`)
  - [ ] Unit tests cover all 4 binding constraints + boundary cases
- **Tests**: 8 cases
- **Complexity**: M

### Task B.6 — PortfolioBadge component (held-in-N-portfolios chip)
- **Goal**: Small chip rendered on stock list rows + stock detail hero. "Held in 4 portfolios · 4.1% book weight" treatment.
- **Files**:
  - Create `frontend/src/components/v6/PortfolioBadge.tsx`
  - Create `frontend/src/components/v6/__tests__/PortfolioBadge.test.tsx`
- **Depends on**: B.1
- **AFK / HITL**: AFK
- **Spec ref**: FM-critic §1.3 critical gap #1, §1.4 critical gap #1
- **Acceptance**:
  - [ ] Two variants: `compact` (single-line chip for table rows) + `expanded` (multi-line for hero)
  - [ ] Reads `HoldingState`; renders nothing if `null` (not "held in 0 portfolios" — silent absence)
  - [ ] InfoTooltip on hover shows full portfolio list (top 5 by weight)
  - [ ] ARIA-labelled
- **Tests**: 4 cases (compact, expanded, null, tooltip)
- **Complexity**: S

### Task B.7 — SectorBookStrip component
- **Goal**: Horizontal strip rendered above sector list table + at top of sector detail page. Shows book vs Nifty 500 sectoral exposure with overweight/underweight badges.
- **Files**:
  - Create `frontend/src/components/v6/SectorBookStrip.tsx`
  - Create `frontend/src/components/v6/__tests__/SectorBookStrip.test.tsx`
- **Depends on**: B.2
- **AFK / HITL**: AFK
- **Spec ref**: FM-critic §1.9 critical gap #1, §1.10 critical gap #1
- **Acceptance**:
  - [ ] Renders 30 sector rows (or filtered to current sector for detail page)
  - [ ] Per row: sector name · book weight · benchmark weight · delta pp · OVERWEIGHT/UNDERWEIGHT/NEUTRAL chip
  - [ ] Stacked horizontal bar shows delta visually (signal-pos for overweight, signal-neg for under)
- **Tests**: 3 cases (all-sectors, single-sector, no-book)
- **Complexity**: M

### Task B.8 — PositionSizingWidget component
- **Goal**: Render the sizing recommendation on stock detail hero. "Suggested next add: +1.5% (binding: max_per_stock 5%; current 3.5%)."
- **Files**:
  - Create `frontend/src/components/v6/PositionSizingWidget.tsx`
  - Create `frontend/src/components/v6/__tests__/PositionSizingWidget.test.tsx`
- **Depends on**: B.5 (sizing fn), B.1 (HoldingState)
- **AFK / HITL**: AFK
- **Spec ref**: FM-critic §1.4 critical gap #2, §5 critical fix #2
- **Acceptance**:
  - [ ] Renders: "Suggested next add: **+X%**" headline + binding-constraint chip + 1-line rationale
  - [ ] Hidden when `HoldingState === null` AND `is_new_entry !== true` (do not show sizing for non-held names unless entry is on the table)
  - [ ] InfoTooltip on binding-constraint chip explains it
  - [ ] When `deployment_multiplier < 1.0`, show "Regime cap: positions sized 50% of normal" microcopy
- **Tests**: 5 cases (held, not-held-but-buy, deployment-cap, max-per-stock, all-zero)
- **Complexity**: M

---

## Phase C — Page-level composites (page composites + foundational data queries from eng-review)

**Prerequisites:** Phases A + B complete.
**Exit gate:** all 17 Phase C tasks complete.
**Parallelization:** the C-data tasks (C.1-C.5) run in parallel with each other. C-component tasks (C.6-C.13) consume both Phase A primitives and Phase C-data outputs. C-page tasks (C.14-C.21 below in Phase E gating) consume both.
**Note on FM-critic interaction:** Tasks D.x in Phase D layer on top of the page composites here. So C lands the spine, D fills the 6 critical gaps + 2 missing pages.

### Task C.1 — `lib/queries/v6/cells.ts` (direct Supabase cell read)
- **Goal**: Replace `localhost:8002/v1/cell.definitions` demo-fallback. Direct Supabase read for `/matrix` and `/v6/cells/[cell_id]`.
- **Files**:
  - Create `frontend/src/lib/queries/v6/cells.ts`
  - Create `frontend/src/lib/queries/v6/__tests__/cells.test.ts`
- **Depends on**: A (primitive layer)
- **AFK / HITL**: AFK
- **Spec ref**: eng-review B1, design-application.md §6.1
- **Acceptance**:
  - [ ] Exports `getCellDefinitions(): Promise<CellDefinition[]>` reading from `atlas_cell_definitions` joined to latest `atlas_cell_walkforward_runs` (top run per cell)
  - [ ] Exports `getCellById(cell_id: string): Promise<CellDetail>` returning rule_dsl, walk-forward windows, IC, fric-adj, BH-FDR q, drift_status, top-N firing stocks today
  - [ ] Returns `predicted_excess` field (FM-critic gap #1.2 fix — tile shows IC AND predicted excess)
  - [ ] Returns `disclaimers_applicable` (e.g., survivorship caveat for NEGATIVE cells — edge case #7)
- **Tests**: 4 cases (24-cell fetch, single-cell, failed-gate cell, drift_warn cell)
- **Complexity**: M

### Task C.2 — `lib/queries/v6/multi_benchmark_rs.ts`
- **Goal**: 5-series benchmark RS data per (iid, tenure) — stock / cohort / Nifty 500 / Nifty 50 / Gold.
- **Files**:
  - Create `frontend/src/lib/queries/v6/multi_benchmark_rs.ts`
  - Create `frontend/src/lib/queries/v6/__tests__/multi_benchmark_rs.test.ts`
- **Depends on**: A.2 (gold availability)
- **AFK / HITL**: AFK
- **Spec ref**: eng-review B2, design-application.md §7.2
- **Acceptance**:
  - [ ] Exports `getMultiBenchmarkRS(iid: string, tenure: Tenure): Promise<MultiBenchmarkRS>` where `MultiBenchmarkRS = { stock_return: string; cohort_median: string | null; nifty500: string | null; nifty50: string | null; gold: string | null }`
  - [ ] Cohort = same `cap_tier` per `atlas_scorecard_daily`
  - [ ] Returns `null` per series when data unavailable; component hides that row (design-app §7.2 graceful)
  - [ ] Single query with correlated subqueries; no N+1
- **Tests**: 4 cases (all-series, no-gold, no-cohort, weekend)
- **Complexity**: M

### Task C.3 — `lib/queries/v6/stock_technicals.ts`
- **Goal**: Unpack `atlas_scorecard_daily.features` JSONB into ema20/50/200, rsi_14, atr_pct_14, obv_slope_60d, dist_above_sma50/200, bb_pct_20d.
- **Files**:
  - Create `frontend/src/lib/queries/v6/stock_technicals.ts`
  - Create `frontend/src/lib/queries/v6/__tests__/stock_technicals.test.ts`
- **Depends on**: none
- **AFK / HITL**: AFK
- **Spec ref**: eng-review B3, design-application.md §6.4 Technicals tab
- **Acceptance**:
  - [ ] Exports `getStockTechnicals(iid: string, date: string): Promise<StockTechnicals | null>`
  - [ ] All values stringified Decimals; nullable when feature absent (insufficient history per CONTEXT.md universe rule)
  - [ ] Uses Postgres `->>` operator for JSONB unpack (single query)
- **Tests**: 4 cases (full-features, partial-features, missing-iid, new-listing)
- **Complexity**: S

### Task C.4 — `lib/queries/v6/audit_trail.ts`
- **Goal**: Provenance chain for AuditTrailTab. Joins 4 tables — `atlas_provenance_log`, `atlas_cell_walkforward_runs`, `atlas_cell_definitions.rule_dsl`, `atlas_signal_calls`. Sections 4 + 6 deferred per eng-review decision #3.
- **Files**:
  - Create `frontend/src/lib/queries/v6/audit_trail.ts`
  - Create `frontend/src/lib/queries/v6/__tests__/audit_trail.test.ts`
- **Depends on**: none
- **AFK / HITL**: AFK
- **Spec ref**: eng-review B4, design-application.md §7.1 (sections 1, 2, 3, 5, 7 only for v6 launch)
- **Acceptance**:
  - [ ] Exports `getAuditTrail(signal_call_id: string): Promise<AuditTrailData>` returning sections 1, 2, 3, 5, 7
  - [ ] Section 1: input data — universe membership, sector, ohlcv range from `atlas_universe_snapshot` + `de_equity_ohlcv` aggregates
  - [ ] Section 2: pipeline timestamps from `atlas_provenance_log`
  - [ ] Section 3: cell-rule evaluation outcome from `atlas_signal_calls`
  - [ ] Section 5: walkforward + IC + BH-FDR from `atlas_cell_walkforward_runs`
  - [ ] Section 7: verdict from `atlas_signal_calls` + `atlas_brief_cache.cell_id`
  - [ ] Returns `sections_4_and_6_deferred: true` flag — UI displays "Predicates met + cross-rule check available in v6.1"
- **Tests**: 3 cases (full-data, drift_warn-cell, missing-provenance)
- **Complexity**: L

### Task C.5 — `lib/queries/v6/multi_tenure_returns.ts`
- **Goal**: 6-tenure × 3-column (abs / rel / EMA-distance) matrix data for MultiTenureReturnsTable.
- **Files**:
  - Create `frontend/src/lib/queries/v6/multi_tenure_returns.ts`
  - Create `frontend/src/lib/queries/v6/__tests__/multi_tenure_returns.test.ts`
- **Depends on**: none
- **AFK / HITL**: AFK
- **Spec ref**: eng-review B5, design-application.md §6.4 Overview tab
- **Acceptance**:
  - [ ] Exports `getMultiTenureReturns(iid: string): Promise<MultiTenureReturns>` returning a 6×3 matrix of stringified Decimals
  - [ ] Tenures: 1d, 1w, 1m, 3m, 6m, 12m
  - [ ] Null cells (insufficient history) preserved; component renders em-dash
- **Tests**: 3 cases (full, missing-12m, missing-1d)
- **Complexity**: S

### Task C.6 — ThesisBullets component
- **Goal**: Renders the `ThesisBullets` type from A.4. Action-verb chip + bolded-number bullets.
- **Files**:
  - Create `frontend/src/components/v6/ThesisBullets.tsx`
  - Create `frontend/src/components/v6/__tests__/ThesisBullets.test.tsx`
- **Depends on**: A.4
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §1 Layer 2, eng-review C1
- **Acceptance**:
  - [ ] Renders the action verb in CAPS+bold at top
  - [ ] Each bullet: `**N%**` markdown rendered with mono numerics
  - [ ] Two density variants: `default` (full bullets) + `inline` (single bullet for table rows — FM-critic §1.3 medium gap fix)
- **Tests**: 4 cases (default, inline, all action verbs, empty-bullets edge)
- **Complexity**: S

### Task C.7 — MultiBenchmarkRSWaterfall component
- **Goal**: Nested signed-bar waterfall (Stock → Cohort → Nifty 500 → Nifty 50 → Gold). The eng-review §1 risk #1 high-leverage viz.
- **Files**:
  - Create `frontend/src/components/v6/MultiBenchmarkRSWaterfall.tsx`
  - Create `frontend/src/components/v6/__tests__/MultiBenchmarkRSWaterfall.test.tsx`
- **Depends on**: A.1, A.2, C.2
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §7.2, eng-review C2
- **Acceptance**:
  - [ ] 4-5 bars rendered; signed forest-green/terracotta
  - [ ] Attribution summary line: "Nifty 500 beat Nifty 50 by **+2.8pp** → Cohort added **+1.6pp** → Stock added **+6.8pp** on top"
  - [ ] Each bar has deterministic-translation line underneath
  - [ ] Null-row treatment (e.g., gold unavailable) hides that row gracefully
  - [ ] Re-renders on tenure / benchmark toggle change
- **Tests**: 8 cases (4-bar, 5-bar, null-cohort, null-gold, attribution-sum, tenure-change, benchmark-change, signed-bar-render)
- **Complexity**: L

### Task C.8 — BubbleRiskReturnChart component (extend StockBubbleChart)
- **Goal**: D3 scatter — risk-X, return-Y, log-AUM size, Atlas-state color. Eng-review decision #2: LIFT from `StockBubbleChart`, don't rebuild.
- **Files**:
  - Modify `frontend/src/components/stocks/StockBubbleChart.tsx` (add axis-selector + state-color props; preserve backward compat for v2 callers)
  - Create `frontend/src/components/v6/BubbleRiskReturnChart.tsx` (thin wrapper re-exporting StockBubbleChart with v6 defaults)
  - Create `frontend/src/components/v6/__tests__/BubbleRiskReturnChart.test.tsx`
- **Depends on**: A.1, A.2
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §7.5, eng-review C3 + decision #2
- **Acceptance**:
  - [ ] Accepts `axes: { x: 'risk' | 'vol_60d' | 'beta'; y: 'return' | 'rel_return' }` props
  - [ ] Bubble radius = `Math.max(4, Math.min(32, log10(aum_cr+1) * 6))`
  - [ ] Color by Atlas state (signal-pos / signal-pos@70 / signal-warn / signal-neg)
  - [ ] Hover tooltip card 280×120 with name + composite + ELI5 one-liner
  - [ ] Click navigates to detail page via Next router
  - [ ] Lazy-loaded via `React.lazy` (eng-review perf budget)
  - [ ] Renders 750 instruments under 120ms (test via `performance.now()`)
- **Tests**: 5 cases (750-row mount, hover, click-nav, color-by-state, lazy-load)
- **Complexity**: L

### Task C.9 — MultiTenureReturnsTable component
- **Goal**: 6×3 matrix with column chooser, sortable, persists column visibility.
- **Files**:
  - Create `frontend/src/components/v6/MultiTenureReturnsTable.tsx`
  - Create `frontend/src/components/v6/__tests__/MultiTenureReturnsTable.test.tsx`
- **Depends on**: A.1, A.3, C.5
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §6.4, eng-review C4
- **Acceptance**:
  - [ ] 6-row × 3-col matrix; null cells render em-dash with InfoTooltip "insufficient history"
  - [ ] Selected tenure column highlighted (synced with TenureToggle)
  - [ ] Column chooser top-right
  - [ ] Mono numerics, right-aligned, signed colors
- **Tests**: 6 cases (24-cell render, null cells, tenure-highlight, column-chooser, sort, signed-colors)
- **Complexity**: M

### Task C.10 — SectorBreadthPanel component
- **Goal**: 3 EMA gauges + concentration indicator + dispersion σ.
- **Files**:
  - Create `frontend/src/components/v6/SectorBreadthPanel.tsx`
  - Create `frontend/src/components/v6/__tests__/SectorBreadthPanel.test.tsx`
- **Depends on**: A.1
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §7.4, eng-review C5
- **Acceptance**:
  - [ ] 3 horizontal-bar gauges (EMA20 / EMA50 / EMA200) with % + trend arrow
  - [ ] Concentration badge: green <40%, amber 40-65%, red >65%
  - [ ] Dispersion σ line with "moderate / consensus / stockpicker's" qualitative label
  - [ ] Reads from `atlas_sector_breadth_daily` (verify table; if absent, flag in implementation)
- **Tests**: 4 cases (broad, narrow, distributed, missing-data)
- **Complexity**: M

### Task C.11 — IndustrySnapshot component
- **Goal**: 4-6 stat callouts for fund + ETF list pages.
- **Files**:
  - Create `frontend/src/components/v6/IndustrySnapshot.tsx`
  - Create `frontend/src/components/v6/__tests__/IndustrySnapshot.test.tsx`
- **Depends on**: none
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §6.5, eng-review C6
- **Acceptance**:
  - [ ] Renders 4-6 stat cards: total count, Atlas Leaders, Atlas Avoid, top category (with median), weakest category, AMC leaderboard (top 3, funds only)
  - [ ] Accepts `kind: 'funds' | 'etfs'` prop; AMC leaderboard hidden when ETFs (per FM-critic §1.5 ask: also add ETF AMC leaderboard — implementation note: include it for ETFs too)
- **Tests**: 3 cases (funds variant, ETFs variant, sparse-data)
- **Complexity**: M

### Task C.12 — SignatureMatrix component
- **Goal**: Grade × category mini-grid for fund + ETF list pages. Click-to-filter.
- **Files**:
  - Create `frontend/src/components/v6/SignatureMatrix.tsx`
  - Create `frontend/src/components/v6/__tests__/SignatureMatrix.test.tsx`
- **Depends on**: A.7 (GradeChip)
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §6.5, eng-review C7
- **Acceptance**:
  - [ ] Rows = grades (AAA / AA / A / BBB / BB / B); columns = categories
  - [ ] Funds categories: Large / Mid / Small / Flexi / Multi / ELSS / Hybrid
  - [ ] ETFs categories: broad / sector / thematic / commodity
  - [ ] Cell = count; click filters parent table by `(grade, category)`
- **Tests**: 3 cases (funds variant, ETFs variant, click-filter callback)
- **Complexity**: M

### Task C.13 — RankDecompositionCards component
- **Goal**: 4-layer horizontal card breakdown for fund + ETF detail.
- **Files**:
  - Create `frontend/src/components/v6/RankDecompositionCards.tsx`
  - Create `frontend/src/components/v6/__tests__/RankDecompositionCards.test.tsx`
- **Depends on**: none
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §6.6, eng-review C8
- **Acceptance**:
  - [ ] 4 layer cards: Risk-adjusted return (50% weight) / Style consistency / Holdings quality / Cost-aware net excess
  - [ ] Each card: score /100, weight %, 3-5 sub-metric bullets
  - [ ] Layer weights configurable via prop (defaults from `atlas_fund_scorecard` schema)
- **Tests**: 4 cases (full-data, missing-layer, weight-sum, sub-metric render)
- **Complexity**: M

### Task C.14 — `/matrix` page wire-up + redirect from old path
- **Goal**: Wire `/matrix` to direct Supabase read (C.1). Add NEGATIVE-direction caveat, drift-warn chip on tiles. Failed-gate microcopy differentiation (eng-review edge case #6).
- **Files**:
  - Modify `frontend/src/app/matrix/page.tsx`
  - Modify `frontend/src/components/v6/CellMatrix.tsx` (extend tile to render predicted_excess + drift_warn + held-count overlay)
  - Create `frontend/src/app/matrix/[cell]/page.tsx` (redirect to `/v6/cells/[cell_id]`)
- **Depends on**: A (primitives), B.1 (held-iid for tile overlay), C.1 (cells query)
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §6.1, FM-critic §1.2 critical gaps #1+2+3
- **Acceptance**:
  - [ ] 3×8 = 24 tiles render
  - [ ] Tile shows: grade chip · IC · fric-adj · predicted_excess · sample size · drift_warn chip when applicable · held-count badge ("12 of your book")
  - [ ] Failed-gate microcopy differentiates: "No rule survived" (n_gate_pass=0) vs "No candidates tested" (n_candidates=0) vs "Insufficient data"
  - [ ] NEGATIVE-direction tiles render the survivorship-caveat InfoTooltip
  - [ ] Page shell ≤250 LOC
- **Tests**: Vitest covers CellMatrix; E2E in E1 covers route
- **Complexity**: M

### Task C.15 — `/v6/stocks` list extend
- **Goal**: Wire BubbleRiskReturnChart, ColumnChooser, ThesisBullets-inline, owner badge (B.6). Default sort = signal-flip recency. Default 12-15 columns (per FM-critic §1.3 high gap #2).
- **Files**:
  - Modify `frontend/src/app/v6/stocks/page.tsx` (≤250 LOC)
  - Modify `frontend/src/components/v6/StocksTableV6.tsx`
  - Create `frontend/src/components/v6/StocksFilterRow.tsx` (multi-select chips + drift_warn / in_my_book filters)
- **Depends on**: A.1, A.2, A.3, B.6, C.6, C.8
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §6.3, FM-critic §1.3 critical gaps #1+2+3, §1.3 medium gaps
- **Acceptance**:
  - [ ] BubbleRiskReturnChart renders above table (lazy-loaded)
  - [ ] Table virtualized via `@tanstack/react-virtual` at >300 rows (eng-review perf budget)
  - [ ] Default 12 columns visible: own badge / symbol / name / sector / tier / ConvictionTape / 1d / 1w / 6m / IC / fric-adj / Action chip
  - [ ] Optional columns: predicted_excess, hit_rate, beta, σ, dist_ema200, RSI, RS-vs-{nifty50, nifty500, gold}, drift_status
  - [ ] Default sort: most-recent `signal_call.computed_at` desc
  - [ ] Filter chips: tier, sector, action verb, drift_warn, in_my_book (cross-references B.1)
  - [ ] Multi-row select state (compare / export — actions stubbed for v6.1 but UI present)
- **Tests**: extend `StocksTableV6.test.tsx` (4 new cases) + E2E in E1
- **Complexity**: L

### Task C.16 — `/v6/stocks/[iid]` hero + Overview + Technicals + Rule tabs
- **Goal**: Stock detail page hero (3-layer pattern) + Overview/Technicals/Rule tabs. Hero gains PortfolioBadge (B.6) + PositionSizingWidget (B.8) + cross-rule consistency depth metric.
- **Files**:
  - Modify `frontend/src/app/v6/stocks/[iid]/page.tsx` (≤250 LOC — body in client component)
  - Modify `frontend/src/components/v6/StockDetailClient.tsx`
  - Create `frontend/src/components/v6/StockHero.tsx` (Layers 1+2)
  - Create `frontend/src/components/v6/StockTabs.tsx` (Tab routing)
  - Create `frontend/src/components/v6/StockOverviewTab.tsx` (MultiBenchmarkRSWaterfall + RRGChart + DwellTimeline + MultiTenureReturnsTable + WithinStatePeers + FundsHoldingStock)
  - Create `frontend/src/components/v6/StockTechnicalsTab.tsx` (OBV + ATR + EMA panel + RSI sparkbars)
  - Create `frontend/src/components/v6/StockRuleTab.tsx` (cell + rule_dsl plain English + per-window backtest + HitRateRow + cross-rule check)
- **Depends on**: A, B.1, B.3, B.6, B.8, C.2, C.3, C.5, C.6, C.7, C.9, plus v2 components (RRGChart, DwellTimeline, OBV, ATR, WithinStatePeers, HitRateRow)
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §6.4, FM-critic §1.4 critical gaps #1+2+3 + high gap #1
- **Acceptance**:
  - [ ] Hero shows: ticker · grade · sector pill · ConvictionTape · Action verb · 3-5 thesis bullets · PortfolioBadge expanded · PositionSizingWidget · CrossRuleDepth metric ("Conviction depth: 1/5 rules") · 52w-high distance · drawdown-from-peak
  - [ ] Overview tab integrates `FundsHoldingStock` section (B.3 — top 10 mutual funds with each fund's Atlas grade)
  - [ ] Technicals tab uses C.3 data
  - [ ] Rule tab renders cell rule_dsl as plain English (read predicates from `atlas_cell_definitions.rule_dsl` JSONB)
  - [ ] cap-tier label respects binding rule ("Triggered as Mid" even if currently Large)
  - [ ] Page shell ≤250 LOC
- **Tests**: smoke test for each tab subcomponent (covered by E2E in E1)
- **Complexity**: L

### Task C.17 — `/v6/today` extend (3-col hero + recent signal_calls)
- **Goal**: Add 3-col hero (mini-matrix / regime / top conviction). Defer the FM-critic "diff since yesterday" panel + "your book at a glance" — those land in Phase D.
- **Files**:
  - Modify `frontend/src/app/v6/today/page.tsx` (≤250 LOC)
  - Create `frontend/src/components/v6/TodayHero.tsx`
  - Create `frontend/src/components/v6/RecentSignalCalls.tsx`
- **Depends on**: A, C.1 (cells), existing regime + top-conviction queries
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §6.2
- **Acceptance**:
  - [ ] 3-column hero (mini 24-cell matrix preview, regime card, top 5 conviction stocks)
  - [ ] Sector ladder snapshot section (top 5)
  - [ ] Recent signal_calls section: last 20 (FM-critic medium gap #1 — increased from 10), sortable, filterable
  - [ ] Page shell ≤250 LOC
- **Tests**: smoke + E2E
- **Complexity**: M

---

## Phase D — FM-critic critical fixes (6 critical + 2 missing pages)

**Prerequisites:** Phase C complete (page composites are wired to the spine).
**Exit gate:** all 12 Phase D tasks complete.

### `/v6/today` co-ownership matrix (CRITICAL serialization rule)

**Four tasks mutate `frontend/src/app/v6/today/page.tsx`**: C.17 (3-col hero + RecentSignalCalls), D.1 (DiffSinceYesterdayPanel), D.2 (BookAtAGlance), D.12 (drift_warn rollup chip in DiffPanel header). Per code-reviewer adversarial review fix #2, these MUST be co-owned by ONE implementer in a single batch — NOT dispatched in parallel. Implementer prompt for the today-page batch should bundle C.17 + D.1 + D.2 + D.12 acceptance criteria into a single brief.

### Task D.1 — DiffSinceYesterday panel on `/v6/today`
- **Goal**: FM-critic §1.1 critical gap #1 — "diff since yesterday" header strip.
- **Files**:
  - Create `frontend/src/components/v6/DiffSinceYesterdayPanel.tsx`
  - Create `frontend/src/components/v6/__tests__/DiffSinceYesterdayPanel.test.tsx`
  - Modify `frontend/src/app/v6/today/page.tsx` (add panel above 3-col hero) — **CO-OWNED with C.17, D.2, D.12**
- **Depends on**: B.4a (matrix diff), B.4b (book diff)
- **AFK / HITL**: AFK (but bundled with C.17/D.2/D.12 — single implementer)
- **Spec ref**: FM-critic §5 critical fix #3, §1.1
- **Acceptance**:
  - [ ] Header banner: "12 cells active today (+1 since yesterday) · 3 cells in drift_warn · 47 signal_calls overnight"
  - [ ] Two-column body: "New cells firing" / "Cells gone dormant"
  - [ ] Holdings flips section: list iids `held_iids_flipped` from B.4 with state-change badges
  - [ ] Empty-state microcopy: "No changes since yesterday's snapshot"
- **Tests**: 4 cases
- **Complexity**: M

### Task D.2 — "Your book at a glance" widget on `/v6/today`
- **Goal**: FM-critic §1.1 critical gap #2. Holdings count by state + biggest moves + names that flipped overnight.
- **Files**:
  - Create `frontend/src/components/v6/BookAtAGlance.tsx`
  - Create `frontend/src/components/v6/__tests__/BookAtAGlance.test.tsx`
  - Modify `frontend/src/app/v6/today/page.tsx`
- **Depends on**: B.1, B.4
- **AFK / HITL**: AFK
- **Spec ref**: FM-critic §1.1 critical gap #2, §5 critical fix #1
- **Acceptance**:
  - [ ] Card: "Your book: X POSITIVE · Y NEUTRAL · Z NEGATIVE · N flipped overnight"
  - [ ] Sub-list: top 5 biggest moves (by absolute return today)
  - [ ] CTA: "View calls you haven't acted on" → links to `/v6/screening?filter=unacted`
- **Tests**: 3 cases
- **Complexity**: M

### Task D.3 — `/v6/sectors` list extend with SectorBookStrip
- **Goal**: Add SectorBookStrip (B.7) above the 30-row ladder. RRGChart + BubbleRiskReturnChart from C.8.
- **Files**:
  - Modify `frontend/src/app/v6/sectors/page.tsx` (≤250 LOC)
  - Create `frontend/src/components/v6/SectorsList.tsx`
- **Depends on**: B.7, C.8
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §6.7, FM-critic §1.9 critical gap #1
- **Acceptance**:
  - [ ] SectorBookStrip rendered above RRG
  - [ ] RRGChart (all 30 sectors)
  - [ ] BubbleRiskReturnChart (sectors as bubbles, risk-X / relative-return-Y)
  - [ ] 30-row ladder with rank Δ, breadth %, vol regime σ, sector thesis bullets
  - [ ] 12-week rank trajectory sparkline per row (FM-critic §1.9 critical gap #2)
- **Tests**: smoke
- **Complexity**: M

### Task D.4 — `/v6/sectors/[name]` extend with SectorBookStrip + SectorBreadthPanel
- **Goal**: Sector detail page. Hero + SectorBookStrip (filtered to this sector) + SectorBreadthPanel + SectorBubbleChart + constituent table.
- **Files**:
  - Modify `frontend/src/app/v6/sectors/[name]/page.tsx` (≤250 LOC)
  - Create `frontend/src/components/v6/SectorDetailClient.tsx`
- **Depends on**: A, B.7, C.10 (SectorBreadthPanel)
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §6.8, FM-critic §1.10; Opus review §5 portfolio-awareness gap
- **Acceptance**:
  - [ ] Hero: sector name · current rank · ConvictionTape · action verb · sector thesis bullets
  - [ ] **Hero strip: "Your book in this sector: X% (vs N50 weight Y%) — OVERWEIGHT/UNDERWEIGHT chip"** (B.7 single-sector variant rendered as a thin hero band, not just buried below)
  - [ ] SectorBookStrip (single-sector variant)
  - [ ] SectorBreadthPanel
  - [ ] SectorBubbleChart filtered to constituents
  - [ ] Constituent table with column chooser + **PortfolioBadge column (default visible, compact variant rendered for each held iid)**
- **Tests**: smoke + portfolio-badge-renders-for-held-iid case
- **Complexity**: M

### Task D.5 — `/v6/funds` list extend + SwitchProposalsBanner
- **Goal**: Funds list page with IndustrySnapshot + Bubble + SignatureMatrix + ranked table. SWITCH proposals surfaced at top (FM-critic critical fix #5).
- **Files**:
  - Modify `frontend/src/app/v6/funds/page.tsx` (≤250 LOC)
  - Create `frontend/src/components/v6/FundsList.tsx`
  - Create `frontend/src/components/v6/SwitchProposalsBanner.tsx`
  - Create `frontend/src/lib/queries/v6/switch_proposals.ts`
  - Create `frontend/src/lib/queries/v6/__tests__/switch_proposals.test.ts`
- **Depends on**: A.0 (seed-data check), B.1, C.8, C.11, C.12
- **AFK / HITL**: AFK — `atlas_mf_switch_rules` exists in migration 085 (ground-truth check corrected the adversarial reviewers); A.0 confirms seed data is present
- **Spec ref**: design-application.md §6.5, FM-critic §1.6 critical gap #2, §5 critical fix #5, CONTEXT.md MF SWITCH rule; Opus review §5
- **Acceptance**:
  - [ ] SwitchProposalsBanner at top: "3 of your fund holdings should switch — click for proposals" (silent when zero)
  - [ ] `switch_proposals.ts` reads from the source confirmed in A.0 + cross-references B.1 holdings
  - [ ] SWITCH semantics: same-category, Q3/Q4 → Q1/Q2, ≥6mo, tie-break expense (per CONTEXT.md)
  - [ ] Default cols include **PortfolioBadge ("Held in N portfolios")** column (default visible) alongside name, category, AUM, expense_ratio, 3y CAGR, XIRR, peer-quartile, Atlas grade, 1w NAV, composite, sector-tilt (FM-critic §1.6 critical gap #1)
  - [ ] IndustrySnapshot (funds variant)
  - [ ] SignatureMatrix (funds variant)
  - [ ] BubbleRiskReturnChart (funds)
- **Tests**: smoke + switch_proposals.test.ts (4 cases) + portfolio-badge-renders-for-held-fund case
- **Complexity**: L

### Task D.6 — `/v6/funds/[code]` detail page + SWITCH proposal hero
- **Goal**: Fund detail page. Hero with SWITCH proposal (when Q3/Q4) + manager tenure + AUM trend. RankDecompositionCards + MultiBenchmarkRSWaterfall + 3y rolling Sharpe + Holdings tab + Audit tab.
- **Files**:
  - Create `frontend/src/app/v6/funds/[code]/page.tsx` (NEW route, ≤250 LOC)
  - Create `frontend/src/components/v6/FundDetailClient.tsx`
  - Create `frontend/src/components/v6/FundHero.tsx`
- **Depends on**: A, C.7, C.13, switch_proposals (D.5)
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §6.6, FM-critic §1.7 critical gaps #1+2+3; Opus review §5
- **Acceptance**:
  - [ ] Hero shows: grade · **PortfolioBadge expanded ("Held in N portfolios · X% aggregate book weight")** · SWITCH proposal banner (if Q3/Q4) · Manager + tenure · AUM + 3M flow sparkline · expense · exit load · thesis bullets
  - [ ] PortfolioBadge renders ONLY when `getHoldingState(fund_code)` returns non-null; silently absent otherwise
  - [ ] Overview tab: RankDecompositionCards + MultiBenchmarkRSWaterfall + 3y rolling Sharpe
  - [ ] Holdings tab: top-20 with each holding's Atlas verdict (LinkedTicker per row, edge case #8: "Not in Atlas universe" chip for non-universe holdings) + sector tilt bar + holdings-conviction histogram
  - [ ] Audit Trail tab (uses Phase E component; includes Section 4 — predicates met — promoted from v6.1 per Opus review §3)
  - [ ] Page shell `page.tsx` remains a thin wrapper around `FundDetailClient.tsx` (≤250 LOC route shell; all logic in client component)
- **Tests**: smoke + E2E + portfolio-badge-on-hero case
- **Complexity**: L

### Task D.7 — `/v6/etfs` list extend + ETF AMC leaderboard
- **Goal**: ETF list page. IndustrySnapshot (with AMC leaderboard variant for ETFs per FM-critic §1.5 critical gap #3) + Bubble + SignatureMatrix + table with TE/expense/bid-ask cols.
- **Files**:
  - Modify `frontend/src/app/v6/etfs/page.tsx` (≤250 LOC)
  - Create `frontend/src/components/v6/ETFsList.tsx`
- **Depends on**: A, C.8, C.11, C.12
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §6.5 (with override: AMC leaderboard applies to ETFs too — see Vocabulary lock), FM-critic §1.5 critical gaps #1+2+3; Opus review §5
- **Acceptance**:
  - [ ] Default cols: name, category, AUM, **expense_ratio**, **tracking_error** (index ETFs), Atlas grade, 1w return, 6m return, composite, top-3 holdings, **PortfolioBadge column (default visible)**
  - [ ] IndustrySnapshot ETF variant includes AMC leaderboard (per Vocabulary-lock override of design-lock §6.5)
  - [ ] Bubble + SignatureMatrix as in funds
- **Tests**: smoke + portfolio-badge-renders-for-held-etf case
- **Complexity**: M

### Task D.8 — `/v6/etfs/[iid]` detail page
- **Goal**: ETF detail page with TE/expense/bid-ask/premium-to-NAV hero metrics + RankDecompositionCards + Holdings + Audit.
- **Files**:
  - Create `frontend/src/app/v6/etfs/[iid]/page.tsx` (NEW route, ≤250 LOC)
  - Create `frontend/src/components/v6/ETFDetailClient.tsx`
  - Create `frontend/src/components/v6/ETFHero.tsx`
- **Depends on**: A, C.7, C.13
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §6.6, FM-critic §1.8 critical gaps #1+2+3; Opus review §5
- **Acceptance**:
  - [ ] Hero: grade · **PortfolioBadge expanded (when held in any portfolio)** · TE vs benchmark · expense · AUM + flow · bid-ask spread · premium-to-NAV (when applicable) · thesis bullets
  - [ ] PortfolioBadge silently absent when `getHoldingState(iid)` returns null
  - [ ] Overview / Holdings / Audit tabs (Audit tab includes Section 4 — predicates met)
  - [ ] Page shell `page.tsx` is a thin wrapper around `ETFDetailClient.tsx` (≤250 LOC)
- **Tests**: smoke + E2E + portfolio-badge case
- **Complexity**: M

### Task D.9 — `/regime` extend with deployment_multiplier hero
- **Goal**: FM-critic §5 critical fix #6. Make `deployment_multiplier` a hero number. Add days-in-regime + 5d flip probability. 4 input sparklines.
- **Files**:
  - Modify `frontend/src/app/regime/page.tsx` (≤250 LOC)
  - Create `frontend/src/components/v6/RegimeHero.tsx`
  - Create `frontend/src/components/v6/RegimeInputPanel.tsx`
  - Modify `frontend/src/lib/queries/v6/regime.ts` (add `getRegimeDetail`)
- **Depends on**: A
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §6.9, FM-critic §5 critical fix #6, §1.11
- **Acceptance**:
  - [ ] Hero numbers: regime label · **deployment_multiplier** (0.5x / 1.0x / 1.5x) · days_in_regime · 5d flip probability (read from `atlas_regime_daily` or compute from rolling Markov estimate; placeholder = `null` if not available, display "—")
  - [ ] Regime input panel: 4 sparklines for smallcap_rs_z, breadth_pct_above_200dma, vix_percentile, cross_sectional_dispersion
  - [ ] 12-week regime journey strip (colored timeline)
  - [ ] "Cells favored under this regime" clickable list
  - [ ] "What this regime means for cells / sectors / cap-tiers" structured table (FM-critic §1.11 critical gap #3)
- **Tests**: smoke
- **Complexity**: M

### Task D.10 — `/v6/cells/[cell_id]` cell detail page (FM-critic missing page #1)
- **Goal**: Spec the cell detail page that FM-critic flagged as HIGH severity missing. THE second most important page in v6 after `/matrix`.
- **Files**:
  - Create `frontend/src/app/v6/cells/[cell_id]/page.tsx` (NEW route, ≤250 LOC)
  - Create `frontend/src/components/v6/CellDetailClient.tsx`
  - Create `frontend/src/components/v6/CellHero.tsx`
  - Create `frontend/src/components/v6/CellRulePlainEnglish.tsx`
- **Depends on**: A.0 (ledger row-count check), A, C.1
- **AFK / HITL**: AFK — actual table is `atlas_ledger` (migration 083), NOT `atlas_ledger_public` (ground-truth check corrected the adversarial reviewers). C.1 ships `getCellById` — D.10 does NOT re-declare it.
- **Spec ref**: FM-critic §1.13 critical gap (page is undefined — this task defines it; FM-critic scope addition, not design-lock implementation); code-reviewer §C.1/D.10 clarification
- **Acceptance**:
  - [ ] `atlas_ledger` query confirmed in A.0; query joins on `signal_call_id`
  - [ ] Hero: cell name (e.g., "Mid 12m Pullback") · grade chip · IC · fric-adj · BH-FDR q · **predicted_excess sourced from `atlas_signal_calls` (latest ACTIVE per cell_id), NOT `atlas_cell_definitions`** · drift_status chip ({healthy / drift_warn / deprecated})
  - [ ] Section: rule_dsl rendered as plain English predicates (e.g., "Stock is in top decile of Mid-cap by trailing-60d traded value")
  - [ ] Section: all stocks firing this cell today (table with PortfolioBadge col + ConvictionTape col)
  - [ ] Section: 3-window backtest with per-window IC + sample size + excess curve sparkbar
  - [ ] Section: IC stability over time (rolling-12m IC line)
  - [ ] Section: friction-adjusted excess curve
  - [ ] Section: feature predicates each with "what this means" deterministic-translation
  - [ ] Section: last-N signal_calls fired with realized outcomes (joins `atlas_ledger` on `signal_call_id`)
  - [ ] Section: maintainer notes (read-only) + drift event log link
  - [ ] Page shell `page.tsx` is a thin wrapper around `CellDetailClient.tsx` (≤250 LOC)
- **Tests**: smoke + E2E
- **Complexity**: L

### Task D.11 — `/v6/screening` cross-universe screener (FM-critic missing page #2)
- **Goal**: Multi-criteria screener across stocks (v6 launch) — saveable queries deferred to v1.1.
- **Files**:
  - Create `frontend/src/app/v6/screening/page.tsx` (NEW route, ≤250 LOC)
  - Create `frontend/src/components/v6/ScreenerClient.tsx`
  - Create `frontend/src/components/v6/ScreenerFilterBuilder.tsx`
  - Create `frontend/src/lib/queries/v6/screen.ts`
  - Create `frontend/src/lib/queries/v6/__tests__/screen.test.ts`
- **Depends on**: A, B.1, C.6
- **AFK / HITL**: AFK
- **Spec ref**: FM-critic §1.14 critical gap (page is missing)
- **Acceptance**:
  - [ ] Filter builder: multi-criteria AND across columns (IC > X, sector rank ∈ top-N, drift_status = clean, RS percentile > X, in/not-in book, action verb, cap-tier)
  - [ ] Results table reuses StocksTableV6 with column chooser
  - [ ] URL-encoded query for shareability
  - [ ] Page shell ≤250 LOC
  - [ ] v6 launch scope: stocks only. Funds + ETFs in v6.1.
- **Tests**: smoke + 4 query-construction unit tests
- **Complexity**: L

### Task D.12 — `/v6/today` ConvictionTape header (drift_warn rollup chip)
- **Goal**: Cross-page drift_warn surfacing on the today page header. FM-critic §1.1 critical gap #3.
- **Files**:
  - Modify `frontend/src/components/v6/DiffSinceYesterdayPanel.tsx` (extend with drift_warn count) — **SERIAL after D.1 ships the base panel; CO-OWNED with C.17/D.1/D.2 batch**
  - Create `frontend/src/lib/queries/v6/drift_status_rollup.ts`
  - Create `frontend/src/lib/queries/v6/__tests__/drift_status_rollup.test.ts`
- **Depends on**: D.1 (SERIAL — D.12 extends a component D.1 creates)
- **AFK / HITL**: AFK (bundled in single-implementer today-page batch)
- **Spec ref**: FM-critic §1.1 critical gap #3, CONTEXT.md "Drift UI surface"; code-reviewer review §6 hidden conflict
- **Acceptance**:
  - [ ] Drift warn count rendered in the today header banner: "X cells in drift_warn" (using corrected enum literal `drift_warn`)
  - [ ] Click drills into a methodology-page section listing drift_warn cells
  - [ ] Query reads `SELECT COUNT(*) FROM atlas_cell_definitions WHERE drift_status = 'drift_warn'` (corrected literal)
- **Tests**: 2 cases
- **Complexity**: S

---

## Phase E — Audit trail + closed-loop methodology

**Prerequisites:** Phase D complete (since AuditTrailTab consumes data on every detail page).
**Exit gate:** all 4 Phase E tasks complete.

### Task E.1 — AuditTrailTab (6 sections — Section 4 promoted to v6.0 per Opus review; only Section 6 deferred to v6.1)
- **Goal**: 7-section provenance chain (6 sections in v6 launch). Used on stock / fund / ETF / cell detail pages. **Section 4 (Predicates met by this stock today) promoted back to v6.0 per Opus adversarial review §3** — the data is already loaded by C.1 (`atlas_cell_definitions.rule_dsl`) + C.3 (`atlas_scorecard_daily.features`); the section is a renderer over data already in hand, not net-new work.
- **Files**:
  - Create `frontend/src/components/v6/AuditTrailTab.tsx`
  - Create `frontend/src/components/v6/__tests__/AuditTrailTab.test.tsx`
- **Depends on**: C.1, C.3, C.4 (audit_trail query)
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §7.1, Opus adversarial review §3 (Section 4 promotion); eng-review decision #9 (Section 7 expanded by default)
- **Acceptance**:
  - [ ] Renders sections 1, 2, 3, **4** (NEW: predicates met), 5, 7 from C.1+C.3+C.4 data
  - [ ] Section 4 renders the cell's `rule_dsl.entry` predicate list, each predicate paired with the actual feature value from `atlas_scorecard_daily.features` for this iid + today's snapshot, with a green checkmark if the predicate is satisfied and a red x if not. Example row: `log_med_tv_60d = 16.92  ≥ 16.5 ✓` with deterministic translation `"Stock trades enough volume to be in the eligible Mid-cap pool"`
  - [ ] Section 6 renders a deferred-state notice: "Cross-rule consistency (top-5 ensemble) coming in v6.1" — the headline `CrossRuleDepth` metric DOES ship in v6.0 (on C.16 stock hero); only the audit-tab breakdown is deferred
  - [ ] Each section foldable; section 7 expanded by default
  - [ ] Every numeric has a `↳ ` deterministic-translation line (via A.6 InfoTooltip)
  - [ ] **v6.1 tracking**: leave a code comment `// V6_1_TODO: Section 6 (cross-rule ensemble breakdown) — see docs/TODOS.md` + open issue
- **Tests**: 8 cases (one per section + Section 4 predicate-pass + Section 4 predicate-fail + Section 6 deferred-state)
- **Complexity**: L

### Task E.2 — ClosedLoopDiagram (pre-split: layout + drawer)
- **Goal**: Closed-loop methodology diagram. Includes continuous-improvement + WTP + freeze-gate nodes per FM-critic §1.12 critical gap #1+3. **Pre-split into two files per code-reviewer review §14** — 12 nodes + drawer + 5 explainers in one component would bust 600 LOC.
- **Files**:
  - Create `frontend/src/components/v6/ClosedLoopDiagram.tsx` — SVG layout, node positions, animation, click handler
  - Create `frontend/src/components/v6/ClosedLoopNodeDrawer.tsx` — right-slide drawer with what-this-step-does + input/output tables + code-module ref + last 7 run timestamps + avg duration
  - Create `frontend/src/components/v6/__tests__/ClosedLoopDiagram.test.tsx`
  - Create `frontend/src/components/v6/__tests__/ClosedLoopNodeDrawer.test.tsx`
- **Depends on**: none
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §6.10 + §7.3, FM-critic §1.12 critical gaps #1+3, CONTEXT.md continuous-improvement workstream
- **Acceptance**:
  - [ ] SVG diagram per design-app §6.10 layout
  - [ ] Nodes (extended per FM-critic): Raw data · Daily feature compute · Cell-rule sweep (WF+FDR) · Scorecard · Top-1 + top-5 per cell · Daily conviction tape · Fund/ETF aggregation · Regime monitoring · **Continuous improvement** · **WTP gate** · **Methodology freeze gate** · Methodology re-validation
  - [ ] Each node clickable → right-slide drawer with what-this-step-does + input/output tables + code module ref + last 7 run timestamps + avg duration
  - [ ] Cadence badge per node (daily/weekly/monthly/quarterly color-coded)
  - [ ] Last-run timestamp from `atlas_provenance_log`
  - [ ] Animated flow respects `prefers-reduced-motion` (eng-review decision #7)
- **Tests**: 4 cases (all-nodes-render, reduced-motion respected, click→drawer, last-run-fallback)
- **Complexity**: L

### Task E.3 — `/methodology` extend with diagram + 5 explainers + drift-warn hero count
- **Goal**: Wire ClosedLoopDiagram + render the 5 explainers below + add drift-warn count to hero (FM-critic §1.12 critical gap #2).
- **Files**:
  - Modify `frontend/src/app/methodology/page.tsx` (≤250 LOC)
  - Create `frontend/src/components/v6/MethodologyClient.tsx`
  - Create `frontend/src/components/v6/WalkForwardExplainer.tsx`
  - Create `frontend/src/components/v6/RegimeClassifierExplainer.tsx`
  - Create `frontend/src/components/v6/BHFDRExplainer.tsx`
  - Create `frontend/src/components/v6/DriftDetectionExplainer.tsx`
  - Create `frontend/src/components/v6/PipelineStateTimeline.tsx`
- **Depends on**: E.2, D.12 (drift rollup)
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §6.10, FM-critic §1.12
- **Acceptance**:
  - [ ] ClosedLoopDiagram rendered as hero
  - [ ] Hero strip shows: "X cells under drift_warn · last retraining MMM-YYYY"
  - [ ] 5 explainer sections below
  - [ ] "What Atlas does NOT do" callout (FM-critic §1.12 medium gap #1)
  - [ ] Page shell ≤250 LOC
- **Tests**: smoke
- **Complexity**: M

### Task E.4 — Drift-warn chip propagation across all v6 detail pages
- **Goal**: CONTEXT.md "Drift UI surface — 24h propagation" requirement. Every detail page renders a `drift_warn` chip when the relevant cell is flagged.
- **Files**:
  - Create `frontend/src/components/v6/DriftWarnChip.tsx`
  - Create `frontend/src/components/v6/__tests__/DriftWarnChip.test.tsx`
  - Modify `frontend/src/components/v6/StockHero.tsx`, `FundHero.tsx`, `ETFHero.tsx`, `CellHero.tsx` to render the chip
  - Modify `frontend/src/components/v6/CellMatrix.tsx` (overlaps with C.14 — see depends-on)
- **Depends on**: C.1 (cells query exposes `drift_status`), **C.14 (CellMatrix tile chip rendering — code-reviewer review §M11 added dep)**, D.6, D.8, D.10 (so the *Hero components exist)
- **AFK / HITL**: AFK
- **Spec ref**: CONTEXT.md "Drift UI surface (24h propagation — option B5a)", eng-review edge case #10; code-reviewer §M11
- **Acceptance**:
  - [ ] Chip renders only when `drift_status = 'drift_warn'` (corrected enum literal)
  - [ ] Variant treatment: "⚠ Drift flagged · maintainer reviewing"
  - [ ] InfoTooltip: "This cell's realized excess is diverging from its locked prediction. Methodology team is reviewing. Position remains open; no automatic action."
  - [ ] Wired on stock detail, fund detail, ETF detail, cell detail, matrix tile
- **Tests**: 3 cases (warn-renders, clean-no-render, tooltip)
- **Complexity**: S

---

## Phase F — QA + ship

**Prerequisites:** Phases A-E complete.
**Exit gate:** all 7 Phase F tasks complete; deploy verified on `atlas.jslwealth.in`.

### Task F.1 — E2E suite (3 fund-manager critical paths)
- **Goal**: Playwright E2E tests covering the FM storyboard's 3 critical paths.
- **Files**:
  - Create `frontend/tests/e2e/fund_manager_flow.spec.ts` (Path A: today→top conviction→stock detail→Audit)
  - Create `frontend/tests/e2e/matrix_drilldown.spec.ts` (Path B: matrix→cell→stock)
  - Create `frontend/tests/e2e/fund_holdings_drilldown.spec.ts` (Path C: funds→fund detail→holding→stock)
  - Create `frontend/tests/e2e/tenure_toggle_persistence.spec.ts` (URL+LS persistence)
  - Create `frontend/playwright.config.ts` (if absent)
- **Depends on**: all Phases A-E
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §9 storyboard, eng-review §6
- **Acceptance**:
  - [ ] 3 critical paths pass headless on CI
  - [ ] Tenure toggle URL+LS roundtrip verified
  - [ ] Test runs in <3min on CI
- **Tests**: the tests themselves
- **Complexity**: L

### Task F.2 — Accessibility scan (axe-core on every v6 page)
- **Goal**: a11y CI gate — axe-core scan with zero serious violations.
- **Files**:
  - Create `frontend/tests/e2e/a11y.spec.ts`
- **Depends on**: F.1 config
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §11
- **Acceptance**:
  - [ ] axe-core scan on each of 14 v6 routes
  - [ ] Zero serious/critical violations
  - [ ] Failures block PR
- **Tests**: the test itself
- **Complexity**: M

### Task F.3 — Performance budget verification
- **Goal**: Validate eng-review §5 budgets on Indian latency. TTFB ≤800ms p95, LCP ≤1.5s p95, bundle ≤350KB gzipped per page.
- **Files**:
  - Create `frontend/tests/perf/lighthouse_budgets.spec.ts` (or use existing /benchmark skill)
- **Depends on**: F.1
- **AFK / HITL**: HITL (requires manual verification on real Indian latency — coordinate with deployer)
- **Spec ref**: eng-review §5
- **Acceptance**:
  - [ ] Lighthouse budgets pass on `/v6/today`, `/v6/stocks`, `/matrix`, `/v6/stocks/[iid]`
  - [ ] Bundle audit run: `npm run build && npx next-bundle-analyzer`
  - [ ] D3 imports tree-shaken (no full `import * as d3`)
  - [ ] Report posted to PR
- **Tests**: lighthouse runs
- **Complexity**: M

### Task F.4 — Voice + Indian-format audit
- **Goal**: Sweep every v6 page for DESIGN.md voice violations + Indian number-format compliance.
- **Files**:
  - Audit pass; modifications to whichever component strings violate
- **Depends on**: all C+D+E
- **AFK / HITL**: AFK
- **Spec ref**: design-application.md §10, §13 acceptance
- **Acceptance**:
  - [ ] No banned words (explore/discover/unleash/supercharge/elevate/journey/dive in)
  - [ ] All numbers use `Intl.NumberFormat('en-IN')` (lakh/crore)
  - [ ] All percentages have +/- prefix where signed
  - [ ] All dates DD-MMM-YYYY, IST timezone
  - [ ] No emoji anywhere (CSV grep: `grep -rn '[\\u{1F600}-\\u{1F64F}]' frontend/src/`)
- **Tests**: lint-style script `scripts/voice_audit.ts`
- **Complexity**: S

### Task F.5 — `/codex review` + `/review`
- **Goal**: Pre-merge code review per project skill cadence.
- **Files**: n/a — review output
- **Depends on**: all C+D+E
- **AFK / HITL**: HITL (codex review iteration with human gate)
- **Spec ref**: CLAUDE.md skill cadence "Pre-merge"
- **Acceptance**:
  - [ ] `/review` skill run; findings addressed
  - [ ] `/codex review` skill run; findings addressed (or explicit override documented)
- **Tests**: n/a
- **Complexity**: M

### Task F.6 — `/design-review` polish pass (skill loop process)
- **Goal**: FM-critic + design-review iteration per `feedback_skill_loop_process.md` user memory.
- **Files**: n/a — design-review output + small fixes
- **Depends on**: F.5
- **AFK / HITL**: HITL (review iteration loop)
- **Spec ref**: user memory `feedback_skill_loop_process.md`
- **Acceptance**:
  - [ ] `/design-review` skill run on staged build
  - [ ] Findings batched + addressed
  - [ ] fund-manager-critic agent re-run for sign-off (§13 last criterion)
- **Tests**: n/a
- **Complexity**: M

### Task F.7 — Deploy to `atlas.jslwealth.in` + canary
- **Goal**: Ship to production EC2 via `/ship` then `/land-and-deploy`. Canary post-deploy.
- **Files**:
  - `git push` triggers deploy hook; verify via `/canary`
- **Depends on**: F.1, F.2, F.3, F.4, F.5, F.6
- **AFK / HITL**: AFK (`/ship` + `/land-and-deploy` are automated; canary is automated; the manual step is the final go-no-go after canary clears)
- **Spec ref**: CLAUDE.md skill cadence "Ship"
- **Acceptance**:
  - [ ] PR merged via `/ship`
  - [ ] EC2 deploy: `git pull && npm run build && pm2 restart atlas-frontend` (per user memory `reference_atlas_frontend_host.md`)
  - [ ] `/canary` clean post-deploy
  - [ ] `/v6/today` loads under 2s p95 from a real client
- **Tests**: canary
- **Complexity**: M

---

## v6.1 deferred (tracked, NOT in scope)

- AuditTrailTab sections 4 (predicates met) + 6 (cross-rule consistency check) — deferred per eng-review decision #3
- `atlas_brief_cache` LLM brief integration on detail pages (eng-review decision #4)
- Mobile responsive polish (CEO-accepted-risk O2)
- Customizable dashboards / saved views (design-app §14)
- Watchlist (design-app §14)
- Notifications / alerts on portfolio flips (FM-critic §2 weakness #9 — pencilled as v6.1)
- Conviction-tape history (30d evolution) on stock detail
- ETF / fund holding-overlap pairwise analysis
- Cross-universe screener for funds + ETFs (v6 launch ships stocks only)
- Methodology version-diff viewer
- Pair-trade idea callout on sector detail
- Earnings calendar overlay
- News / corp-action stream per instrument

**Tracking location**: `docs/TODOS.md` — open an issue per item per CLAUDE.md issue-tracker convention. Each deferred item references this plan's task number.

---

## Risk register (top 3 from eng-review + 1 from FM-critic)

1. **Shared primitives not built first → refactor wave.** Phase A is gated SERIAL before any other phase. Implementer prompts must enforce this gate.
2. **AuditTrailTab data layer is the heaviest single query.** C.4 must precede E.1. Sections 4 + 6 deferred to keep v6 launch shipable.
3. **Performance budget on `/v6/stocks` list page.** Mitigations encoded in C.15: virtualize >300 rows, lazy-load BubbleRiskReturnChart, measure on real Indian latency in F.3.
4. **Portfolio-awareness wiring is cross-cutting (FM-critic risk).** Phase B lands the primitives BEFORE Phase C page composites so every page wires them once. If Phase B slips, Phase C accepts a stub `getHeldIidSet() = new Set()` and Phase D backfills the real wire-up.

---

## Spec coverage check (self-review)

Each design-application.md section maps to plan tasks:

| Design-app section | Covered by |
|---|---|
| §1 three-layer pattern | C.6, C.16, D.10 (every hero) |
| §2 Bubble chart standard | C.8 |
| §3.1 Temporal toggle | A.1 |
| §3.2 Benchmark toggle | A.2 |
| §3.3 Column chooser | A.3 |
| §3.4 Short-horizon return cols | C.15, C.16 |
| §4 19-archetype thesis registry | A.4, C.6 |
| §5 Component inventory | C.6-C.13, B.6-B.8, E.1, E.2 |
| §6.1 `/matrix` | C.14 |
| §6.2 `/v6/today` | C.17, D.1, D.2, D.12 |
| §6.3 `/v6/stocks` | C.15 |
| §6.4 `/v6/stocks/[iid]` | C.16, E.1 |
| §6.5 `/v6/etfs` list, `/v6/funds` list | D.5, D.7 |
| §6.6 fund + ETF detail | D.6, D.8 |
| §6.7 `/v6/sectors` | D.3 |
| §6.8 `/v6/sectors/[name]` | D.4 |
| §6.9 `/regime` | D.9 |
| §6.10 `/methodology` | E.3 |
| §7.1 AuditTrailTab | E.1 |
| §7.2 MultiBenchmarkRSWaterfall | C.7 |
| §7.3 ClosedLoopDiagram | E.2 |
| §7.4 SectorBreadthPanel | C.10 |
| §7.5 BubbleRiskReturnChart | C.8 |
| §8 Interaction state coverage | A.5, A.9 |
| §9 Fund-manager flow | F.1 |
| §10 Voice rules | F.4 |
| §11 Accessibility | F.2 |
| §12 Responsive | v6.1 deferred (mobile polish) |
| §13 Per-page acceptance | F.6 |
| §14 NOT in scope | v6.1 deferred list above |
| §15 Reuse | C.8 (lift StockBubbleChart), C.16 (RRG, DwellTimeline, OBV, ATR, WithinStatePeers, HitRateRow) |

FM-critic §5 critical fixes (6 of 6 covered):
1. Portfolio-awareness layer — B.1-B.8, C.14, C.15, C.16, D.3-D.7
2. Position-sizing widget — B.5, B.8, C.16
3. Diff since yesterday — B.4, D.1
4. `/v6/cells/[cell_id]` page — D.10
5. SWITCH proposals on fund pages — D.5, D.6
6. `deployment_multiplier` hero on `/regime` — D.9

FM-critic missing pages (2 of 2 covered):
- `/v6/cells/[cell_id]` — D.10
- `/v6/screening` — D.11

CONTEXT.md additions (post-2026-05-24) covered:
- Cell state vocabulary POSITIVE/NEUTRAL/NEGATIVE + ownership-aware display labels — A.4
- Drift UI 24h propagation — E.4, C.14
- Methodology freeze gate node — E.2
- Continuous-improvement node — E.2
- WTP gate node — E.2
- Named secondary maintainer — out of frontend scope (compliance binder)

---

## Task count summary (post-adversarial reconciliation + ground-truth check)

| Phase | Tasks | AFK | HITL | Complexity (S/M/L) |
|---|---|---|---|---|
| A — shared primitives + data pre-flight + decimal utility | **11** | 11 | 0 | 7S / 3M / 1L |
| B — portfolio awareness (B.4 split into B.4a + B.4b) | **9** | 9 | 0 | 1S / 7M / 1L |
| C — page composites + queries | 17 | 17 | 0 | 1S / 9M / 7L |
| D — FM-critic fixes + missing pages | 12 | 12 | 0 | 1S / 6M / 5L |
| E — audit trail + methodology | 4 | 4 | 0 | 1S / 1M / 2L |
| F — QA + ship | 7 | 5 | 2 | 1S / 4M / 2L |
| **Total** | **60** | **58** | **2** | — |

**Ground-truth correction**: The two adversarial reviewers between them flagged ~7 tasks as HITL pending Nimish decisions. A ground-truth scan of `migrations/versions/` 2026-05-26 found that 4 of those decisions resolve autonomously to the obvious technical default (the migration scan made the trade-off one-sided, not subjective). Net HITL split is 2, not 8. The remaining 2:
- **F.3** — Performance measurement on real Indian latency (irreducibly HITL — needs Bhavin or similar real-network user)
- **F.6** — `/design-review` polish iteration (judgement call; could be co-owned with a design lead)

B.5 (sizing formula) is AFK-with-escalation: implementer greps for v2 `computeSizing`. If exactly one canonical implementation surfaces, port it. If multiple inconsistent OR zero matches, escalate.

**Recommended next step**: Dispatch the Phase A AFK tasks in parallel — A.1, A.2, A.3, A.4, A.6, A.7, A.8, A.10 are all independent and can run as concurrent implementer subagents. A.0 (data pre-flight) should land first to validate the autonomous data-source resolutions; A.5 + A.9 are skeleton/Suspense tasks that consume the rest. After Phase A green, Phase B in parallel (B.1, B.2, B.3, B.5, B.4a, B.4b independent; B.6/B.7/B.8 follow). Phase C in parallel after Phase B. Bundle the today-page batch (C.17 + D.1 + D.2 + D.12) into one implementer per the co-ownership matrix.
