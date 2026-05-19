# Chunk: Fix C — Backfill missing signal columns in atlas_stock_metrics_daily

## Data scale (verified 2026-05-19)

| Table | Rows |
|---|---|
| atlas_stock_metrics_daily | 1,390,535 |
| de_equity_ohlcv (2022) | 412,356 |
| atlas_benchmark_returns_cache (NIFTY500) | 2,493 |

- 750 distinct instruments, 2016-04-07 to 2026-05-18
- rs_3m_nifty500: 0 non-null (never populated — schema placeholder)
- rs_1w_nifty500, rs_1m_nifty500: also 0 non-null (same issue)
- 2022 Jan-Nov: ret_12m / ema_200_stock / max_drawdown_252 all NULL (~137,000 rows)
- 2016: all three also NULL (expected — lookback not available)

## Root cause

1. **rs_*_nifty500**: The `atlas/compute/stocks.py` pipeline computes `rs_*_tier`
   (vs tier benchmark, e.g. Nifty Midcap150) but never computes `rs_*_nifty500`.
   Only `indices.py` and `sectors.py` compute nifty500-relativised RS.
   The columns exist in the schema (migration 004) but were never populated.

2. **2022 gaps**: The compute engine was likely run in a partial/incremental mode
   that only processed ~Dec 2022 onward for some instruments. Jan-Nov 2022 shows
   0 values for all three long-lookback columns across all 750 instruments.
   Price data exists in de_equity_ohlcv for 2022.

## Chosen approach

### rs_3m_nifty500 (and rs_1w, rs_1m): Pure SQL UPDATE

Formula (from indices.py line 272-278):
  rs_3m_nifty500 = (1 + ret_3m) / (1 + nifty500_ret_3m) - 1

- stock ret_3m is already in atlas_stock_metrics_daily
- nifty500 ret_3m is in atlas_benchmark_returns_cache WHERE benchmark_code = 'NIFTY500'
- Single UPDATE with a JOIN: zero Python memory, runs server-side
- Guard: bench_ret = -1 (impossible in practice but guard with NULLIF)
- Expected coverage: 1,390,535 rows, minus early-date rows where ret_3m is NULL

### 2022 gaps (ret_12m / ema_200_stock / max_drawdown_252)

For 2022 Jan-Nov (~137,000 rows), we need stock prices going back 252 trading days.
Matrix-wide pandas approach (wiki: matrix-wide-risk-backfill):
- Load de_equity_ohlcv from 2021-01-01 to 2022-11-30 (wide date range for lookback)
- Pivot wide (dates × instruments)
- Compute pct_change for daily returns
- ret_12m: close_ratio - 1 using LAG(252) equivalent → rolling 252-period shift
- ema_200_stock: ewm(span=200) per instrument (recursive, must use pandas)
- max_drawdown_252: rolling 252 window, (price/cummax - 1).min()
- Write back via COPY to temp table + UPDATE FROM staging

Why matrix-wide over SQL:
- EMA is recursive, cannot be expressed as a SQL window function efficiently
- max_drawdown_252 requires nested window which PostgreSQL rejects
- 412k rows for 2022 price data fits in ~200MB wide, well under 8GB RAM

Why not re-run the full compute engine:
- Engine runs per-instrument in batches, would recompute 750+ instruments
  with overlapping lookback. Direct backfill is surgical.

## Wiki patterns applied

- SQL Window Computation: for rs_3m_nifty500 (pure SQL, zero Python memory)
- Matrix-Wide Risk Backfill: for 2022 EMA/drawdown gaps
- Computation Boundary: numpy internally, Decimal(str(round())) at write boundary
- Idempotent Upsert: WHERE IS NULL guards prevent double-write

## Edge cases

- 2016: will remain NULL (ret_12m needs 252 trading days of history; earliest
  data is 2016-04-07, so 12m lookback unavailable until ~2017-04-07). Expected.
- Early 2017: some NULLs for young instruments (< 252 days history). Expected.
- NIFTY500 dates not matching stock dates (holidays): LEFT JOIN means stock gets
  NULL rs_3m_nifty500 for those dates. Acceptable — same logic as indices.py.
- bench_ret_3m = -1.0: NULLIF guard prevents division by zero.
- instrument_id not in de_equity_ohlcv for some 2022 dates: pandas dropna
  handles gracefully.

## Expected runtime on t3.large

- rs_3m_nifty500 SQL UPDATE: ~2-4 minutes (1.39M row UPDATE with JOIN)
- 2022 matrix backfill: ~5-8 minutes (load 412k rows + pivot + compute + write)
- Total: ~10-12 minutes

## Files to create

- `scripts/v6_signal_columns_backfill.py` — the backfill script
