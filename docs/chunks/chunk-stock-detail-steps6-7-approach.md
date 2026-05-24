# Chunk: Stock Detail Steps 6-7 — 4 Viz Components + 2 Queries

## Task
Build OBVContinuousChart, ATRContractionGauge, WithinStatePeers, DwellTimeline + 2 SQL queries.

## Data scale
- `de_equity_ohlcv`: point queries by instrument_id + date range. 50-280 rows max per call.
- `atlas_stock_state_daily`: point query by instrument_id, last 252 rows.
- All queries are narrow (instrument_id + date window) — no scale concern.

## Chosen approach
- SQL for OBV and ATR computations (window functions, self-contained).
- Recharts (already installed, used in LineChart.tsx) for OBV sparkline.
- Pure CSS bar for ATR gauge (no chart library needed).
- Pure HTML table for WithinStatePeers (consistent with project pattern).
- Flex bar-strip for DwellTimeline (same pattern as StateTimeline.tsx).
- OBVContinuousChart and ATRContractionGauge need `'use client'` because Recharts requires browser environment.
- DwellTimeline and WithinStatePeers are pure server components.

## Wiki patterns checked
- Recharts LineChart.tsx: uses 'use client', ResponsiveContainer, ReferenceLine for zero line.
- StateTimeline.tsx: flex strip pattern for color-coded state bars.
- ComponentValidationRow.test.tsx: test fixture factory + @testing-library/react pattern.

## Existing code reused
- `@/lib/db` (sql template tag) — same import as all other query files.
- `de_equity_ohlcv` (public schema, not atlas schema — confirmed in spec SQL).
- `atlas_stock_state_daily` (atlas schema) — already in states.ts.
- Recharts imports pattern from LineChart.tsx.
- State color tokens from globals.css: signal-pos, signal-neg, signal-warn, paper-rule, ink-tertiary.

## Edge cases
- OBV: first row has NULL prev_close → signed_volume = 0 (CASE handles it).
- ATR: NULLIF(avg, 0) guards zero-denominator.
- series.length < 14: explicit placeholder rendered.
- history.length < 30: explicit placeholder.
- ATRContraction null: explicit placeholder.
- DwellTimeline: bar width is 1/252 of container. At 600px wide, each bar ≈2.4px — fine.

## bg-paper-highlight
Not in globals.css. Using `bg-teal/10` (Tailwind CSS 4 opacity syntax) as the highlight token
for the current-stock row in WithinStatePeers.

## Expected runtime
- All queries: <50ms (indexed point lookups, 50-280 rows).
- Components: server-rendered except OBVContinuousChart + ATRContractionGauge (client).
