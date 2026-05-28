# Chunk: India Pulse Page (Page 02)

## Data scale
- `atlas.mv_india_pulse`: 2,612 rows, ONE row per as_of_date
- Query: single row read by MAX(as_of_date) — sub-millisecond
- All heavy work pre-computed in the MV (JSONB columns built server-side)
- Expected runtime: <50ms (single row + index seek)

## MV column inventory
Scalars: `as_of_date`, `breadth_pct_above_200dma`, `india_vix`, `cross_section_dispersion`, 
         `smallcap_rs_z`, `vix_pct_v6`, `vix_spot`, `vix_5y_pct`, `vix_term_structure`
JSONB:   `headline_indices` (array[8]), `breadth_table` (array[9]), `sector_heatmap` (array[N]),
         `tier_leadership` (object), `dispersion_60d_series` (array), `macro_cards` (array[8]),
         `narrative_ribbon` (object)

## JSONB shapes (from migration 100)

### headline_indices — array of 8 objects
```
{ index_code, label, close, ret_1d, ret_1w, ret_1m, ret_3m, ret_6m, rs_3m_vs_nifty500 }
```

### breadth_table — array of 9 objects (7 live + 2 data_gap)
```
{ metric, label, today, delta_1w, delta_1m, delta_3m, data_gap: bool }
```

### sector_heatmap — array of N objects
```
{ sector_name, rs_1w, ret_1m, ret_3m }
```

### tier_leadership — object
```
{ returns_table: [ {window, sc, mc, lc, sc_lc_spread, mc_lc_spread} × 5 ], smallcap_rs_z }
```

### dispersion_60d_series — array
```
[ { date, value } ]
```

### macro_cards — array of 8 objects
```
{ id, label, value, ret_1d, ret_1m, sparkline_30d: [{date, v}] }
```

### narrative_ribbon — object
```
{ india_10y_yield, real_yield, cpi_yoy, fii_flow_1m_cr, dii_flow_1m_cr, equity_earnings_yield }
```

## Mockup sections (7 named h2.section-title)
1. "Headline indices" — 4×2 grid of rich index cards
2. "Breadth" — dense table with 9 rows + sparklines + progress bars
3. "Dispersion & concentration" — 60d dispersion line chart + sector return bar chart
4. "Volatility" — 3 cards (spot VIX, 5y percentile, term structure)
5. "Tier leadership · mid & small vs large" — dual-line RS Z-score chart + returns table
6. "Sectoral indices · heatmap" — 11×2 grid of colored sector cells
7. "Macro context" — 8 cards + narrative ribbon

Plus a hero strip of 4 scalars above the sections (not a named section).

## Approach
- Server component page.tsx — one SQL call, passes typed data to client components
- Each section = one client component in `frontend/src/components/v6/india-pulse/`
- Recharts for dispersion line chart (LineChart), sector return bar chart (BarChart),
  tier Z-score line chart (LineChart) — all are <client> components
- Static table renders (breadth table, tier returns table, macro cards) = server-safe
  but in client components because they share "use client" with the chart sections
- No float money: all values are numeric from DB, formatted via existing formatINR/formatPct helpers
- Data gaps (breadth_table.data_gap=true) rendered as "—" rows with visual indicator
- NULL handling explicit: every field has null check before render

## Wiki patterns checked
- Query layer: mirrors `markets_rs.ts` pattern exactly
- Server components: RSC shell → client component pattern from `markets-rs/page.tsx`
- Decimal: using `toNumber()` from `@/lib/v6/decimal`

## Existing code reused
- `DataSourceBanner` — data-as-of strip
- Format utilities: `formatINR`, `formatPct`, `signedPct` from `@/lib/v6/decimal`
- `formatIST` from `@/lib/format-date`
- Tailwind tokens from globals.css

## Edge cases
- All JSONB can be null (LEFT JOINs in MV) — handle with early fallback render
- data_gap rows in breadth_table: render label but show "N/A" for values
- dispersion_60d_series may be empty if atlas_regime_daily has no recent data
- macro sparklines may be empty arrays or null
- sector_heatmap retval sorted by rs_1w DESC already (per MV ORDER BY)
