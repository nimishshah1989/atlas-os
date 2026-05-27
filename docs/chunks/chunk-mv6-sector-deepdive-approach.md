# Approach: MV 6 of 9 — `atlas.mv_sector_deepdive`

**Date**: 2026-05-27
**Chunk**: mv-sector-deepdive (migration 105)
**Revises**: 104 (mv_sector_rrg)

---

## Data Scale

Source tables (row counts from migration docstrings):

| Table | Rows | Notes |
|---|---|---|
| atlas_sector_metrics_daily | 74,752 | 31 sectors × 2,412 trading days |
| atlas_sector_states_daily | ~74,752 | same spine |
| atlas_universe_stocks | 750 | current-only filter: effective_to IS NULL |
| atlas_stock_metrics_daily | ~1.16M | large table (2020+ filtered to ~750K) |
| atlas_stock_states_daily | ~1.16M | same spine as stock_metrics |
| atlas_signal_calls | ~363+ | open calls only (exit_date IS NULL) |
| atlas_stock_conviction_daily | ~300K+ | per-stock daily conviction |

**Output: ONE row per sector, ~30 rows total (LATEST snapshot only).**

---

## Chosen Approach

### Why LATEST-only (vs full historical)

The spec says: "ONE row per sector (LATEST snapshot only — 30 rows total). The 04a page renders for a single sector at a time; historical drill is not in scope."

This fundamentally changes the query profile vs MVs 3-5. Instead of building 48,050 rows with window functions over the full 2020+ spine, we:
1. Pre-compute MAX(date) once per source table
2. Filter every CTE to that single date
3. Aggregate across ~750 stocks on that one date

Expected output: ~30 rows. Refresh time target: <10s.

### JSONB Section Design

Six JSONB sections per row:

1. **`returns`** (object): 1W/1M/3M/6M/12M absolute sector returns
   - Source: `atlas_sector_metrics_daily` (bottomup_ret_*) + `atlas_index_metrics_daily` for 1W/12M back-derivation
   - NULL propagated, never zeroed

2. **`rs_windows`** (object): RS vs Nifty 500 for 1W/1M/3M/6M/12M
   - Source: `atlas_sector_metrics_daily` rs_* columns
   - NULL propagated

3. **`constituents_top30`** (array, up to 30 elements): top stocks by composite_score per sector
   - Per-stock: {symbol, company_name, tier, ret_1w, ret_1m, ret_3m, ret_6m, rs_3m_nifty500, vol_60d, rs_state, composite_score, confidence_band, action}
   - Source: atlas_stock_metrics_daily JOIN atlas_universe_stocks JOIN atlas_stock_conviction_daily JOIN atlas_stock_states_daily
   - ROW_NUMBER() within sector by composite_score DESC, then LIMIT 30 with WHERE rn <= 30
   - No correlated subqueries: single pass

4. **`open_signals`** (array): open BUY/SELL signal calls in this sector
   - Per-signal: {symbol, company_name, action, tenure, cap_tier_at_trigger, confidence_unconditional, date}
   - Source: atlas_signal_calls JOIN atlas_universe_stocks
   - Filter: exit_date IS NULL AND action IN ('POSITIVE','NEGATIVE')

5. **`strength_dist`** (object): {very_strong, strong, neutral, weak, very_weak} counts from NTILE(5) on ret_3m
   - Lifted from mv_sector_breadth pattern (migration 103)
   - NTILE(5) on latest-date per-stock ret_3m within sector

6. **`top_picks_top10`** (array): top 10 by composite_score with positive conviction
   - Subset of constituents_top30 filtered to composite_score > 0
   - Includes: {symbol, company_name, composite_score, confidence_band, action}

### Performance Strategy

- All CTEs filter to `latest_stock_date` or `latest_sector_date` — a single MAX(date) anchor
- No correlated subqueries on large tables
- constituents_top30: ROW_NUMBER() window over ~750 rows on one date — trivial
- strength_dist: NTILE(5) over ~750 rows on one date — trivial
- open_signals: atlas_signal_calls has ~363 rows total, small
- Final assembly: LEFT JOIN on 30-row sector spine

Expected: <5s refresh on Supabase managed Postgres.

---

## Wiki Patterns Checked

- Migration 103 (mv_sector_breadth): NTILE/ROW_NUMBER pattern, strength_dist shape
- Migration 104 (mv_sector_rrg): LATERAL trail assembly (NOT used here — not needed for latest-only)
- Migration 102 (mv_sector_cards): sector_state column name, signal aggregation join path
- Migration 097 (mv_stock_list_v6): composite_score formula, confidence_band mapping, rs_state usage

---

## Existing Code Being Reused

- `composite_score = (conviction_score - 0.5) * 20` from migration 097
- `confidence_band` mapping (industry_grade→H, baseline→M, descriptive_only→L) from migration 097
- Signal join path: `signal_calls → atlas_universe_stocks.instrument_id` from migration 102
- `sector_state` column from `atlas_sector_states_daily` (migration 005)
- `rs_state` from `atlas_stock_states_daily` for weinstein analog

---

## Column Naming Reference

| Table | Column Used | Notes |
|---|---|---|
| atlas_universe_stocks | sector, tier, symbol, company_name, instrument_id, effective_to | `sector` not `sector_name`; `tier` not `cap_tier` |
| atlas_sector_metrics_daily | date, sector_name, bottomup_ret_1m/3m/6m, rs_1w/1m, bottomup_rs_3m_nifty500, rs_6m/12m | |
| atlas_sector_states_daily | date, sector_name, sector_state | |
| atlas_stock_metrics_daily | date, instrument_id, ret_1w/1m/3m/6m, rs_3m_nifty500, realized_vol_63 | |
| atlas_stock_states_daily | date, instrument_id, rs_state | Weinstein analog |
| atlas_stock_conviction_daily | date, instrument_id, conviction_score, confidence_label | composite_score derived |
| atlas_signal_calls | date, instrument_id, action, tenure, cap_tier_at_trigger, confidence_unconditional, exit_date | |
| atlas_index_metrics_daily | date, index_code='NIFTY 500', ret_1w, ret_12m | For 1W/12M sector returns |

---

## Edge Cases

- NULLs: All financial values NULL-propagated (CASE WHEN IS NOT NULL, NULLIF, COALESCE only for counts)
- Sectors with < 30 stocks: constituents_top30 will have fewer elements — valid
- Sectors with no open signals: open_signals = '[]'
- Sectors with all NULL ret_3m: strength_dist counts will all be 0
- Latest date mismatch between sector_metrics and stock_metrics: handled by separate MAX(date) CTEs joined to spine on LEFT JOIN

---

## Expected Runtime

- REFRESH: <5s (30 rows output, all per-sector aggregation at single latest date)
- Cron: 20:55 IST (15:25 UTC) — after mv_sector_rrg at 20:50
