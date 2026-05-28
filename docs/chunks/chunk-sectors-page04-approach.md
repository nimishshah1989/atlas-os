# Chunk: Sectors Page 04 + 04a — Approach

**Date:** 2026-05-27
**Status:** planning

## Actual Data Scale

- `mv_sector_cards`: ~47K rows (31 sectors × ~1,550 trading days), latest snapshot = 30 rows
- `mv_sector_breadth`: same shape as cards, ~47K rows
- `mv_sector_rrg`: same shape, ~47K rows. Each row has `trail_6w` JSONB array (up to 6 weekly snapshots)
- `mv_sector_deepdive`: LATEST-ONLY, ~30 rows total (one per sector). JSONB sections.

All queries use `WHERE as_of_date = (SELECT MAX(as_of_date) ...)` pattern — single-date slice.

## Chosen Approach

**SQL for all data fetching** — MVs exist specifically for this page. No Python computation.
Each query hits the MV with a `MAX(as_of_date)` subquery to get the latest snapshot.
- `getSectorCards()` — latest 30 rows from `mv_sector_cards`
- `getSectorBreadth()` — latest 30 rows from `mv_sector_breadth`
- `getSectorRRG()` — latest 30 rows from `mv_sector_rrg` with `trail_6w` JSONB
- `getSectorDeepdive(sector_name)` — single row from `mv_sector_deepdive`

**Frontend approach:**
- Next.js 14 App Router server components (RSC) — data fetching at top level
- Interactive charts (RRG scatter, heatmap clicks) in 'use client' components
- Recharts only — ScatterChart for RRG with trail polylines rendered as SVG overlays
- All new components in `frontend/src/components/v6/sectors/` namespace

## Wiki Patterns Checked

- SQL Window Computation: not needed here (MVs already computed)
- Dashboard-Backend Name Drift: we rely on MV column names derived from migrations — verified against migration SQL

## Existing Code Reused

- `SectorBreadthPanel`, `SectorBookStrip`, `DataSourceBanner`, `GradeChip` — imported directly
- `SectorsListV6` — NOT ported (has different data shape / uses old query layer)
- `/v6/sectors/page.tsx` — RRG + ladder patterns referenced but ported to new MV data

## MV Column Map

### mv_sector_cards columns:
as_of_date, sector_name, constituent_count, ret_1w, ret_1m, ret_3m, ret_6m, ret_12m,
rs_1m, rs_3m, rs_6m, vol_60d_ann, pct_above_ema20, pct_above_ema200, pct_at_52wh,
hhi_concentration, buy_signal_count, confidence_distribution (JSONB), verdict, verdict_abbr, refreshed_at

### mv_sector_breadth columns:
as_of_date, sector_name, constituent_count, pct_above_ema20, pct_above_ema50, pct_above_ema200,
pct_at_52wh, breadth_by_window (JSONB array), breadth_by_strength (JSONB), top_movers (JSONB),
bottom_movers (JSONB), refreshed_at

### mv_sector_rrg columns:
as_of_date, sector_name, rs_ratio_current, rs_momentum_current, quadrant_current,
trail_6w (JSONB array), refreshed_at

### mv_sector_deepdive columns:
sector_name, verdict, constituent_count, data_as_of, returns (JSONB), rs_windows (JSONB),
pct_above_ema20, pct_above_ema200, pct_at_52wh, constituents_top30 (JSONB array),
open_signals (JSONB array), strength_dist (JSONB), top_picks_top10 (JSONB array), refreshed_at

## Page 04 Sections (List)

1. Hero enriched readout — 3-col grid: Leading / Lagging / Rotation pattern
   Source: derived from `mv_sector_cards` (sort by rs_3m, take top 4 / bottom 5)
2. RRG Scatter chart — Recharts ScatterChart with SVG trail polylines
   Source: `mv_sector_rrg`
3. Sector cards grid — 3-col grid of 30 cards
   Source: `mv_sector_cards`
4. Heatmap table — multi-window return heatmap with color intensity
   Source: `mv_sector_cards` (ret_1w/1m/3m/6m/12m + rs_1m/3m/6m)
5. Breadth panel — bottom section
   Source: `mv_sector_breadth`

## Page 04a Sections (Detail)

1. Hero strip — 6-tile verdict strip (verdict, rs_3m, buy_signal_count, breadth, regime_fit placeholder, ret_12m)
   Source: `mv_sector_deepdive` scalars + JSONB
2. RS windows table — multi-baseline RS grid (show what we have: Nifty 500 only from MV)
   Source: `mv_sector_deepdive.rs_windows`
3. Constituents top-30 table — sortable
   Source: `mv_sector_deepdive.constituents_top30`
4. Top picks — top 10 with positive composite_score
   Source: `mv_sector_deepdive.top_picks_top10`
5. Strength distribution chart — bar chart by quintile
   Source: `mv_sector_deepdive.strength_dist`
6. Open signals panel
   Source: `mv_sector_deepdive.open_signals`
7. Macro overlays — DEFERRED (no macro data in MVs; would require separate query layer)

## Edge Cases

- NULLs in rs_* and ret_* columns → render "—" (pre-backfill data)
- Empty constituents_top30 → show empty state message
- Empty open_signals array → "No open signals"
- trail_6w with fewer than 6 elements — valid, render what exists
- mv_sector_deepdive sector not found → notFound()

## Expected Runtime

- List page: 3 parallel queries (cards, breadth, rrg) → single-date slice → <100ms
- Detail page: 1 query (deepdive) → single row → <50ms
- RRG chart: 30 scatter points + trail polylines — pure SVG, client-side only
- Heatmap: 30-row table render — trivial DOM

## Files to Create / Modify

CREATE:
- `frontend/src/app/sectors/page.tsx`
- `frontend/src/app/sectors/[sector]/page.tsx`
- `frontend/src/components/v6/sectors/SectorCardsGrid.tsx`
- `frontend/src/components/v6/sectors/SectorRRGChart.tsx`
- `frontend/src/components/v6/sectors/SectorHeatmapTable.tsx`
- `frontend/src/components/v6/sectors/SectorHeroReadout.tsx`
- `frontend/src/components/v6/sectors/SectorHeroStrip.tsx`
- `frontend/src/components/v6/sectors/ConstituentsTable.tsx`
- `frontend/src/components/v6/sectors/TopPicksPanel.tsx`
- `frontend/src/components/v6/sectors/StrengthDistChart.tsx`
- `frontend/src/components/v6/sectors/OpenSignalsPanel.tsx`
- `frontend/src/lib/queries/v6/sectors.ts` (EXTEND — add new MV query functions)
- `frontend/src/components/v6/sectors/__tests__/SectorRRGChart.test.tsx`
- `frontend/src/components/v6/sectors/__tests__/SectorCardsGrid.test.tsx`

MUST NOT TOUCH:
- Any existing component outside `sectors/` subdirectory
- `/v6/sectors/*` routes
- next.config.js, package.json, tsconfig.json
