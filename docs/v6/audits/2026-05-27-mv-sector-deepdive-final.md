# Audit: `atlas.mv_sector_deepdive` (Migration 105)

**Date**: 2026-05-27
**Status**: READY FOR PARENT APPLY

---

## Pre-flight Checklist

### Schema / DDL

- [x] MV named exactly `atlas.mv_sector_deepdive`
- [x] `WITH NO DATA` at end of CREATE statement
- [x] Unique index on `(sector_name)` — `uix_mv_sector_deepdive_sector_name`
- [x] `REFRESH MATERIALIZED VIEW atlas.mv_sector_deepdive` in upgrade()
- [x] pg_cron scheduled at 20:55 IST (`25 15 * * *`) as `mv_sector_deepdive_nightly`
- [x] `REFRESH MATERIALIZED VIEW CONCURRENTLY` in cron body (unique index required, present)
- [x] downgrade() unschedules cron before dropping index before dropping MV

### Data Integrity

- [x] Row shape: ONE row per sector_name (~30 rows). Not historical — LATEST snapshot only.
- [x] No financial values zeroed on NULL — all use CASE WHEN IS NOT NULL or explicit NULL propagation
- [x] `effective_to IS NULL` filter on atlas_universe_stocks in all relevant CTEs
- [x] `exit_date IS NULL` filter on atlas_signal_calls (open signals only)
- [x] All return values multiplied by 100 for display (fractions → percentages), rounded to 2dp
- [x] composite_score formula verified: `(conviction_score - 0.5) * 20` — matches migration 097
- [x] confidence_band mapping verified: industry_grade→H, baseline→M, descriptive_only→L

### Performance Guard

- [x] All CTEs filtered to MAX(date) anchor — no full-table window passes
- [x] No correlated subqueries scanning large tables per sector row
- [x] ROW_NUMBER() and NTILE(5) operate over ~750 rows at one date (trivially fast)
- [x] open_signals join is on small table (~363 rows total)
- [x] Expected REFRESH: <5s (30 output rows, all aggregation at single date)

### JSONB Sections

- [x] `returns`: 5 windows (1W/1M/3M/6M/12M), 1W and 12M back-derived from RS + Nifty 500
- [x] `rs_windows`: 5 windows (1W/1M/3M/6M/12M) vs Nifty 500
- [x] `constituents_top30`: top 30 by composite_score, 13-key per-stock JSONB objects
- [x] `open_signals`: open POSITIVE/NEGATIVE calls only, 7-key per-signal JSONB objects
- [x] `strength_dist`: 5-key object (very_strong/strong/neutral/weak/very_weak)
- [x] `top_picks_top10`: top 10 by composite_score WHERE composite_score > 0

### Column Naming (verified against source migrations)

- [x] `atlas_universe_stocks`: uses `sector` (not `sector_name`), `tier` (not `cap_tier`)
- [x] `atlas_sector_metrics_daily`: uses `bottomup_rs_3m_nifty500` (not `rs_3m_nifty500`)
- [x] `atlas_sector_states_daily`: uses `sector_state` (not `verdict`)
- [x] `atlas_stock_metrics_daily`: uses `rs_3m_nifty500`, `realized_vol_63`, `ret_1w/1m/3m/6m`
- [x] `atlas_stock_states_daily`: uses `rs_state` (Weinstein analog)

### Tests

- [x] 50 unit tests pass, 0 failures
- [x] Integration tests written (13), skipped pending EC2 apply
- [x] ruff E,F,W: 0 errors
- [x] Test covers: metadata, SQL content, JSONB section keys, upgrade/downgrade op order

---

## Concerns / Open Items

**Market cap aggregate excluded (known gap)**: The spec calls for market cap aggregate from `public.de_market_cap_history`. This table is confirmed empty as of 2026-05-27 (see `atlas/compute/sectors.py` lines 283 and 1059). The MV omits market cap aggregate rather than returning all-NULL values. When the table is populated, a follow-up migration should add `market_cap_aggregate_lakh_cr` to the MV.

**atlas_scorecard_daily vs atlas_stock_conviction_daily**: The spec mentions `atlas_scorecard_daily` for top_picks composite_score. The v6 schema `atlas_scorecard_daily` (migration 080) has no `composite_score` column. Migration 097 established the canonical approach: composite_score is derived from `atlas_stock_conviction_daily.conviction_score` via `(score - 0.5) * 20`. This MV follows migration 097's pattern.

---

## Apply Instructions (for parent agent)

1. Execute `_CREATE_MV` SQL string via `supabase.execute_sql`
2. Execute `_CREATE_UNIQUE_INDEX` SQL string
3. Execute `_REFRESH_MV` SQL string (initial full build)
4. Execute `_CRON_SCHEDULE` SQL string

The migration strings are in:
`/Users/nimishshah/Documents/GitHub/atlas-os/migrations/versions/105_mv_sector_deepdive.py`
