# D.4 — `/v6/sectors/[name]` extend with SectorBookStrip + SectorBreadthPanel + Constituent table

## Date
2026-05-26

## Data scale
Not applicable — frontend RSC + client component. No DB queries added (reuses existing query modules).

## Approach

**Page shell** (`page.tsx`) is already 106 LOC. We slim it down to a thin wrapper (~80 LOC) that:
1. Fetches all data server-side: sectors, sectorStocks, bookExposure (single-sector filter), breadth (single-sector filter), heldIidSet, cellsRes.
2. Passes serializable props to `SectorDetailClient`.

**`SectorDetailClient.tsx`** is a `'use client'` component (~380 LOC) handling:
- Hero (sector name + rank + StateBadge + action verb + thesis bullets + ConvictionTape)
- HeroBookBand — a thin band reading the single SectorBookExposure row showing "Your book in this sector: X% (vs N500 weight Y%) — OVERWEIGHT chip"
- SectorBookStrip (single variant — full row detail below hero)
- SectorBreadthPanel
- BubbleRiskReturnChart (sector constituents as bubbles)
- Constituent table (ColumnChooser + PortfolioBadge per held iid)

## Reused components
- `SectorBookStrip` — single variant, pass exposures filtered to this sector
- `SectorBreadthPanel` — pass single SectorBreadth row
- `BubbleRiskReturnChart` — map StockV6Row to BubbleDatum
- `PortfolioBadge` — compact variant, silent when iid not in heldIidSet
- `ConvictionTape` — compact in table rows
- `StateBadge`, `DataSourceBanner`, `LinkedCellById` — already in page.tsx
- `ColumnChooser` hook pattern from StocksListV6

## Hero book band logic
- `exposure.book_weight` / `exposure.benchmark_weight` (pp strings, divide by 100 for display)
- Chip: classify(delta_pp) → OVERWEIGHT / UNDERWEIGHT / NEUTRAL
- Silent if exposure is null / empty

## Constituent table
- Columns (default visible): symbol, name, rs_state (stage), conviction_tape, ret_1m, ret_3m, portfolio_badge
- ColumnChooser allows adding: ret_6m, ret_12m, rs_pctile_3m
- PortfolioBadge compact: `heldIidSet.has(row.iid) ? makeHoldingState(row.iid) : null`
  - Since `getHeldIidSet` returns a Set, we check membership; for compact display in table we create a minimal HoldingState stub from set membership (portfolio_count=1, aggregate_weight='0.00', last_add_date=null)

## BubbleRiskReturnChart mapping
- risk: ret_1m standard deviation proxy (use rs_pctile_3m as risk proxy)
- ret: ret_3m
- size: fallback to "1" (uniform) — no mcap column in v6.0
- state: map rs_state → POSITIVE/NEUTRAL/NEGATIVE

## Empty states
- No constituents → "No constituents found" text
- No book (empty heldIidSet and empty exposure) → SectorBookStrip silent (passes empty exposures, component renders sr-only)
- No breadth → breadth section hidden

## LOC budget
- page.tsx: ~85 LOC (trim from 106 by moving all logic to client)
- SectorDetailClient.tsx: ~400 LOC
- Test: ~280 LOC (5 cases)

## Expected runtime
Frontend-only, no new SQL. Negligible impact.

## Edge cases
- Sector not found → notFound() in page.tsx (existing behavior preserved)
- sectorStocks empty → "No constituents found" message
- All held positions zero → SectorBookStrip renders sr-only
- BubbleRiskReturnChart with single stock → renders fine (Recharts handles single point)
- PortfolioBadge compact in table → returns null for unheld iids (silent)
