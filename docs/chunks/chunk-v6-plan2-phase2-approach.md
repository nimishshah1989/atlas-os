# Chunk: v6 Plan 2 Phase 2 — Factor Returns + Residual Momentum

## Data scale (schema-inspected, not from DB — EC2 only)

- `public.de_equity_ohlcv`: ~2M+ rows per atlas-os experience; filtered by date + instrument_id
- `public.de_index_prices`: ~50K rows (limited index codes + dates); single-query safe
- `atlas_universe_stocks`: ~500-600 rows; fits in memory
- `atlas_factor_returns_daily`: 0 rows at start; target ~2,500 rows (2010-2026, trading days)
- `atlas_stock_metrics_daily`: large — query ret_1d only with date range filter

## Schema deviations found

- `atlas_universe_stocks` has NO `shares_outstanding` or `market_cap` column. Only `tier`
  (Large/Mid/Small/Micro enum). Using tier as size proxy for SMB.
- Raw OHLCV is in `public.de_equity_ohlcv` (JIP side), NOT in `atlas` schema.
  Columns: `instrument_id, date, open, high, low, close, close_adj, volume`.
- Nifty 500 index prices in `public.de_index_prices` with `index_code = 'NIFTY 500'`.
- `atlas_stock_metrics_daily` has `ret_1d` — use this for SMB/WML rather than recalculating
  from raw OHLCV (avoids loading the full OHLCV table per date).
- T-bill: use `atlas_macro_daily.risk_free_91d` when available, else 6%/252 = ~0.0002381/day.

## SMB proxy approach (no market cap → use tier)

Spec says "top-200-mcap quintile-1 (small) − quintile-5 (big)". Since no market_cap column
exists, we use `tier` as the size signal:
- Small = tier IN ('Small', 'Micro') → maps to spec's "quintile-1 small"
- Large = tier IN ('Large') → maps to spec's "quintile-5 big"
- SMB = mean(small-tier ret_1d) − mean(large-tier ret_1d) on each trading day

This is documented in the module as a tier-proxy. The mapping is directionally correct
(Large-cap stocks are the biggest by definition in NSE's tier structure).

## WML approach

Spec: "top-decile 12-1 momentum return − bottom-decile". Use `atlas_stock_metrics_daily.ret_12m_1m`
(the 12-1 momentum field) to rank stocks cross-sectionally. Top decile winners − bottom decile losers.
Require ≥10 stocks in universe for a valid WML observation.

## MKT excess approach

`mkt_excess = nifty500_daily_ret − risk_free_daily`. Nifty 500 daily return from
`public.de_index_prices`. T-bill from `atlas_macro_daily.risk_free_91d`; fallback 0.06/252.

## Chosen approach: SQL-heavy, pandas for OLS

- Factor returns compute: SQL per-date aggregate queries — small result sets, no full table scans
- Backfill: date loop with INSERT ... ON CONFLICT DO UPDATE; ~2,500 iterations × 3 queries each
- Residual momentum: OLS via numpy.linalg.lstsq, one stock at a time (252 obs × 3 factors)
  Build the design matrix once per (instrument_id, date) from DB; vectorize the matrix fill
  across stocks by loading the full 252d factor returns once per invocation, then iterating stocks

## Wiki patterns applied

- Idempotent Upsert: ON CONFLICT DO UPDATE on `atlas_factor_returns_daily.date` (PK)
- Computation Boundary: numpy internally, Decimal at SQL storage boundary
- Per-Day Query Loop anti-pattern AVOIDED: load full date ranges, not per-day

## Expected runtime (t3.large EC2)

- Backfill 2010-2026 (~2,500 trading days):
  - 3 SQL queries per day (Nifty return, smb per-tier, wml rank) = ~7,500 queries
  - Batched with chunking (monthly chunks of ~20 days each) = ~125 chunks
  - Est: ~5-10 minutes on EC2 with Postgres on same network

- Residual momentum compute per rebalance date:
  - Load 252d × ~500 stocks ret_1d from `atlas_stock_metrics_daily` = 1 SQL
  - Load 252d factor returns = 1 SQL
  - OLS per stock (500 stocks × lstsq on 231×3 matrix) ≈ 0.2s per rebalance date

## Edge cases

- NULL ret_1d in `atlas_stock_metrics_daily`: skip that date for that stock in OLS regression
- Missing Nifty 500 close: log warning, skip that date in backfill (no row written)
- 0 stocks in small/large tier on a date: return NULL for SMB (not 0.0)
- Fewer than 10 stocks with valid ret_12m_1m: return NULL for WML
- T-bill NULL: use 0.06/252 fallback (logged)
- OLS: if stock has <21 non-null days in the window, skip (cannot reliably fit 3 betas)

## Files

- `atlas/trading/v6/signals/factor_returns.py` (≤600 LOC)
- `scripts/v6_factor_returns_backfill.py`
- `atlas/trading/v6/signals/residual_momentum.py` (≤600 LOC)
- `tests/trading/v6/signals/test_factor_returns.py` (≤800 LOC)
- `tests/trading/v6/signals/test_residual_momentum.py` (≤800 LOC)
