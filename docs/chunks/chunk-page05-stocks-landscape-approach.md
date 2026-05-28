# Chunk: Page 05 Stocks — Landscape Extension

## Data scale
- `mv_stock_landscape`: 747 rows (one per active stock, latest snapshot)
- 30d trajectory JSONB: avg ~8 data points per row
- Matrix grouping: 3 tiers × 8 columns = 24 cells max from 747 rows

## MV Column inventory (confirmed from live Supabase)
instrument_id, symbol, company_name, sector, industry, cap_tier,
ret_1m, ret_3m, ret_6m, ret_12m, rs_1w_nifty500, rs_1m_nifty500, rs_3m_nifty500,
conviction_score, conviction_tier, confidence_label, composite_score, action,
bubble_quadrant, liquidity_proxy_cr, close_price, matrix_tenure_dominant,
matrix_action_sign, cell_id, cell_action, cell_tenure, cell_predicted_excess,
cell_signal_confidence, cell_fire_date, cell_ic, cell_friction_adjusted_excess,
composite_trajectory_30d (JSONB array of {date, score}), realized_vol_63, refreshed_at

Note: rs_3m_nifty500 is ratio-form (e.g. -0.04 = -4pp). Multiply by 100 for display.
Note: composite_score is numeric (e.g. -4.44), not string.
Note: cell_ic is numeric (e.g. 0.5864).

## Approach

### Query layer — `src/lib/queries/v6/stocks-landscape.ts`
All 3 functions use server-only postgres (sql from @/lib/db). Scale is 747 rows —
well under 1K threshold, any approach works but we use SQL aggregation for matrix.

1. `getStocksLandscape()` — SELECT all 747 columns needed for bubble + six picks
2. `getMatrixCells()` — GROUP BY cap_tier, matrix_tenure_dominant, matrix_action_sign
   → COUNT(*), AVG(cell_ic) per cell. Server-side aggregation, not Python.
3. `getHeroStories()` — 4 sub-queries with ORDER BY + LIMIT 5 each:
   - fresh BUYs: action='BUY' ORDER BY composite_score DESC LIMIT 5
   - fresh AVOIDs: action='AVOID' ORDER BY composite_score ASC LIMIT 5
   - high conf BUYs: action='BUY' AND confidence_label IN ('industry_grade','high_confidence')
   - exit candidates: WATCH/degrading composite (composite_score between -4 and 4, matrix_action_sign='NEG')

### Components — all new in `src/components/v6/stocks/`

**HeroStories.tsx** — 4-column grid. Each block: eye label + count pill, list of stocks
with dot + name + meta + value. Data from getHeroStories(). Server component.

**ConvictionBubbleChart.tsx** — client component. Uses existing BubbleRiskReturnChart but
with remapped props: x=rs_3m_nifty500*100, y=composite_score, z=liquidity_proxy_cr,
color by action (BUY=pos, WATCH=neutral/warn, AVOID=neg). 4 quadrant tint overlays via
reference rectangles. Labels: CONTRARIAN BUY, CLEAN BUY, CLEAN AVOID, RS HOLDING COMPOSITE DOWN.
Filter chips: All / BUY only / Large only — client state.

**Matrix24Cell.tsx** — NEW component (different from CellMatrix which is rule-based matrix).
This one shows count+IC from mv_stock_landscape grouping. 3 rows (Large/Mid/Small) × 8 cols
(1m POS/NEG, 3m POS/NEG, 6m POS/NEG, 12m POS/NEG). Cell color by:
  pos-strong: count≥15 AND action_sign=POS
  pos: count≥8 AND action_sign=POS
  pos-weak: count<8 AND action_sign=POS
  neg-strong: count≥15 AND action_sign=NEG
  neg: count≥8 AND action_sign=NEG
  neg-weak: count<8 AND action_sign=NEG
IC displayed as "IC .062" format.

**CompositeTrajectoriesGrid.tsx** — client component. Shows 6 stocks with 30d sparklines.
Picks top 3 BUYs + top 3 AVOIDs by |composite_score|. Uses Recharts LineChart (not SVG).
Each row: stock name/meta | sparkline | endpoint value + delta.

**SixPicksWorthClick.tsx** — client component. 3 BUY + 3 AVOID cards. Mini multidim chart
using Recharts ComposedChart (price line + volume bars + 20D-MA line). Since we don't have
raw OHLCV in this MV, we use composite_trajectory_30d as the signal line + static volume bars
approximated from liquidity_proxy. Cards link to /stocks/[symbol].

### Page integration
`frontend/src/app/stocks/page.tsx` — add parallel data fetches for landscape + heroes,
insert new sections ABOVE existing StocksClientShell. No modifications to existing shell.

## Edge cases
- mv_stock_landscape may have NULLs for composite_trajectory_30d — handle with empty array
- rs_3m_nifty500 NULL → bubble shows at origin, not error
- composite_score NULL → treat as 0, flag with neutral color
- Matrix cells with 0 count → show as empty cell (paper-soft bg)
- trajectory_30d with fewer than 2 points → skip sparkline, show "--"

## Expected runtime
- 3 parallel SQL queries on 747 rows: < 200ms total
- Matrix GROUP BY: server-side, < 50ms
- Page render: < 500ms total (well within Next.js server component budget)
- No iterrows, no apply, no full-table loads to Python
