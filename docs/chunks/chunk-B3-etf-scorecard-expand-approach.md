# Chunk B.3: ETF Scorecard — Expand Universe + 3 New Columns

Date: 2026-05-27  
Status: approach

## Key findings from research

### Universe reality (vs spec)
- `atlas_universe_etfs` total: **126 rows**, but active (`effective_to IS NULL`): **34 rows**
- Inactive 92 rows are retired US ETFs (effective_to = 2026-05-13: IJR, EFA, VTI, XLP, etc.)
- `atlas_etf_scorecard` has **34 rows** — one per active ETF for snapshot_date=2026-05-22
- The spec's "126 rows" refers to total universe; the real target is 34 active ETFs with the 3 new cols populated

**Resolution**: The current writer already covers all 34 active ETFs. This task is purely about backfilling `premium_bps`, `te_60d`, and `adv_20d_inr` into the existing 34 rows + ensuring future runs populate them.

### Data availability (verified live on EC2)

| Column | Source | Coverage |
|--------|--------|----------|
| `adv_20d_inr` | `public.de_etf_ohlcv.close * volume` last 20 trading days | 34/34 (all active tickers have OHLCV) |
| `te_60d` | `atlas.atlas_etf_metrics_daily.ret_1d` (ETF) minus benchmark return from `atlas.atlas_benchmark_returns_cache.ret_1d` (NIFTY500 for Broad/Thematic, GOLD for Gold/Silver, MSCIWORLD for International, SP500 for MOM100/MAFANG) | ~22/34 (sectoral ETFs fall back to NIFTY500; linked_index codes like NIFTYBANK not in benchmark_returns_cache) |
| `premium_bps` | No ETF-specific NAV in any table (no ISIN on active ETFs, no de_mf_nav ETF match) | 0/34 — will be NULL best-effort |

### premium_bps situation
No ETF NAV data exists in the DB:
- `atlas_universe_etfs.isin` is NULL for all 34 active ETFs
- `de_mf_nav_daily` keyed by `mstar_id` (mutual funds, not ETF NSE tickers)
- `mf_nav_history` uses ISIN which is NULL for all active ETFs
- `de_etf_ohlcv` has market price (close) but no NAV separately

Decision: `premium_bps = NULL` for all rows with a `raw_metrics` reason flag `"premium_bps_no_nav_available"`. This is honest — ETF NAV is published by AMFI separately. Acceptable per spec ("flag if blocked").

### te_60d approach
- ETF daily returns: `atlas_etf_metrics_daily.ret_1d`  
- Benchmark daily returns: `atlas_benchmark_returns_cache.ret_1d`
- Benchmark mapping per THEME_BENCHMARK in `atlas/compute/etfs.py`:
  - Broad → NIFTY500
  - Gold → GOLD
  - Silver → NIFTY500 (no silver benchmark; existing code uses this)
  - International → MSCIWORLD (and SP500 for MAFANG/MOM100 — use MSCIWORLD as fallback)
  - Thematic → NIFTY500
  - Sectoral → NIFTY500 fallback (sector-specific indices not in benchmark_returns_cache)
- Window: last 60 trading days in atlas_etf_metrics_daily
- Formula: std(etf_ret_1d - bench_ret_1d) * sqrt(252), annualized
- Expected coverage: ~30/34 (4 ETFs may have incomplete 60d history)

### adv_20d_inr approach
- Source: `de_etf_ohlcv.close * volume` over last 20 trading days
- All 34 active tickers present in OHLCV
- Formula: SUM(close * volume over 20 days) / 20

## Implementation plan

### Files to modify/create

1. `atlas/inference/etf_scorecard.py` — Add:
   - `compute_premium_bps(market_close, nav) -> float | None` (clamp ±500 bps)
   - `compute_te_60d(etf_returns_60d, underlying_returns_60d) -> float | None` (annualized)
   - `compute_adv_20d_inr(volume_20d, close_20d) -> float` (sum/20)
   - `_load_extra_metrics_from_db(engine, snapshot_date)` — SQL query populating all extra_metrics including the 3 new cols
   - Add `premium_bps`, `te_60d`, `adv_20d_inr` to `ETFScoreRow` dataclass
   - Add these cols to `emit_upsert_sql()`

2. `scripts/etf_scorecard_expand.py` — EC2 runner that:
   - Calls `compute_etf_scorecard(snapshot_date, engine=engine)` which now loads all extra_metrics from DB
   - Executes upsert via live write

3. `tests/compute/test_etf_scorecard_new_cols.py` — TDD tests for the 3 pure functions

4. `docs/v6/audits/2026-05-27-B3-final.md` — Coverage report post-run

## Scale
- `atlas_etf_metrics_daily`: 280,077 rows — query with WHERE ticker = ANY([34 tickers]) AND date >= cutoff (60 rows per ticker = 2040 rows max)
- `de_etf_ohlcv`: 450,699 rows — query with WHERE ticker = ANY([34 tickers]) AND date >= cutoff (20 rows per ticker = 680 rows max)
- `atlas_benchmark_returns_cache`: small (<15K rows) — full table fits in memory

Expected runtime: <30 seconds on EC2.

## Edge cases
- NULL ret_1d in atlas_etf_metrics_daily: skip those dates in TE calc
- NULL in benchmark returns: skip those dates
- <60 days of data: TE calc returns NULL (not enough data)
- zero volume days in OHLCV: include them (0 traded value)
- Missing benchmark for ticker theme: fall back to NIFTY500
