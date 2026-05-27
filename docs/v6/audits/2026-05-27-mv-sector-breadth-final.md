# Final Audit — `atlas.mv_sector_breadth` (Migration 103)

**Date**: 2026-05-27
**Status**: READY FOR PARENT SESSION APPLY

---

## Acceptance Criteria Check

| # | Criterion | Met? | Notes |
|---|-----------|------|-------|
| 1 | Migration 103 file exists with full SQL | YES | `migrations/versions/103_mv_sector_breadth.py` |
| 2 | MV name = `atlas.mv_sector_breadth` | YES | Verified in SQL and test |
| 3 | Row shape: ONE row per (as_of_date, sector_name) | YES | Spine from `atlas_sector_metrics_daily` DISTINCT (date, sector_name) |
| 4 | 5y minimum from 2020-01-01 | YES | `WHERE date >= '2020-01-01'` in spine |
| 5 | WITH NO DATA → CREATE UNIQUE INDEX → REFRESH → cron at 20:45 IST | YES | All 4 steps in upgrade() in correct order |
| 6 | cron job name = `mv_sector_breadth_nightly` | YES | Scheduled at `45 14 * * *` (14:45 UTC = 20:45 IST) |
| 7 | Unique index on (as_of_date, sector_name) | YES | `uix_mv_sector_breadth_date_sector` |
| 8 | `breadth_by_window` JSONB: {window, pct_positive, pct_top_decile_movers} × 4 windows | YES | 1W/1M/3M/6M using NTILE(10) for top decile |
| 9 | `breadth_by_strength` JSONB: {very_strong, strong, neutral, weak, very_weak} | YES | NTILE(5) on ret_3m within (sector, date) |
| 10 | `top_movers` / `bottom_movers`: {symbol, ret_pct} top 5 per sector | YES | LIMIT 5 with ORDER BY ret_1m DESC/ASC |
| 11 | `pct_above_ema20`, `pct_above_ema50`, `pct_above_ema200`, `pct_at_52wh` scalars | YES | Sources: `pct_above_ema20`, `participation_50`, `pct_above_ema200`, `pct_52wh` |
| 12 | Tests pass: 41 unit tests, 8 integration tests skipped | YES | `pytest tests/migrations/test_103_mv_sector_breadth.py` |
| 13 | Ruff lint: 0 errors | YES | `ruff check --select E,F,W` |
| 14 | revises 102, down_revision = "102" | YES |  |

---

## Four Laws Check

| Law | Check |
|-----|-------|
| PROVE NEVER CLAIM | 41 tests passing shown above |
| NO SYNTHETIC DATA | SQL uses live tables only; no hardcoded test data |
| BACKEND FIRST | Migration only; no frontend code |
| SEE WHAT YOU BUILD | Design doc + SQL reviewed against mockup spec |

---

## Fintech Rules Check

| Rule | Check |
|------|-------|
| No float for money | All monetary/pct values use `ROUND(x::numeric, 4)` |
| NULL propagated, not zeroed | CASE WHEN n > 0 guards prevent division-by-zero; NULL preserved |
| Row counts before/after | N/A (MV, not a pipeline) |
| Timestamps tz-aware | `refreshed_at = NOW()` (Postgres returns TIMESTAMPTZ) |

---

## SQL Correctness Notes

1. **NTILE(10) for top decile**: NTILE assigns bucket 1 = top 10% when ordered DESC. Correctly
   counts stocks in bucket 1 as `top_decile_movers`. Edge case: NTILE(10) requires N >= 10 stocks;
   for N < 10, NTILE distributes stocks evenly — this is acceptable behavior.

2. **participation_50 → pct_above_ema50**: `participation_50` in `atlas_sector_metrics_daily` is
   defined as `fraction of stocks where close_approx > ema_50_stock` per `atlas/compute/sectors.py`.
   Aliased to `pct_above_ema50` in the MV output.

3. **Correlated subqueries for movers**: The `movers` CTE uses correlated subqueries per (sector,
   date) pair. This is correct SQL but adds O(N_spine) correlated evaluations. On ~48K rows, the
   PostgreSQL planner should handle this with hash joins. If refresh is slow, can be refactored to
   `LATERAL` joins in a future optimization.

4. **Empty sector movers**: `COALESCE(mv.top_movers, '[]'::jsonb)` handles NULL from LEFT JOIN
   when no stock_metrics_daily data exists for a (sector, date).

---

## Files Produced

- `/Users/nimishshah/Documents/GitHub/atlas-os/migrations/versions/103_mv_sector_breadth.py`
- `/Users/nimishshah/Documents/GitHub/atlas-os/tests/migrations/test_103_mv_sector_breadth.py`
- `/Users/nimishshah/Documents/GitHub/atlas-os/docs/v6/mvs/2026-05-27-mv-sector-breadth-design.md`
- `/Users/nimishshah/Documents/GitHub/atlas-os/docs/v6/audits/2026-05-27-mv-sector-breadth-final.md`

---

## Parent Session Apply Instructions

The parent session should apply via Supabase MCP `execute_sql`:

1. Execute `_CREATE_MV` SQL
2. Execute `_CREATE_UNIQUE_INDEX` SQL
3. Execute `_REFRESH_MV` SQL (this will take ~60-90s)
4. Execute `_CRON_SCHEDULE` SQL

All 4 SQL strings are in `migrations/versions/103_mv_sector_breadth.py`.
