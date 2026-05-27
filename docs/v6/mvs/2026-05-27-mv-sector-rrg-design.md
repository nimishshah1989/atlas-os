# MV 5 of 9 — `atlas.mv_sector_rrg` Design

**Date**: 2026-05-27
**Migration**: 104
**Revises**: 103

---

## Purpose

Serves Page 04 Sectors — Relative Rotation Graph (RRG) visualization:
- Today's sector position on the 4-quadrant RRG plane (X = rs_ratio, Y = rs_momentum)
- 6-week trailing path per sector so the user sees trajectory/rotation direction
- Quadrant label for color-coding and filtering

---

## Row Shape

ONE row per `(as_of_date, sector_name)`.

Scale: ~31 sectors x ~1,550 trading days (2020-01-01 onward) = ~48,050 rows.

---

## Data Scale Analysis

Source table row counts:
- `atlas.atlas_sector_metrics_daily`: 74,752 rows (31 sectors x ~2,412 trading days backfilled to pre-2020)
- 2020+ filter reduces to ~48,050 rows — well within SQL window function territory (no Python needed)

---

## Source

Single source: `atlas.atlas_sector_metrics_daily.bottomup_rs_3m_nifty500`.

This column is the bottom-up sector return relative to Nifty 500 (trailing 3M, decimal fraction: 0.05 = +5% RS).
Available since M3 backfill. NULL before that backfill date; NULL propagated, never zeroed.

Reason not to use `rs_velocity` (stored column):
- `rs_velocity` uses a configurable window from `atlas_thresholds` (tunable at runtime)
- RRG spec requires a fixed 20-day (4-week) lag — self-contained inline SQL is more reliable
- Keeps the MV independent of threshold configuration changes

---

## Formulas

```
rs_ratio     = 100 + (bottomup_rs_3m_nifty500 * 100)
               Parity (0% RS vs Nifty 500) → 100.0
               +5% RS → 105.0,  −5% RS → 95.0

rs_momentum  = rs_ratio_today − LAG(rs_ratio, 20) OVER (PARTITION BY sector_name ORDER BY date)
               Approximates 4-week rate-of-change of RS
               Positive = RS accelerating, Negative = RS decelerating
               NULL for first 20 trading days per sector (LAG window unavailable)
```

---

## Quadrant Assignment

| Condition                             | Quadrant  |
|---------------------------------------|-----------|
| rs_ratio >= 100 AND rs_momentum >= 0  | Leading   |
| rs_ratio <  100 AND rs_momentum >= 0  | Improving |
| rs_ratio <  100 AND rs_momentum <  0  | Lagging   |
| rs_ratio >= 100 AND rs_momentum <  0  | Weakening |
| Either input is NULL                  | NULL      |

Counter-clockwise rotation path: Leading → Weakening → Lagging → Improving → Leading.

---

## 6-Week Trail

"Weekly" = every 5th trading-day row per sector (descending date order).
- ROW_NUMBER() OVER (PARTITION BY sector_name ORDER BY date DESC)
- Filter: `rn_desc % 5 = 1` → rows 1, 6, 11, 16, 21, 26 = today + 5 prior weekly snapshots

Trail assembled via LATERAL: for each (as_of_date, sector_name), pick the 6 most-recent weekly anchor rows with date <= as_of_date, then sort ascending for oldest-first ordering.

JSONB structure per element:
```json
{
  "week_end_date": "2026-05-27",
  "rs_ratio": 103.45,
  "rs_momentum": 1.23,
  "quadrant": "Leading"
}
```

Fewer than 6 elements is valid (sparse early data, new sector, or insufficient history for LAG).

---

## CTE Chain

1. **spine** — DISTINCT (date, sector_name) from atlas_sector_metrics_daily WHERE date >= '2020-01-01'
2. **raw_rs** — bottomup_rs_3m_nifty500 → rs_ratio (inline CASE + ROUND to 4dp)
3. **with_momentum** — rs_ratio + LAG(rs_ratio, 20) OVER window → rs_momentum + quadrant CASE
4. **weekly_anchors** — ROW_NUMBER() OVER (PARTITION BY sector_name ORDER BY date DESC) to rank all rows descending
5. **weekly_filtered** — filter weekly_anchors WHERE rn_desc % 5 = 1 (every 5th row)
6. **Final SELECT** — spine JOIN with_momentum LEFT JOIN LATERAL (trail assembly)

---

## NULL Handling

| Column                        | NULL when                                          |
|-------------------------------|-----------------------------------------------------|
| rs_ratio_current              | bottomup_rs_3m_nifty500 is NULL                    |
| rs_momentum_current           | rs_ratio NULL or first 20 trading days per sector  |
| quadrant_current              | either rs_ratio or rs_momentum is NULL             |
| trail_6w element rs_momentum  | LAG window not available for that snapshot date    |
| trail_6w element quadrant     | either field NULL for that snapshot date           |

---

## Performance

Source rows: ~48K (post 2020 filter). CTE chain O(N) with standard window functions.
LATERAL trail assembly: 48K evaluations × up to ~50 rows each = ~2.4M lookup rows.
Weekly_filtered is pre-indexed by (sector_name, date) on the source table primary key.

Expected REFRESH runtime: 30–60 seconds on Supabase shared compute.
Cron schedule: 20:50 IST (15:20 UTC) — 5 minutes after mv_sector_breadth_nightly (14:45 UTC).

---

## Refresh Schedule

- pg_cron job: `mv_sector_rrg_nightly`
- Schedule: `20 15 * * *` (15:20 UTC = 20:50 IST)
- Command: `REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_sector_rrg`
- Unique index: `uix_mv_sector_rrg_date_sector` on `(as_of_date, sector_name)`

---

## Columns

| Column               | Type             | Description                                        |
|----------------------|------------------|----------------------------------------------------|
| as_of_date           | DATE             | Trading date (spine)                               |
| sector_name          | VARCHAR          | Sector label                                       |
| rs_ratio_current     | NUMERIC(4dp)     | 100 + RS×100; parity=100                          |
| rs_momentum_current  | NUMERIC(4dp)     | rs_ratio change over 20 trading days              |
| quadrant_current     | VARCHAR          | Leading/Improving/Lagging/Weakening/NULL           |
| trail_6w             | JSONB            | Array of up to 6 weekly snapshots, oldest-first   |
| refreshed_at         | TIMESTAMPTZ      | MV refresh timestamp                              |
