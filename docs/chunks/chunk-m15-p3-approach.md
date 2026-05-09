# M15 Phase 3 Approach — /portfolios + Static Builder

**Date:** 2026-05-10
**Branch:** feat/m15-simulation-frontend

## Data scale

No DB query possible from Mac (psycopg2 broken, EC2 is the working path).
Based on migration review:
- atlas_universe_stocks: ~750 rows (PRD states "750 stocks max")
- atlas_universe_etfs: ~100 rows
- atlas_universe_funds: ~592 rows
- strategy_fm_custom_portfolios: 0 rows (new table, migration 020)
- strategy_configs WHERE is_fm_authored=TRUE: 0 rows (migration 025 just added column)
- strategy_backtest_results: small, backtest data not yet populated

All tables are small (<1K rows). Any query approach works; direct SQL is cleanest.

## Approach

### Queries (portfolios.ts, instruments.ts)
- Direct postgres.js tagged-template queries, same pattern as strategies.ts
- NUMERIC stays as string (::text casts)
- Import 'server-only' at top of each file
- Filters passed as nullable params with IS NULL coalesce guards (same pattern as getAllStrategies)
- LIMIT 100 default on instrument pickers (spec says "30-100 names by default")

### Server Actions (actions.ts)
- 'use server' file with only async function exports
- callInternalApi = triggerRecompute pattern from internal-api.ts
- Extend internal-api.ts with a generic callInternalApi helper
- Validation inline: name non-empty, instruments not empty, weights sum ~100 (±0.5)
- revalidatePath('/portfolios') on success

### Chart dedup
- Move EquityCurveChart.tsx + DrawdownChart.tsx from
  frontend/src/app/strategies/[id]/ to frontend/src/components/charts/
- Update strategies/[id]/page.tsx imports
- Both files reference @/lib/queries/paper_perf.PaperPerfRow — type still works

### Pages
- /portfolios/page.tsx: RSC, ≤250 LOC shell, logic in PortfoliosView client island
- /portfolios/[id]/page.tsx: RSC, ≤250 LOC shell, branches on portfolio type
- /portfolios/new/page.tsx: RSC, ≤250 LOC shell, Static tab built + Rule-Based placeholder

### Components
- InstrumentPicker.tsx: client island, URL-backed filter state, no react-window (750 rows max, CSS overflow is fine)
- WeightTable.tsx: client island, equal-weight default, sum indicator, normalize button

### Tests
- Vitest, jsdom env (existing pattern)
- Mock @/lib/db and next/cache (existing pattern)
- Mock 'server-only' implicit (vitest config handles it via module resolution)

## Wiki patterns checked
- Idempotent Upsert: not needed (using FastAPI write path)
- Decimal Not Float: N/A (frontend display only, NUMERIC as string)
- Dashboard-Backend Name Drift: instrument counts come from query, not hardcoded

## Edge cases
- Empty portfolio list: "No portfolios yet" + CTA
- NULL sharpe: display as "—"
- paper_trading_active=TRUE but no backtest: CHECK constraint in migration prevents this
- Rule-based portfolios: query strategy_configs WHERE is_fm_authored=TRUE
- instruments JSONB in custom_portfolios: type is Array<{instrument_id, instrument_type, weight_pct}>
- Type routing on /portfolios/[id]: check fm_custom_portfolios first, then strategy_configs

## Files in scope
- frontend/src/lib/queries/portfolios.ts (NEW)
- frontend/src/lib/queries/instruments.ts (NEW)
- frontend/src/lib/internal-api.ts (EXTEND: add callInternalApi helper)
- frontend/src/app/portfolios/page.tsx (NEW)
- frontend/src/app/portfolios/[id]/page.tsx (NEW)
- frontend/src/app/portfolios/new/page.tsx (NEW)
- frontend/src/app/portfolios/new/actions.ts (NEW)
- frontend/src/components/charts/EquityCurveChart.tsx (MOVED from strategies/[id]/)
- frontend/src/components/charts/DrawdownChart.tsx (MOVED from strategies/[id]/)
- frontend/src/app/strategies/[id]/EquityCurveChart.tsx (REPLACED with re-export)
- frontend/src/app/strategies/[id]/DrawdownChart.tsx (REPLACED with re-export)
- frontend/src/components/portfolio/InstrumentPicker.tsx (NEW)
- frontend/src/components/portfolio/WeightTable.tsx (NEW)
- frontend/src/components/nav/TopNav.tsx (UPDATE: add Strategies + Portfolios links)
- frontend/src/__tests__/portfolios/portfolios.test.ts (NEW)
- frontend/src/__tests__/portfolios/instruments.test.ts (NEW)
- frontend/src/__tests__/portfolios/actions.test.ts (NEW)
- frontend/src/__tests__/portfolios/InstrumentPicker.test.tsx (NEW)
- frontend/src/__tests__/portfolios/WeightTable.test.tsx (NEW)

## Expected runtime
All queries are simple SELECTs on small tables (<1K rows). Sub-second.
No complex aggregations needed. No chunking or streaming required.
