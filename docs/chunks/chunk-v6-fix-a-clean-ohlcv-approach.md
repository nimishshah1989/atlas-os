# Chunk: Fix A — Clean OHLCV view for v6 signals

## Problem
`de_equity_ohlcv` has ~150 corrupt rows/year where futures/index prices were
inserted for equity tickers (e.g. SBIN 2020-05-25 close=11,000 vs neighbors
~151). These produce ret_1d of 71x, inflating v6 backtest CAGR.

## Data scale
`de_equity_ohlcv` — large table (~10M+ rows); not loading into Python.

## Approach
1. Create `atlas.atlas_v6_clean_ohlcv` as a Postgres VIEW (not materialized) via
   migration 088. The view excludes rows where:
   - `abs(close / prev_close - 1) > 0.25` AND `volume < 1000`
   Both together = "big return on no volume" = erroneous price signature.
   A CTE computes `LAG(close)` over (symbol ORDER BY date) once; the WHERE
   filters on that. First row per symbol (prev_close IS NULL) is always kept.

2. Update `atlas/trading/v6/universe.py` to query `atlas.atlas_v6_clean_ohlcv`
   instead of `public.de_equity_ohlcv`. This is the only v6/ file that directly
   queries that table — all other v6 code reads from `atlas_stock_metrics_daily`.

## Wiki patterns checked
- View-as-filter pattern used in 084-086 unified views (same repo)
- `de_equity_ohlcv` partitioned by year — view sits above partitions, no change needed

## Existing code reused
- Migration structure copied from 087_v6_prerequisites.py
- `universe.py` query updated in-place (surgical change to one string)

## Files changed
- `migrations/versions/088_v6_clean_ohlcv_view.py` (new)
- `atlas/trading/v6/universe.py` (update table reference in SQL string)

## Edge cases
- First row per symbol: prev_close IS NULL → always kept (correct)
- NULLIF(prev_close, 0) → guards zero prev_close (division safety)
- volume = 0 or NULL: `volume >= 1000` is FALSE for NULL → corrupt rows with
  NULL volume and big return are correctly dropped. NULL-safe because the AND
  condition: if volume IS NULL, the row is only dropped if the return condition
  ALSO fires.
- The view is not materialized — reads through to live partition data each query.
  This is fine: universe.py is called monthly (12× per backtest year), not on
  every trading day.

## Expected dropped rows
~150-300/year × ~10 years = 1,500-3,000 rows (< 0.05% of table).

## Expected runtime
View creation: instantaneous. Per-query overhead: minimal (LAG is a window
function over the filtered date range, not the full table — universe.py always
adds `WHERE date BETWEEN :s AND :e`).
