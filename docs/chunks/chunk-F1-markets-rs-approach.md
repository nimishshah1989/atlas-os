---
chunk: F.1
project: atlas-os
date: 2026-05-27
status: success
---

# Chunk F.1 — /markets-rs page approach

## Goal
Build /markets-rs root route per mockup 03 (03-markets-rs.html r3 multidim charts).
This is the ONE demo page that proves the skill loop works end-to-end.

## Data scale (verified from migration notes)
- `atlas.mv_markets_rs_grid`: 9 rows (one per baseline). Trivially small. Single SQL.
- `public.de_index_prices`: 2,499 rows (10yr, 5 India indices). For detail charts if added.
- `public.de_global_prices`: ~46K rows (^GSPC 39702, URTH 3406, VWO 2588).
- `atlas.atlas_macro_daily.usdinr`: 2704/2711 populated.

## Approach

### Query module
`frontend/src/lib/queries/v6/markets_rs.ts`
- Import `server-only`
- Single query: `SELECT * FROM atlas.mv_markets_rs_grid ORDER BY rank_order`
- Returns typed `MvMarketsRsRow[]` with all ret_* and rank_* columns as strings (Postgres NUMERIC → string via postgres-js)
- Compute hero readouts in TypeScript from the 9 rows (no second SQL query needed — 9 rows in memory is fine):
  - today_leader: find row with rank_1w === 1
  - india_rank_1m: find 'Nifty 500' row, read rank_1m
  - large_vs_midsmall_spread_3m: Nifty 100 ret_3m minus avg(Midcap150, Smallcap250) ret_3m
  - india_rs_grade: avg of Nifty 500 rank_1m + rank_3m + rank_6m → A/B/C/D per spec

### MarketsRsClient.tsx
All rendering logic. Sections:
1. Page-head: breadcrumb, serif H1, sub, as-of stamp
2. 4-card hero readout (paper-soft bordered row)
3. RS grid: inline HTML table (not MultiBenchmarkRSWaterfall — that component is for stock-level waterfall attribution, wrong pattern). Uses cellTint() helper to assign CSS class.
4. Narrative card: 5 auto-generated rows from grid data (deterministic, real data)
5. Detail charts: 6 inline SVG charts using the mockup's exact 3-pane (PRICE/RS/VOL) pattern. Charts use hardcoded-shape SVG paths since historical time-series query is deferred (flagged in comments).
6. Footnote

### Tailwind tokens only
All tokens from tailwind.config.ts: bg-paper, bg-paper-soft, bg-paper-deep, border-paper-rule, text-ink, text-ink-secondary, text-ink-tertiary, text-signal-pos, text-signal-neg, text-signal-warn, font-mono, font-serif.
Zero raw hex or bg-red-500 etc.

### Components reused (≥3 required)
1. DataSourceBanner
2. ELI5Tooltip (for narrative card hover)
3. GradeChip (for India RS grade badge)
If GradeChip doesn't fit, use inline span with correct token classes.

### Page shell
`frontend/src/app/markets-rs/page.tsx` — RSC, ≤250 LOC, force-dynamic.
`frontend/src/app/markets-rs/loading.tsx` — skeleton with paper-deep placeholder blocks.

## Edge cases
- NULL ret_* columns (foreign baselines with insufficient history): toNumber returns null, render "—"
- as_of_date NULL: fall back to "today"
- 9 rows vs fewer: narrative skips if leader/laggard not found
- Rank ties (dense_rank can give same rank to 2 rows): rank pill shows the integer as-is

## Detail charts deferral
The full multidim charts require historical price + volume + RS strips per baseline.
Phase F.1 delivers REPRESENTATIVE SVG mockups using the grid's single-point ret_3m value
to set the RS strip direction and magnitude, with placeholder price/volume shapes.
A code comment marks each chart: `// TODO F.2: replace with live time-series query`.

## Expected runtime on t3.large
9-row MV query: <5ms. Page renders in <200ms.

## Wiki patterns checked
- `docs/chunks/chunk-D7-etfs-list-approach.md` — RSC shell + client component split
- `docs/chunks/chunk-C15-stocks-list-approach.md` — table-with-color-cells pattern
