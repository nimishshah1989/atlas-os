# Chunk C.10 — SectorBreadthPanel Approach

## Data scale
- `atlas_scorecard_daily`: checked via migrations — single snapshot row per instrument per date.
  ~750 instruments, one row per day — expected ~250K rows after backfill.
- No `atlas_sector_breadth_daily` table exists (confirmed A.0 audit).
- No `market_cap_cr` column on `atlas_universe_stocks` (migration 002 confirms only:
  instrument_id, symbol, company_name, tier, sector, industry, in_nifty_50/100/500,
  listing_date, effective_from, effective_to). top3_concentration_pct = "0.00" + TODO.

## Feature key discovery
- `dist_above_sma20` does NOT exist in scorecard features JSONB.
- Available SMA features in JSONB: `dist_above_sma50`, `dist_above_sma200`.
- For SMA20 proxy: use `rs_residual_1m` (21-day RS residual). Actually EMA20 
  breadth (above/below EMA20) approximated via `dist_above_sma50` comparison.
- Wait — the task spec says `dist_above_sma20` from features. Per `atlas/features/__init__.py`
  lines 77-79, `ema_20` IS in the feature list. The deep_search_features.py shows `sma50` 
  but NOT `sma20`. However the scorecard_writer lines 94-96 list `rs_residual_3m/6m/12m`
  and line 114 lists `rs_residual_1m`. There is NO dist_above_sma20 in actual features.
- Decision: use `dist_above_sma50` as above_20 proxy (with a TODO comment) so the
  component gracefully degrades. SQL will attempt `dist_above_sma20` first, COALESCE 
  to `dist_above_sma50` if NULL.
- For dispersion σ: use `rs_residual_1m` (the 1-month RS residual, present in JSONB).
- For ret_1m (dispersion): rs_residual_1m is available in features JSONB.

## Chosen approach
- SQL query with CTE: latest date → universe join → per-sector aggregation.
- above_20/50/200: COALESCE dist_above_smaXX (may be NULL for newer stocks) > 0.
- dispersion: STDDEV(rs_residual_1m) per sector (cross-sectional σ).
- top3_concentration: "0.00" with TODO (no market_cap column).
- No Python processing beyond row mapping.
- All numeric values stringified (::text) as per SectorBookExposure pattern.

## Existing patterns reused
- Query pattern: `sector_book_exposure.ts` (CTE, optional sector filter, ::text cast)
- Component pattern: `SectorBookStrip.tsx` (signal-pos/warn/neg classes, formatPct)
- Test pattern: `SectorBookStrip.test.tsx` (render + DOM assertions)

## Edge cases
- NULL dist_above_sma50: CASE WHEN .. ELSE 0 END via COALESCE.
- STDDEV on single-stock sector: COALESCE(STDDEV(..), 0).
- Empty sector filter: returns [].
- as_of_date: returns the actual MAX(date), never the requested date.

## LOC estimates
- sector_breadth.ts: ~130 LOC (well under 220 limit)
- SectorBreadthPanel.tsx: ~150 LOC (well under 200 limit)
- Test files: ~200 LOC each (under 250 limit)

## Expected runtime
- t3.large: query aggregates ~750 rows → milliseconds. No EXPLAIN ANALYZE needed.
