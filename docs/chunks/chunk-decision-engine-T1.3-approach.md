# Task 1.3: Regime page — verdict + scorecard + worklist

## Data sources verified (real columns, no fabrication)

### Trend tile
- Source: `atlas.atlas_stock_state_daily` (table already queried in `states.ts`)
- Column: `state` — values include `stage_2a`, `stage_2b`, `stage_2c`, `stage_1`, `stage_3`, `stage_4`, `uninvestable`
- Formula: `COUNT(*) FILTER (WHERE state IN ('stage_2a','stage_2b','stage_2c')) / COUNT(*)`
- Grouped by latest date (`ORDER BY date DESC LIMIT 1` subquery approach or using `classifier_version = 'v2.0-validated'`)

### Breadth tile
- Source: `atlas.atlas_market_regime_daily` — `pct_above_ema_50` column
- Already available in `MarketRegimeRow` returned by `getCurrentRegime()`
- No extra query needed — pass from `current` prop
- Formula: fraction of Nifty 500 stocks above their 50-day EMA

### Momentum tile
- Source: `atlas.atlas_stock_state_daily` — looking at `state` on latest date vs 5 trading days prior
- Net Stage-2 inflow = (count in stage_2* on today) - (count in stage_2* on date 5 rows back)
- Use a window CTE to get latest_date and date-5 rows
- Returns a signed integer (positive = net inflow, negative = net outflow)

### Participation tile
- Source: `atlas.atlas_sector_metrics_daily` — `leadership_concentration` column (real, confirmed in `sectors.ts` type definitions and query)
- Formula: `AVG(1 - leadership_concentration)` across all sectors on latest date
- leadership_concentration is 0..1; higher = more concentrated = worse participation quality
- `1 - leadership_concentration` = breadth of leadership across sector

## Worklist sources
- "Sectors entered favour" — sectors whose `sector_state` changed to `Overweight` recently (join `atlas_sector_signal_unified` with LAG). Count from `mv_sector_rotation_state` or query `atlas_sector_signal_unified` directly.
- "Fresh breakouts" — count from `atlas.mv_breakout_candidates` (used in intelligence.ts already)
- "Holdings deteriorating" — count from `atlas.mv_deterioration_watch` (used in intelligence.ts already)

## RegimeVerdict
- Accepts `(regimeState, deploymentPct, leadingSectors)` as props
- Returns one-line sentence, no DB needed — pure derivation from props

## Architecture decisions
- `regime-scorecard.ts` — new query file with `getRegimeScorecard()` function
  - Returns `{ trend, breadth, momentum, participation, worklist }` in one parallel call
  - Trend and Momentum require direct SQL on `atlas_stock_state_daily`
  - Breadth comes from `pct_above_ema_50` already in `getCurrentRegime()` — pass from page, no duplicate query
  - Participation from `atlas_sector_metrics_daily`
  - Worklist counts from `mv_breakout_candidates` + `mv_deterioration_watch` + `atlas_sector_signal_unified`
- Components are presentational — take data as props, no DB calls inside components
- `page.tsx` calls `getRegimeScorecard()` alongside existing `getCurrentRegime()` + `getRegimeHistory()`
- Three new components: `RegimeVerdict`, `SignalScorecard`, `TodayWorklist`

## Metric registry additions
- `scorecard_trend_pct` — % universe in Stage 2a/2b/2c
- `scorecard_breadth_pct` — % above EMA-50
- `scorecard_momentum_net` — net Stage-2 inflow over 5 trading days
- `scorecard_participation` — avg leadership breadth (1 - concentration) across sectors

## Edge cases
- Empty `atlas_stock_state_daily`: return null, render "n/a"
- `leadership_concentration` NULL on any sector: exclude that sector from AVG (SQL handles via AVG ignoring NULLs)
- `mv_breakout_candidates` empty: count = 0, worklist shows "0 fresh breakouts"
- `mv_deterioration_watch` empty: count = 0
- Sectors-entered-favour: if no recent transitions, count = 0
- Breadth comes from `current` regime row — if NULL, render "n/a"

## LOC budget
- `RegimeVerdict.tsx`: ≤120 LOC
- `SignalScorecard.tsx`: ≤180 LOC  
- `TodayWorklist.tsx`: ≤150 LOC
- `regime-scorecard.ts`: query file, no LOC limit (not a source component)
- `page.tsx`: must stay ≤250 LOC

## Test approach
- Component tests pass data as props (no DB in component tests)
- `RegimeVerdict`: test that it renders a sentence containing the regime state + deploy %
- `SignalScorecard`: test 4 tiles present, each has a tooltip trigger
- `TodayWorklist`: test sector count links to /sectors, breakout count links to /stocks/[symbol], deterioration shows list items
