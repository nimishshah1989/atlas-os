# Agent Prompts for Sprint 2, 3, 4 Planning

Paste each section below into a new Claude Code session to have that agent run the full
CEO → Design → Engineering review pipeline and produce the implementation plan for that sprint.
Each prompt is self-contained. Make sure Sprint 1 has merged to main before spawning Sprint 2.
Sprints 3 and 4 can start immediately — they don't depend on Sprint 2.

---

## SPRINT 2 AGENT PROMPT

```
You are starting a new planning session for the Atlas OS project. Your job is to produce a complete
implementation plan for Sprint 2 (Stocks + ETF Page Upgrade) of the Atlas Intelligence Platform.

## Context you MUST read before planning

1. Full spec: docs/superpowers/specs/2026-05-10-atlas-intelligence-platform-design.md
   - Sections 1–14 cover the full product vision and component anatomy
   - Section 15: Accessibility/Responsive conventions
   - Sprint 2 task list is at line ~676 under "### Sprint 2 — Stocks + ETF Page Upgrade"

2. CEO Plan (scope decisions already made): ~/.gstack/projects/atlas-os/ceo-plans/2026-05-10-atlas-intelligence-platform.md

3. Sprint 1 plan (foundation already built/building): docs/superpowers/plans/2026-05-10-sprint-1-design-system.md
   Sprint 1 has already built or is building:
   - lib/state-segment-utils.ts (buildSegments utility)
   - lib/chart-colors.ts (CHART_COLORS, bubbleColor, rsStateColor)
   - lib/screener-utils.ts (stateRank, matchesSearch, buildSortKey)
   - lib/url-params.ts (validatePeriod, validateBenchmark)
   - lib/commentary/stocks.ts (buildStocksCommentary)
   - components/ui/StateValuePair.tsx
   - components/ui/MetricTooltip.tsx (METRIC_DEFINITIONS)
   - components/ui/CommentaryBlock.tsx
   - Migration 026 (state_since_date DATE on atlas_stock_states_daily)
   All of these are available for Sprint 2 to import — do NOT re-implement them.

4. Key existing files Sprint 2 will modify:
   - frontend/src/lib/queries/stocks.ts — getAllStocks() will need state_since_date column added
   - frontend/src/components/stocks/StockScreener.tsx — add new columns, show/hide, expandable row
   - frontend/src/app/stocks/page.tsx — wire CommentaryBlock, intelligence panel

5. Key architectural decisions (non-negotiable, already decided):
   - days_in_state reads s.state_since_date (Migration 026) — NO CTE fallback
   - Column show/hide persists in localStorage key "atlas-column-prefs-stocks" / "atlas-column-prefs-etfs"
   - Expandable screener row: 300ms debounce before firing /api/states-compact fetch; cancel on collapse
   - ETF screener follows IDENTICAL pattern to stocks screener (same columns, same expandable row)
   - buildCommentary aggregates come from the same Band 1 page query — NO second DB round-trip
   - Metric tiles are Band 1, StateJourneyTimeline compact variant is inside Band 2 expandable row

6. Tech stack: Next.js 14 App Router, TypeScript, Tailwind CSS, Recharts, Radix UI, Vitest + @testing-library/react

## Your task

Run the following skills IN ORDER, making ALL decisions autonomously (pick recommended options, do not ask for user input):

1. /plan-ceo-review — review Sprint 2 scope against the CEO plan
2. /plan-design-review — run the full 7-pass visual audit on Sprint 2 components
3. /plan-eng-review — run the full architecture + quality + performance review

After all three reviews complete (with all recommended options accepted), invoke:
4. /superpowers:writing-plans — write the Sprint 2 implementation plan

Save the plan to: docs/superpowers/plans/2026-05-10-sprint-2-stocks-etf-upgrade.md

The plan must cover:
- Stocks screener: 8 new columns (ret_1w, ret_6m, vol_63, extension, drawdown, gold_rs, days_in_state, gates/weinstein)
- Stocks screener: column show/hide UI (settings popover, localStorage persistence)
- Stocks screener: sector filter dropdown
- Stocks screener: StateValuePair on all state chip columns
- Stocks screener: expandable row with compact StateJourneyTimeline (90D, 4 lanes)
- /api/states-compact route (new API endpoint)
- Stocks intelligence panel (Band 1): RS state distribution bars, momentum distribution, investable count card
- Stocks CommentaryBlock wire-up (uses buildStocksCommentary from Sprint 1)
- getAllStocks() query update: add state_since_date to SELECT, compute days_in_state
- ETF screener: same upgrades as stocks (parallel implementation)
- ETF getAllETFs() or equivalent query with state_since_date
- ETF CommentaryBlock (build buildETFCommentary condition array + full test coverage)
- Metric tiles (Band 1) full implementation for both pages
- Full test coverage: every new hook/util tested, commentary condition branches all tested

Optimize all decisions for a fund manager's daily workflow: high information density, zero ambiguity in signals, fast page loads, mobile-readable screener on 1280px+ displays.
```

