# M15 Phase 2 — Read-only Strategies UI: Approach

## Data scale
- strategy_configs: 15 rows (tiny; any fetch pattern works)
- strategy_backtest_results: O(15-150) rows initially; reads with strategy_id WHERE clause
- strategy_paper_performance: O(0) rows today (paper trader not yet live); table empty
- strategy_paper_trades: O(0) rows today; table empty

All reads are tiny; postgres.js direct queries are correct.

## Chosen approach
- Queries lib: server-only postgres.js tagged template literals, exact column names from migrations
- NUMERIC columns returned as `string` (postgres.js default) — parsed at display time
- Pages: RSC shells (≤250 LOC) + client islands for interactivity
- Charts: inline client components per route folder (not shared charts/) per spec
- KPICard: shared component at `frontend/src/components/strategy/KPICard.tsx`
- Filters: URL-param backed, client island `StrategiesView.tsx`

## Wiki patterns checked
- Decimal Not Float (NUMERIC as string, parse at display time) — confirmed
- PRD Golden Example Testing — chart components get empty-state + data tests

## Existing code being reused
- `frontend/src/lib/db.ts` — postgres.js singleton
- `frontend/src/components/regime/IndicatorChart.tsx` — Recharts wiring + hex colors
- `frontend/src/app/admin/policies/page.tsx` — RSC shell pattern
- `frontend/src/components/nav/TopNav.tsx` — nav link pattern

## Edge cases
- Empty paper_performance: EquityCurveChart falls back to placeholder text
- NULL regime_breakdown in backtest: RegimeBreakdownChart shows empty state
- NULL sharpe_ratio: KPICard renders "—"
- No backtests for strategy: KPI section shows "—" for all backtest metrics
- paper_active logic: JOIN strategy_paper_portfolios; ANY rows → active

## File LOC estimates (all under limits)
- queries/strategies.ts: ~70 LOC
- queries/backtests.ts: ~50 LOC  
- queries/paper_perf.ts: ~60 LOC
- components/strategy/KPICard.tsx: ~50 LOC
- app/strategies/[id]/EquityCurveChart.tsx: ~100 LOC
- app/strategies/[id]/DrawdownChart.tsx: ~80 LOC
- app/strategies/[id]/RegimeBreakdownChart.tsx: ~80 LOC
- app/strategies/[id]/ConfigJSONViewer.tsx: ~100 LOC
- app/strategies/page.tsx: ~60 LOC (shell)
- app/strategies/StrategiesView.tsx: ~180 LOC
- app/strategies/[id]/page.tsx: ~120 LOC (shell)

## Expected runtime
All reads are tiny (< 200 rows). No performance concerns. Sub-100ms on t3.large.
