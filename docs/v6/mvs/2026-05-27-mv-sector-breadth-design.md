# MV 4 of 9 — `atlas.mv_sector_breadth` Design

**Date**: 2026-05-27
**Migration**: 103
**Revises**: 102

---

## Purpose

Serves Page 04 Sectors breadth visualizations:
- Breadth waterfall: % of sector constituents above their EMA per lookback window (1W / 1M / 3M / 6M)
- Strength distribution: very_strong / strong / neutral / weak / very_weak constituent counts
- Top/bottom movers: top 5 and bottom 5 stocks by latest return
- EMA-level breadth scalars: pct_above_ema20, pct_above_ema50, pct_above_ema200, pct_at_52wh

---

## Row Shape

ONE row per `(as_of_date, sector_name)`.

Scale: ~31 sectors x ~1,550 trading days (2020-01-01 onward) = ~48,050 rows.

---

## Data Scale Analysis

Source table row counts (from existing migrations):
- `atlas.atlas_sector_metrics_daily`: 74,752 rows (31 sectors x ~2,412 days backfilled)
- `atlas.atlas_stock_metrics_daily`: large (750 stocks x ~1,550 days = ~1.16M rows for filtered range)
- `atlas.atlas_universe_stocks`: 750 rows (current snapshot)

Decision: SQL with window functions for all aggregations. No Python loading. The per-stock breadth
counts (positive return per window) are computed via COUNT/CASE in SQL with GROUP BY sector+date.
The top/bottom movers JSONB uses `jsonb_agg(jsonb_build_object(...) ORDER BY ret DESC)` window-
side, then sliced to 5. Full SQL computation — zero Python orchestration.

---

## Columns

### Scalars (from `atlas_sector_metrics_daily`)
- `pct_above_ema20` — % constituents above 20-day EMA (from `atlas_sector_metrics_daily.pct_above_ema20`)
- `pct_above_ema50` — % constituents above 50-day EMA (from `atlas_sector_metrics_daily.participation_50`)
- `pct_above_ema200` — % constituents above 200-day EMA (from `atlas_sector_metrics_daily.pct_above_ema200`)
- `pct_at_52wh` — % constituents at 52-week high (from `atlas_sector_metrics_daily.pct_52wh`)
- `constituent_count` — live count from `atlas_universe_stocks` (current snapshot)

### JSONB: `breadth_by_window`
Array of 4 objects, one per lookback window:
```json
[
  {"window": "1W", "pct_positive": 0.72, "pct_top_decile_movers": 0.10},
  {"window": "1M", "pct_positive": 0.64, "pct_top_decile_movers": 0.10},
  {"window": "3M", "pct_positive": 0.58, "pct_top_decile_movers": 0.10},
  {"window": "6M", "pct_positive": 0.51, "pct_top_decile_movers": 0.10}
]
```
- `pct_positive`: % of sector stocks with positive return for that window (ret_Nw > 0)
- `pct_top_decile_movers`: % of sector stocks in top decile (top 10% by return for that window within the sector)

Source: `atlas_stock_metrics_daily` (ret_1w, ret_1m, ret_3m, ret_6m) joined to
`atlas_universe_stocks` for sector mapping.

### JSONB: `breadth_by_strength`
Distribution of constituent strength states for latest date:
```json
{"very_strong": 8, "strong": 14, "neutral": 22, "weak": 11, "very_weak": 7}
```
Computed by bucketing stocks on `ret_3m` quintiles (sector-relative on that date):
- very_strong: top quintile (p80-p100)
- strong: p60-p80
- neutral: p40-p60
- weak: p20-p40
- very_weak: bottom quintile (p0-p20)

### JSONB: `top_movers`
Top 5 stocks by `ret_1m` (latest date):
```json
[{"symbol": "RELIANCE", "ret_pct": 6.8}, ...]
```

### JSONB: `bottom_movers`
Bottom 5 stocks by `ret_1m` (latest date):
```json
[{"symbol": "SBIN", "ret_pct": -9.2}, ...]
```

---

## Source Tables

1. `atlas.atlas_sector_metrics_daily` — pct_above_ema20, pct_above_ema200, participation_50, pct_52wh
2. `atlas.atlas_universe_stocks` — sector mapping (effective_to IS NULL)
3. `atlas.atlas_stock_metrics_daily` — ret_1w, ret_1m, ret_3m, ret_6m per stock per date

---

## SQL Approach

### CTE Chain

1. **spine** — date + sector spine from `atlas_sector_metrics_daily` (2020-01-01+)
2. **sector_breadth_scalars** — pct_above_ema20/50/200, pct_at_52wh, participation_50 from `atlas_sector_metrics_daily`
3. **constituent_counts** — live count from `atlas_universe_stocks` (current snapshot)
4. **stock_returns** — join `atlas_stock_metrics_daily` to `atlas_universe_stocks` for sector + ret_1w/1m/3m/6m
5. **breadth_by_window_agg** — COUNT CASE aggregations per (sector, date) for each window
6. **strength_dist_agg** — NTILE(5) over (PARTITION BY sector, date ORDER BY ret_3m) for quintile distribution
7. **movers_agg** — TOP 5 / BOTTOM 5 by ret_1m per (sector, date) via jsonb_agg + subquery slice

### NULL handling
- All ret_* NULL checks: COUNT CASE skips NULLs implicitly (standard SQL COUNT behavior)
- pct_positive = NULL when no stocks have non-NULL returns for that window (no zeros)
- COALESCE used for constituent_count (0 if no universe mapping)
- JSONB arrays: NULL movers arrays handled via COALESCE to '[]'::jsonb

---

## Refresh Schedule

- cron job name: `mv_sector_breadth_nightly`
- Schedule: `45 14 * * *` (20:45 IST = 14:45 UTC)
- CONCURRENTLY requires unique index on (as_of_date, sector_name)

---

## Expected Runtime

On t3.large (2 vCPU, 8GB RAM):
- Full initial REFRESH: ~60-90 seconds (joins across ~1.16M stock-metrics rows)
- Nightly incremental: SQL still does full MV rebuild (MVs don't support partial refresh)
- Acceptable — runs at 20:45 IST after mv_sector_cards (20:40 IST)

---

## Edge Cases

- Sectors with < 5 stocks: top/bottom movers returns fewer than 5 items (correct behavior)
- Stocks with NULL ret_1m: excluded from pct_positive numerator AND denominator
- pct_52wh: can be NULL before migration 097 backfill date — propagated as NULL
- participation_50: can be NULL before M3 backfill — propagated as NULL, aliased as pct_above_ema50
- Dates before stock_metrics_daily data: breadth_by_window will have NULL pct_positive values

---

## Wiki Patterns Referenced

- SQL Window Computation — all aggregations done in SQL
- Idempotent Upsert — CREATE MATERIALIZED VIEW follows WITH NO DATA pattern
- Decimal in JSONB — all float values in JSONB are cast to numeric before round
