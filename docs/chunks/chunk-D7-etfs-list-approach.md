# Chunk D.7 — /v6/etfs list extend + ETF AMC leaderboard

## Task
Extend `frontend/src/app/v6/etfs/page.tsx` (thin RSC shell) and create
`frontend/src/components/v6/ETFsList.tsx` (client component) with:
- IndustrySnapshot ETF variant (includes AMC leaderboard)
- BubbleRiskReturnChart for ETFs
- SignatureMatrix for ETFs
- Ranked table: name, category, AUM, expense_ratio, tracking_error, Atlas grade,
  1w return, 6m return, composite, top-3 holdings, PortfolioBadge column (default visible)
- ColumnChooser for additional columns
- Empty state: "No ETFs available"

## Data scale
- ETF scorecard: ~80-120 rows per snapshot (small — all fits in memory)
- No psql check needed; existing etfs.ts query already proven

## Data layer decisions
- `expense_ratio` and `tracking_error`: source from `raw_metrics->>'ter_pct'` and
  `raw_metrics->>'tracking_error_252d'` via SQL cast in etfs.ts
- `aum_cr`: from `raw_metrics->>'aum_cr'`
- `amc` (for IndustrySnapshot leaderboard): existing `getIndustrySnapshot('etfs')` already
  derives from `atlas_etf_scorecard.amc` (confirmed in industry_snapshot.ts query)
- `top_holdings`: ETF scorecard has no top_holdings JSONB; display "—" as placeholder
- PortfolioBadge: use `getHoldingState` from portfolio_holdings, passed as prop map
- Sort default: composite_score DESC (already the query default)

## Extended etfs.ts query
Add to SELECT from `atlas_etf_scorecard`:
```sql
(s.raw_metrics->>'ter_pct')::text          AS expense_ratio,
(s.raw_metrics->>'tracking_error_252d')::text AS tracking_error,
(s.raw_metrics->>'aum_cr')::text           AS aum_cr,
```
Also pull `s.is_atlas_leader` as grade signal.

## Extended ScreenEtf type
Add `expense_ratio: string | null`, `tracking_error: string | null`,
`aum_cr: string | null`, `is_atlas_leader: boolean | null`,
`composite_score: string | null`, `ret_1w: number | null` (derived from ret_1m).

## Architecture
- `page.tsx`: RSC fetches data (etfs, snapshot, holdingState map) → passes to ETFsList
- `ETFsList.tsx`: `'use client'` — renders IndustrySnapshot + Bubble + SignatureMatrix + table
- Table columns with ColumnChooser following C.15/C.16 stocks pattern

## Tests
5 cases in `ETFsList.test.tsx`:
1. Renders rows from query
2. PortfolioBadge column visible by default
3. ColumnChooser toggle hides/shows column
4. Empty state: "No ETFs available"
5. Sort by composite_score DESC by default (first row has highest score)

## Expected runtime
< 500ms (80 rows, direct SQL, single snapshot_date filter)

## Edge cases
- NULL expense_ratio / tracking_error: display "—"
- ETF category ≠ 'broad_index': tracking_error column shows "—" (index ETFs only)
- Empty etfs array: "No ETFs available" 
- PortfolioBadge absent when no holding (silent null per FM-critic spec)

## Wiki / existing patterns checked
- C.15 stocks list page pattern (ColumnChooser wiring)
- C.11 IndustrySnapshot (already supports ETF variant)
- C.8 BubbleRiskReturnChart (generic, accepts BubbleDatum[])
- C.12 SignatureMatrix (generic, accepts SignatureCell[])
- B.6 PortfolioBadge (compact variant, silent null)
