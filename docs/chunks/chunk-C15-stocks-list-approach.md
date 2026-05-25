# chunk-C15-stocks-list-approach.md

## Task
C.15 — /v6/stocks list page (rewire to v6 queries + column chooser + portfolio badge)

## Data scale
- atlas_universe_stocks: ~727 rows (vocabulary lock)
- atlas_conviction_daily: ~2,900 rows per snapshot (727 × 4 tenures)
- atlas_stock_metrics_daily: large historical table; all queries use date-pinned WHERE clauses
- atlas_paper_portfolio: empty at v6.0 launch, handled gracefully

## Approach

### Page shell (page.tsx)
The existing 57-LOC shell already:
- fetches `getStocksForDate(snapshotDate)` and `getCellDefinitions()`
- renders `StocksTableV6` (original component)

Changes needed:
- Add `getHeldIidSet()` call from portfolio_holdings module
- Replace `StocksTableV6` reference with new `StocksListV6` client component
- Pass `heldIids: Set<string>` as a serializable `heldIids: string[]` array (Sets don't serialize across the RSC boundary)
- Keep shell ≤ 250 LOC

### Query extension (stocks.ts)
The existing `getStocksForDate` query does NOT fetch `ret_1d` or `ret_1w` — required by design lock §3.4 ("always visible" short-horizon columns for stocks). Add additive columns to `StockRow` and the SQL SELECT. The `ScreenStock` type also lacks these fields, so we extend the query return type in-place and add a separate `StockRowExtended` type locally.

Rather than modify the `ScreenStock` type in `v1.ts` (risky, breaks other consumers), we'll define a local `StockV6Row` type in stocks.ts that extends ScreenStock with `ret_1d: number | null` and `ret_1w: number | null`, and update `getStocksForDate` return type to `StockV6Row[]`.

### StocksListV6.tsx (new client component)
- Full table with ColumnChooser, filter row, sort, virtualization
- Default visible columns: ticker, name, sector, tier, grade/action, 1d, 1w, 6m return, RS pct, IC, fric-adj, composite score, PortfolioBadge
- Optional columns via ColumnChooser: volatility, 1m/3m/12m returns, EMA distance, RSI, drawdown
- Filter row: cap_tier, sector, action (POSITIVE/NEUTRAL/NEGATIVE), in_my_book toggle
- Virtualization: @tanstack/react-virtual for >300 rows
- URL-param persistence for filters via useSearchParams + router.push
- Sort: all column headers sortable, default composite (tape score) DESC
- Empty state: "No stocks match the current filters" with clear-filters CTA

### Virtualization strategy
With 727 rows, @tanstack/react-virtual is needed. We'll use `useVirtualizer` from `@tanstack/react-virtual` with:
- `estimateSize: () => 40` (row height estimate)
- Container with fixed height (70vh or calculated)
- Only render visible rows + overscan of 10

### Grade/IC computation
- The `conviction_tape` on each stock has per-tenure IC values. For the "IC" column, use the 6m tenure IC (matching default tenure, could be made tenure-aware)
- For "fric-adj composite" (composite_score), use the tapeScore function: count of POSITIVE segments + 0.5 × sum of IC

### Portfolio badge column
- `heldIids` passed as string[] from page.tsx (serializable)
- In StocksListV6, build `heldSet = new Set(heldIids)` from prop
- For each row, pass `state = heldSet.has(s.iid) ? PLACEHOLDER_HOLDING_STATE : null` to `PortfolioBadge`
- Since portfolio_count/weight are not available per-iid client-side, we use a minimal HoldingState with portfolio_count=1, aggregate_weight='0.00', last_add_date=null for held items — just enough to trigger badge render

## Wiki patterns checked
- `~/.forge/knowledge/wiki/index.md` — consulted for virtualization patterns
- Existing: `useColumnPreferences.ts`, `ColumnChooser.tsx`, `PortfolioBadge.tsx` — all will be reused directly
- `StocksTableV6.tsx` kept intact (other consumers may reference it); StocksListV6 is the v6 evolution

## Edge cases
- ret_1d / ret_1w: NULL-safe — format as "—" when null (formatPct handles null)
- heldIids empty Set: PortfolioBadge returns null (silent absence) — handled
- 0 rows after filter: empty state render (no synthetic rows)
- URL params: useSearchParams requires Suspense wrapper at call site — page.tsx wraps in Suspense already via force-dynamic
- Sort stability: use Array.from().sort() not in-place mutation of props

## Expected runtime
- Query: <200ms (indexed WHERE clauses, 727 rows)
- Client render: <100ms (virtualized, only ~20 rows in DOM at once)

## Files to modify/create
1. `frontend/src/app/v6/stocks/page.tsx` — add heldIids fetch, swap component
2. `frontend/src/lib/queries/v6/stocks.ts` — add ret_1d/ret_1w to query + StockV6Row type
3. `frontend/src/components/v6/StocksListV6.tsx` — new client component (main deliverable)
4. `frontend/src/components/v6/__tests__/StocksListV6.test.tsx` — 5 test cases