---

## SPRINT 3 AGENT PROMPT

```
You are starting a new planning session for the Atlas OS project. Your job is to produce a complete
implementation plan for Sprint 3 (Sectors Page Upgrade) of the Atlas Intelligence Platform.

## Context you MUST read before planning

1. Full spec: docs/superpowers/specs/2026-05-10-atlas-intelligence-platform-design.md
   - Sections 1–14 (especially Section 6: Sectors Page anatomy)
   - Section 15: Accessibility conventions
   - Sprint 3 task list is at line ~690 under "### Sprint 3 — Sectors Page Upgrade"

2. CEO Plan: ~/.gstack/projects/atlas-os/ceo-plans/2026-05-10-atlas-intelligence-platform.md

3. Sprint 1 plan (foundation built): docs/superpowers/plans/2026-05-10-sprint-1-design-system.md
   Sprint 1 utilities available for Sprint 3 to import:
   - lib/state-segment-utils.ts (buildSegments)
   - lib/chart-colors.ts (CHART_COLORS, rsStateColor)
   - lib/screener-utils.ts
   - components/ui/StateValuePair.tsx
   - components/ui/MetricTooltip.tsx
   - components/ui/CommentaryBlock.tsx

4. Key existing files Sprint 3 will modify/extend:
   - frontend/src/app/sectors/ — current sectors page structure
   - frontend/src/components/sectors/ — existing sector components
   - frontend/src/lib/queries/sector-deep-dive.ts — existing sector query
   - frontend/src/lib/sectors-decision.ts — existing sector decision logic

5. Key architectural decisions for Sprint 3 (non-negotiable):
   - RRG X-axis = bottomup_rs_3m_nifty500 (already in DB)
   - RRG Y-axis = rs_momentum = self-join on atlas_sector_metrics_daily at T vs T-20. Computed as CTE inside the sectors query — NOT a separate endpoint. NOT stored in DB.
   - RRGChart uses D3 (NOT Recharts) — it is a genuine scatter with quadrant labels and trailing history dots
   - BreadthWaterfall uses D3 or Recharts BarChart — assess which fits better during planning
   - Tab navigation: Rotation Matrix / Decision Table / State History / RRG (4 tabs)
   - StateTransitionCard sits ABOVE tabs, always visible
   - Sector deep dive URL: /sectors/[sector_slug] (verify slug pattern matches existing routes)
   - Sector CommentaryBlock follows same condition-array pattern as stocks

6. Tech stack: Next.js 14 App Router, TypeScript, Tailwind CSS, D3 (for RRG and Waterfall), Recharts (for simpler charts), Vitest + @testing-library/react

## Your task

Run the following skills IN ORDER, making ALL decisions autonomously (pick recommended options, do not ask for user input):

1. /plan-ceo-review — review Sprint 3 scope against the CEO plan
2. /plan-design-review — run the full 7-pass visual audit on Sprint 3 components (RRG is the focal new component)
3. /plan-eng-review — architecture + quality + performance review (focus: RRG Y-axis CTE performance, D3 SSR concerns)

After all three reviews complete, invoke:
4. /superpowers:writing-plans — write the Sprint 3 implementation plan

Save the plan to: docs/superpowers/plans/2026-05-10-sprint-3-sectors-upgrade.md

The plan must cover:
- Sectors page tab navigation (4 tabs) + tab URL state (?tab=rrg)
- StateTransitionCard component (above tabs, always visible)
- RRGChart component in D3: quadrant labels (Leading/Weakening/Lagging/Improving), trailing dots (T-4 to T-0), click → sector deep dive
- RRG data query: sectors query extended with rs_momentum CTE (T vs T-20 self-join)
- BreadthWaterfall component: % stocks in each RS state over time, event annotations (regime change markers)
- Sector decision table: upgrade to use StateValuePair, new columns, ENTER hover popover with entry criteria
- State history tab: range selector (1M/3M/6M/1Y), StateTimeline using buildSegments
- Sector deep dive page: reconciliation panel + breadth waterfall
- Sector CommentaryBlock: buildSectorCommentary condition array + full branch test coverage
- URL param validation for sector pages (?tab, ?sector, ?period)

Optimize all decisions for fund manager rotation analysis: the RRG must be immediately readable at a glance — quadrant labels prominent, dot trails clearly showing momentum direction, sector names visible without hover.
```

---

## SPRINT 4 AGENT PROMPT

