# Chunk C.11 — IndustrySnapshot Approach

## What we're building
- `frontend/src/lib/queries/v6/industry_snapshot.ts` — server-only query returning IndustrySnapshot for funds or ETFs
- `frontend/src/lib/queries/v6/__tests__/industry_snapshot.test.ts` — 4 test cases
- `frontend/src/components/v6/IndustrySnapshot.tsx` — React component
- `frontend/src/components/v6/__tests__/IndustrySnapshot.test.tsx` — 4 test cases

## Data scale
- `atlas_fund_scorecard`: moderate size (hundreds of funds), single snapshot_date query
- `atlas_etf_scorecard`: small (tens to low hundreds of ETFs)
- Both: aggregation via SQL AVG/COUNT/GROUP BY — no Python computation needed

## Approach

### Query (industry_snapshot.ts)
Two separate SQL paths, one per asset_class:
- Funds: `atlas_fund_scorecard` — has `composite_score`, `is_atlas_leader`, `is_avoid`, `amc`, `sub_metrics` JSONB for expense_ratio + aum_cr
- ETFs: `atlas_etf_scorecard` — same scorecard shape but different table and column names

SQL aggregation strategy:
- Single query with two CTEs: `totals` (COUNT/SUM/AVG) + `amc` (GROUP BY amc ORDER BY AVG(composite_score) LIMIT 5)
- Returns JSON directly from Postgres to avoid Python-level iteration
- `median_expense` and `median_aum_cr` computed as AVG (approximate) from sub_metrics JSONB cast
- `pct_above_benchmark_3y` returns null (no column available in either scorecard)

### Component (IndustrySnapshot.tsx)
- `'use client'` component (pure display, no server fetch)
- Props: `{ snapshot: IndustrySnapshot; className?: string }`
- Layout:
  1. Header with asset class label
  2. Top row: 3 stat tiles (n_atlas_leaders, n_avoid, n_total)
  3. Median row: 2 more tiles (median_expense %, median_aum_cr crores)
  4. AMC leaderboard: 5 rows, color-coded by avg_composite quartile
     - Both funds AND ETFs get leaderboard (per Vocabulary lock override)
     - Empty leaderboard: "Insufficient data" placeholder
- Tokens: signal-pos/neg/warn, paper, ink-* classes

### Edge cases
- NULL amc rows excluded from leaderboard (`WHERE amc IS NOT NULL`)
- Empty leaderboard array renders placeholder text
- JSONB expense/aum fields may be NULL → AVG returns NULL → rendered as "—"
- `is_avoid` column exists on fund scorecard; ETF scorecard uses same boolean pattern

## Wiki patterns checked
- Existing `funds.ts` and `etfs.ts` for SQL shape and sql`` tagged template usage
- `cells.test.ts` for mock pattern (`vi.mock('server-only')`, `vi.mock('@/lib/db')`)
- `RankDecompositionCards.tsx` for component + test pattern

## Existing code reused
- `sql` tagged template from `@/lib/db`
- `toNumber`, `formatINR` from `@/lib/v6/decimal`
- Tailwind token classes from GradeChip.tsx (signal-pos, signal-neg, signal-warn, paper, ink-*)

## Expected runtime
- SQL: <100ms (simple aggregation on indexed snapshot_date column, <1K rows)
- Component render: trivial (<5ms)

## LOC estimate
- `industry_snapshot.ts`: ~130 LOC
- `industry_snapshot.test.ts`: ~160 LOC
- `IndustrySnapshot.tsx`: ~160 LOC
- `IndustrySnapshot.test.tsx`: ~180 LOC
