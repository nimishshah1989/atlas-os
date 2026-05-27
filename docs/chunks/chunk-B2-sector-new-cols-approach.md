# Chunk B.2 Approach: Sector 8 New Columns + 5-Year Backfill

## Actual Data Scale

- `atlas_stock_metrics_daily`: 1,392,776 rows (stock-level computed metrics)
- `atlas_sector_metrics_daily`: 74,752 rows (31 sectors × ~2575 trading days)
- `de_equity_ohlcv`: 4,747,445 rows (raw OHLCV, needed for 52wh compute)
- `atlas_index_metrics_daily`: ~2,246 rows for Nifty 500 (has ret_6m, ret_12m)

## New Columns

| Column | Source | Computation |
|---|---|---|
| `rs_1w` | stock ret_1w vs nifty500 ret_1w | sector_ret_1w − n500_ret_1w (simple diff, not price-relative, to match existing bottomup_rs pattern) |
| `rs_1m` | stock ret_1m vs nifty500 ret_1m | sector_ret_1m − n500_ret_1m |
| `rs_6m` | stock ret_6m vs nifty500 ret_6m | sector_ret_6m − n500_ret_6m |
| `rs_12m` | stock ret_12m vs nifty500 ret_12m | sector_ret_12m − n500_ret_12m |
| `pct_above_ema20` | ema_20_ratio > 1 | fraction of sector constituents with ema_20_ratio > 1 |
| `pct_above_ema200` | extension_pct > 0 | fraction of sector constituents with extension_pct > 0 (close > ema200) |
| `pct_52wh` | close vs 52w rolling max | fraction within 5% of rolling 252-day close high (from de_equity_ohlcv) |
| `hhi` | traded value proxy | Herfindahl-Hirschman index using traded value (avg_volume_20 × close_approx) as market cap proxy |

## Design Decisions

### RS windows (rs_1w/1m/6m/12m)
- Simple difference: `sector_bottom_up_ret_W − nifty500_ret_W`
- Rationale: Spec says "sector return - Nifty500 return", which is a simple difference
- Source: weighted-mean of constituent `ret_1w/1m/6m/12m` (already in stock_metrics) minus Nifty500 index ret from `atlas_index_metrics_daily`
- All already computed in `compute_bottom_up_sector_metrics` — just need to expose `ret_6m/12m` weights and subtract n500

### EMA breadth (pct_above_ema20/200)
- `ema_20_ratio > 1` means close > ema20 (confirmed column semantics)
- `extension_pct > 0` means close > ema200 (ema_200_stock × (1 + ext) > ema_200_stock iff ext > 0)
- Both columns are non-null for ~89% of stock rows
- SQL-side aggregation per sector/date

### 52-week high proximity (pct_52wh)
- `de_equity_ohlcv` has `close_adj` for all dates
- Compute 252-day rolling max of close_adj per instrument, then fraction within 5%
- Must pull OHLCV with 252-day lookback per batch year
- At 4.7M rows total in OHLCV (manageable with SQL window function)
- Use SQL: `MAX(close_adj) OVER (PARTITION BY instrument_id ORDER BY date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW)` then compute in Python

### HHI (Herfindahl-Hirschman Index)
- `de_market_cap_history` is EMPTY (0 rows, confirmed)
- Use traded value proxy: `avg_volume_20 × close_approx` as market cap proxy
- This is the same proxy used in `_compute_traded_value_weight` — consistent
- HHI = sum(s_i^2) where s_i = share of constituent i in sector total traded value
- Range: [1/n, 1]. Higher = more concentrated. Normalize: not needed, keep raw HHI

## Implementation Strategy

### SQL vs Python
- **RS windows**: SQL aggregation to get weighted ret_6m/12m per sector/date, then subtract n500
- **EMA breadth**: SQL COUNT FILTER per sector/date (pure SQL, tiny result)
- **52wh**: SQL window function for rolling max, then Python fraction per sector/date
- **HHI**: SQL sum of squares per sector/date after computing shares

### Scale: Year-by-year batching
- Load 1 year of stock data at a time (~120K rows per year)
- For 52wh: load year + 252-day lookback from OHLCV
- UPSERT into sector_metrics_daily on (date, sector_name) PK

## Existing Patterns Reused
- `_compute_traded_value_weight` for HHI weight denominator
- `load_sector_stock_data` for constituent data loading
- `bulk_upsert` from `atlas.compute._session`
- Year-by-year batch loop from other backfill scripts

## Edge Cases
- NULLs in ret_12m (early history, warm-up): exclude from mean, if all NULL → sector rs_12m = NULL
- HHI with 0 total weight: → NULL
- pct_52wh: stocks missing from OHLCV → exclude from denominator
- Sector with 0 constituents → NULL all metrics for that date

## Expected Runtime
- 10 years × ~31 sectors × ~250 trading days = 74,752 rows to upsert
- SQL computation per year batch: < 30 seconds
- Total expected: 10-15 minutes on t3.large

## Files
- `atlas/compute/sectors.py` — add 4 new functions (extend, file already has allow-large comment)
- `tests/compute/test_sectors_new_cols.py` — new test file
- `scripts/sector_5y_backfill.py` — EC2 runner
- `docs/v6/audits/2026-05-27-B2-final.md` — coverage audit