```
You are starting a new planning session for the Atlas OS project. Your job is to produce a complete
implementation plan for Sprint 4 (Funds Page) of the Atlas Intelligence Platform.

## Context you MUST read before planning

1. Full spec: docs/superpowers/specs/2026-05-10-atlas-intelligence-platform-design.md
   - Sections 1–14 (especially Section 7: Funds Page anatomy)
   - Section 15: Accessibility conventions
   - Sprint 4 task list is at line ~702 under "### Sprint 4 — Funds Page"

2. CEO Plan: ~/.gstack/projects/atlas-os/ceo-plans/2026-05-10-atlas-intelligence-platform.md

3. Sprint 1 plan (foundation built): docs/superpowers/plans/2026-05-10-sprint-1-design-system.md
   Sprint 1 utilities available for Sprint 4:
   - lib/chart-colors.ts (CHART_COLORS, bubbleColor)
   - lib/screener-utils.ts
   - lib/url-params.ts
   - components/ui/StateValuePair.tsx
   - components/ui/MetricTooltip.tsx
   - components/ui/CommentaryBlock.tsx

4. Key existing DB tables for funds:
   - atlas.atlas_universe_funds — fund master (check if mstar_id column is populated — if not, use scheme_name slug as fallback route key)
   - atlas.atlas_fund_metrics_daily — fund metrics
   - atlas.atlas_fund_states_daily — fund states (Recommended/Hold/Reduce/Exit)
   - atlas.atlas_fund_decisions_daily — fund investability decisions

5. Key architectural decisions for Sprint 4 (non-negotiable):
   - Fund deep dive URL key: /funds/[mstar_id] IF mstar_id is populated; otherwise /funds/[scheme_slug]
   - MUST verify mstar_id population BEFORE writing the plan (this is the Sprint 4 pre-flight check)
   - Funds bubble chart: X = 3-year volatility, Y = 3-year return, Z = AUM (log-normalized). Use Recharts ScatterChart (same pattern as stocks bubble chart, NOT D3).
   - Fund CommentaryBlock: condition array pattern same as stocks. Fund-specific signals: 3L score (alpha, drawdown, AUM trend), fund category leadership.
   - 3-lens view in deep dive: Performance (3Y return, Sharpe, drawdown), Portfolio (holdings alignment), Management (AUM trend, category rank)
   - Fund states are: Recommended / Hold / Reduce / Exit (4-level, unlike stocks 7-level RS)
   - No separate ETF funds — only mutual funds in this sprint

6. Critical pre-flight (do this before writing the plan):
   Run this query via the existing DB connection pattern to verify mstar_id:
   Check frontend/src/lib/queries/ for existing fund query files and run a count of non-null mstar_id values.
   Decision: if >50% populated → use mstar_id as route key. If <50% → use scheme_name slug.

7. Tech stack: Next.js 14 App Router, TypeScript, Tailwind CSS, Recharts (bubble chart), Vitest + @testing-library/react

## Your task

Run the following skills IN ORDER, making ALL decisions autonomously (pick recommended options, do not ask for user input):

1. /plan-ceo-review — review Sprint 4 scope (funds page is net-new, no existing page to upgrade)
2. /plan-design-review — 7-pass visual audit. Focus: 3-lens view layout, fund bubble chart, decision history timeline
3. /plan-eng-review — architecture review (focus: route key decision (mstar_id vs slug), query layer for 4 fund tables, CommentaryBlock data flow)

After all three reviews complete, invoke:
4. /superpowers:writing-plans — write the Sprint 4 implementation plan

Save the plan to: docs/superpowers/plans/2026-05-10-sprint-4-funds-page.md

The plan must cover:
- Pre-flight: mstar_id population check → route key decision documented in plan
- Funds page shell: 4 bands (Band 1 metric tiles, Band 2 screener, Band 3 forward return, Band 4 top picks)
- Funds screener: fund name, category, state (4-level), 1Y/3Y return, Sharpe, drawdown, AUM, RS vs category
- Column show/hide (localStorage atlas-column-prefs-funds)
- Funds bubble chart (Recharts ScatterChart: 3Y vol vs 3Y return, Z=AUM)
- Fund deep dive page: 3-lens view, decision history timeline, StateJourneyTimeline (fund state over time)
- Fund CommentaryBlock: buildFundCommentary condition array + full branch test coverage
- getAllFunds() query: 4-table JOIN with latest date CTE
- URL param validation for fund pages
- Fund API routes if needed for deep dive data

Optimize all decisions for fund manager due diligence: the 3-lens view is the core value — it must give a fund manager everything needed to make a hold/exit/add decision without switching tabs or opening another tool.
```

---

## Notes for parallel execution

- Sprint 3 and Sprint 4 can start immediately in parallel — they don't depend on Sprint 2
- Sprint 2 SHOULD wait for Sprint 1 to merge (it imports StateValuePair, screener-utils, etc.)
- Each agent works on its own branch: feat/sprint-2-stocks-etf, feat/sprint-3-sectors, feat/sprint-4-funds
- Merge order after all three complete: Sprint 2 → Sprint 3 → Sprint 4 (one at a time, review between)
