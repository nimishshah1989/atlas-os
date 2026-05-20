# Chunk: Decision Engine Task 1.7 — /stocks sector pre-filter + index badge linking

## Data scale
- `atlas.atlas_universe_stocks`: ~500–600 rows (Indian equity universe). No scale concern.
- `getAllStocks()` returns the full universe; filtering is currently client-side in `StockScreener`.
- The query already has `u.sector` (from `atlas_universe_stocks.sector`) and the three boolean index columns `u.in_nifty_50`, `u.in_nifty_100`, `u.in_nifty_500`.

## Real column names found
- **Sector**: `u.sector` on `atlas.atlas_universe_stocks` — a plain text column. Already in SELECT.
- **Index membership**: three boolean columns: `u.in_nifty_50`, `u.in_nifty_100`, `u.in_nifty_500` — all already SELECTed. These are REAL columns with data. Part B is implementable.

## Chosen approach

### Part A: sectorFilter param + URL searchParam
- `getAllStocks(params?: { sectorFilter?: string; indexFilter?: string })` — add optional params object. Keep zero-arg signature working (both filters default to undefined/null).
- SQL: add `AND ($sector::text IS NULL OR u.sector = $sector::text)` at the WHERE clause. Uses postgres-postgres tagged template with positional params.
- `stocks/page.tsx`: reads `searchParams.sector` (Next.js App Router server component). Passes it to `getAllStocks`.  Must be `async` page with `searchParams` prop typed as `Promise<{sector?: string}>` (Next.js 15 async searchParams).
- `StockScreener.tsx`: accepts new optional `initialSectorFilter?: string` prop. On mount (useEffect), if `initialSectorFilter` is set, seed the `sectorFilter` state and default sort to `within_state_rank` desc. Shows a dismissible banner "Filtering: Banking ✕" — clicking ✕ navigates to `/stocks` (clear URL param) and resets filter.
- `StocksClientShell.tsx`: receives `initialSectorFilter` from page and passes it to `StockScreener`.

### Part B: indexFilter param + IndexBadge linking
- Real index membership data exists (in_nifty_50/100/500 booleans). Part B is implementable.
- Add `indexFilter?: string` param to `getAllStocks` with `AND ($index::text IS NULL OR (CASE WHEN $index = 'Nifty 50' THEN u.in_nifty_50 WHEN $index = 'Nifty 100' THEN u.in_nifty_100 WHEN $index = 'Nifty 500' THEN u.in_nifty_500 ELSE FALSE END) = TRUE)`.
- `stocks/page.tsx`: also reads `searchParams.index`.
- `StockScreener.tsx`: shows "Filtering: Nifty 50 ✕" banner for index filter too.
- `StockDeepDiveHeader.tsx`: wrap `IndexBadge` renders in Next `<Link href="/stocks?index=Nifty 50">` etc.

## SQL driver: postgres-js template tags
The `sql` tagged template uses positional params. Pattern: `${value}` for safe interpolation. No SQL injection risk — values come from controlled URL params, validated server-side.

## Architecture
- Filter is applied server-side (fewer rows sent to client = correct).
- Client `StockScreener` also has its own `sectorFilter` dropdown — when `initialSectorFilter` is set from URL, it syncs that dropdown state to match. Both co-exist: URL param → seeds initial state, user can then further filter client-side.
- The `sectorFilter` state in StockScreener is seeded once on mount from prop, not re-derived on every render (avoids infinite loop).

## Edge cases
- NULL sector: `AND ($sector IS NULL OR u.sector = $sector)` handles both "no filter" and "filter present" cleanly.
- Empty string param: treat as no filter (`'' === undefined` check in page).
- Stocks with NULL sector in DB: they naturally disappear when a sector filter is active (correct behaviour — they have no sector).
- `StockScreener` already has a client-side `sectorFilter` dropdown; the URL-seeded value just pre-populates it, user can override or clear via the banner ✕.

## Files modified (only these)
- `frontend/src/lib/queries/stocks.ts` — add `sectorFilter` + `indexFilter` params
- `frontend/src/app/stocks/page.tsx` — read `?sector=` and `?index=` searchParams
- `frontend/src/components/stocks/StockScreener.tsx` — `initialSectorFilter`/`initialIndexFilter` props, banner
- `frontend/src/components/stocks/StocksClientShell.tsx` — pass initial filter props
- `frontend/src/components/stocks/StockDeepDiveHeader.tsx` — IndexBadge → Link
- New test file: `frontend/src/lib/queries/__tests__/stocks-filter.test.ts`
- New test file: `frontend/src/components/stocks/__tests__/StockScreenerFilter.test.tsx`

## Expected runtime
- No measurable change — 500-row table, single filter predicate on an indexed column.
