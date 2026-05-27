# Approach: MV 5 of 9 — `atlas.mv_sector_rrg`

**Date**: 2026-05-27
**Migration**: 104
**Chunk**: mv-sector-rrg

---

## Data Scale

- `atlas.atlas_sector_metrics_daily`: 74,752 rows (31 sectors × ~2,412 trading days; filtered to 2020+ = ~48k rows)
- Scale is 100K–1M range: use SQL window functions exclusively; no Python aggregation

## Approach

### Source

Use `atlas.atlas_sector_metrics_daily.bottomup_rs_3m_nifty500` as the per-sector RS series.
This column is: sector return relative to Nifty 500 over the trailing 3M (decimal fraction, e.g. 0.05 = +5%).

Do NOT use `rs_velocity` (stored column) because:
- It's computed with a configurable window from `atlas_thresholds`
- We need a fixed 20-day lag for RRG momentum (spec-defined)
- Self-contained SQL is more reliable for a standalone MV

### Formula

```
rs_ratio     = 100 + (bottomup_rs_3m_nifty500 * 100)
               → 0% RS = 100.0, +5% RS = 105.0, −5% RS = 95.0
rs_momentum  = rs_ratio_today - LAG(rs_ratio, 20) OVER (PARTITION BY sector_name ORDER BY date)
               → positive = RS accelerating upward vs ~4 weeks ago
```

Quadrant assignment:
- `rs_ratio >= 100 AND rs_momentum >= 0` → Leading
- `rs_ratio <  100 AND rs_momentum >= 0` → Improving
- `rs_ratio <  100 AND rs_momentum <  0` → Lagging
- `rs_ratio >= 100 AND rs_momentum <  0` → Weakening
- NULL when either input is NULL → NULL

### 6-week trail

"Weekly" = every 5th trading day row within the sector's date-ordered sequence.
Approach: ROW_NUMBER() OVER (PARTITION BY sector_name ORDER BY date DESC) — rows 1, 6, 11, 16, 21, 26 give the last 6 weekly snapshots including today.

Trail JSONB assembled via `jsonb_agg(jsonb_build_object(...) ORDER BY date ASC)` on those 6 rows.

### CTE chain (6 CTEs)

1. `spine` — DISTINCT (date, sector_name) from atlas_sector_metrics_daily WHERE date >= '2020-01-01'
2. `raw_rs` — date, sector_name, bottomup_rs_3m_nifty500, rs_ratio (inline computed)
3. `with_momentum` — raw_rs + LAG(rs_ratio, 20) OVER window → rs_momentum, quadrant (CASE)
4. `weekly_rows` — ROW_NUMBER() OVER (PARTITION BY sector_name ORDER BY date DESC) % 5 == 1 filter (rows 1,6,11,16,21,26) to get weekly snapshots for trail
5. `trail_agg` — jsonb_agg of 6-element trail per (as_of_date, sector_name): self-join weekly_rows to assemble trailing 6 from the most-recent date backward
6. Final SELECT joining spine → with_momentum (current scalars) → trail_agg (JSONB)

### Trail assembly approach

Rather than a correlated subquery per row (which caused MV 4 timeout risk), we use a lateral join:
- Compute week_num = CEIL(ROW_NUMBER() / 5) to identify weekly buckets
- For each as_of_date: find the 6 weekly anchor points (row 1, 6, 11, 16, 21, 26) looking back
- Use a LATERAL with LIMIT 6 approach: for the most recent date per sector, collect the 6 weekly anchors from within a pre-filtered set

Actually: given 48K rows (small), a window approach is fine. We materialize all the weekly anchors for the full history, then in the final SELECT we use LATERAL to pick the 6 most-recent anchors on or before as_of_date.

Revised approach (avoid correlated subqueries):
- `weekly_candidates` CTE: all rows where `row_num % 5 = 1` (every 5th row per sector, descending)
- `trail_per_date` CTE: for each (as_of_date, sector_name), JSONB aggregate the 6 most-recent weekly_candidates with date <= as_of_date — using a WHERE filter + LIMIT 6 inside jsonb_agg via ordered subquery

Wait — this IS a correlated subquery (the LATERAL). With 48K rows and 31 sectors × ~1550 dates, the number of LATERAL evaluations is 48K. Each LATERAL scans at most 50 rows (6 weeks × few extras). That is ~2.4M row-lookups total — well within 60s budget.

Final approach: LATERAL with LIMIT 6 on pre-filtered weekly_candidates, scanned via (sector_name, date) index on the source table.

### NULL handling

- `bottomup_rs_3m_nifty500` NULL → rs_ratio NULL → rs_momentum NULL → quadrant NULL → trail entry has all NULLs except week_end_date
- LAG returns NULL for first 20 rows per sector (dates before 20-day window) → rs_momentum NULL, quadrant NULL
- trail_6w will contain NULLs for entries where momentum not yet computable (early 2020)

## Wiki Patterns Used

- SQL Window Computation (LAG OVER window, ROW_NUMBER OVER partition)
- Idempotent Upsert (IF NOT EXISTS DDL)

## Existing Code Reused

- Migrations 100-103 structural pattern (constants, upgrade/downgrade shape)
- `bottomup_rs_3m_nifty500` from atlas_sector_metrics_daily (migration 004)
- pg_cron at 20:50 IST = 15:20 UTC (5 minutes after mv_sector_breadth_nightly)

## Edge Cases

- Sectors with < 20 trading days of data: rs_momentum NULL for those rows (LAG not available)
- Sectors with < 6 weekly snapshots: trail_6w will have fewer than 6 elements (acceptable per spec)
- Empty result for early dates (pre-2020): filtered out by date >= '2020-01-01'
- NULL `bottomup_rs_3m_nifty500`: propagated as NULL throughout, never zeroed

## Expected Runtime

Source: ~48K rows for 2020+ sector spine. CTE chain is O(N) with window functions.
JSONB assembly via LATERAL is ~2.4M lookup rows but indexed on (sector_name, date).
Expected REFRESH: 30–60 seconds on Supabase shared compute.
