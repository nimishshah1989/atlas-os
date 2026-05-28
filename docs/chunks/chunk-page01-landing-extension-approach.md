# Chunk: Page 01 Landing Extension — 12-week journey + Today's conviction tabs

## Data scale
- `atlas_market_regime_daily`: ~500-700 rows (daily since ~2023). 84-day window for journey = 84 rows max.
- `atlas_signal_calls`: ~363 rows backfilled. Active calls (exit_date IS NULL) filtered to latest 30-50.
- `atlas_etf_signal_calls`: ~9 rows backfilled.
- `atlas_universe_stocks`: ~750 rows (full universe).

## Chosen approach

### 12-week journey section
- Reuse `getRegimeDetail()` from `frontend/src/lib/queries/v6/regime.ts` — it already returns `journey[]` (84-day history, oldest→newest) and `inputs[]` (breadth, vix, dispersion).
- Downsample daily data to weekly in TypeScript layer: group by ISO week, pick the last day's value.
- New component `RegimeJourney12w.tsx` under `frontend/src/components/v6/landing/`:
  - Row 1: Colored blocks per week (regime_state → CSS color class)
  - Rows 2-4: metric cells (Breadth %, India VIX, Dispersion)
  - Date row: week start labels
  - No Recharts needed — pure div/CSS grid like the mockup (segmented bar is CSS, not a chart)

### Today's conviction tabs
- New query `getTopConvictionCalls()` in `frontend/src/lib/queries/v6/landing.ts`:
  - Stocks tab: `atlas_signal_calls` active (exit_date IS NULL), joined `atlas_universe_stocks`, ordered by confidence_unconditional DESC, LIMIT 15
  - ETFs tab: `atlas_etf_signal_calls` active, joined `atlas_universe_etfs`, LIMIT 10
  - Funds tab: `atlas_fund_scorecard` latest snapshot with recommendation IN ('SWITCH IN', 'HOLD'), LIMIT 10
- New component `TodayConvictionTabs.tsx` under `frontend/src/components/v6/landing/`:
  - Client component with useState for tab selection
  - 3 tabs: Stocks / ETFs / Funds
  - Each tab shows a list of conv-rows (symbol, name/sector, cell_name, confidence bar, action badge, predicted_excess)
  - Reuse GradeChip for action badges

## Wiki patterns checked
- frontend-component pattern (patterns/)
- server-component query pattern

## Existing code reused
- `getRegimeDetail()` from `frontend/src/lib/queries/v6/regime.ts` — journey data already fetched
- `GradeChip.tsx` — action badges (BUY/AVOID/WATCH)
- `DataSourceBanner.tsx` — may use for as-of date
- RegimeHero color helpers — regime-state → color mapping

## Edge cases
- Empty journey: render 12 gray placeholder cells
- NULL breadth/vix/dispersion: show "—" in metric cells
- Zero active calls: tab shows "No active calls" message
- Funds tab may have zero rows if scorecard hasn't run: handled gracefully
- Current week highlighted with ring (last cell in journey row)

## Files
**CREATE:**
- `frontend/src/components/v6/landing/RegimeJourney12w.tsx`
- `frontend/src/components/v6/landing/TodayConvictionTabs.tsx`
- `frontend/src/lib/queries/v6/landing.ts`
- `frontend/src/components/v6/landing/__tests__/RegimeJourney12w.test.tsx`
- `frontend/src/components/v6/landing/__tests__/TodayConvictionTabs.test.tsx`

**MODIFY:**
- `frontend/src/app/page.tsx` — APPEND new sections below existing content

## Expected runtime
- `getTopConvictionCalls()`: <10ms (small tables, indexed on exit_date)
- `getRegimeDetail()` already called: journey is free (reuse prop)
- Page render: <80ms total on t3.large
