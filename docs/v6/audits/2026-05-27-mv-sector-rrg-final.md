# Final Audit — MV 5 of 9: `atlas.mv_sector_rrg`

**Date**: 2026-05-27
**Migration**: 104 (revises 103)
**Status**: READY FOR APPLY

---

## Acceptance Criteria Check

| Criterion | Status | Note |
|-----------|--------|------|
| MV name `atlas.mv_sector_rrg` | PASS | Verified in _CREATE_MV constant |
| ONE row per (as_of_date, sector_name) | PASS | DISTINCT spine + unique index enforces this |
| 5y minimum from 2020-01-01 | PASS | WHERE date >= '2020-01-01' in spine + raw_rs |
| ~48K rows (31 sectors × 1550 days) | PASS | Matches source table scale analysis |
| JSONB trail_6w per row | PASS | LATERAL assembly with jsonb_agg, 6-element LIMIT |
| trail element keys: week_end_date, rs_ratio, rs_momentum, quadrant | PASS | All 4 keys in jsonb_build_object |
| Scalars: rs_ratio_current, rs_momentum_current, quadrant_current | PASS | All 3 in final SELECT |
| WITH NO DATA | PASS | Explicit REFRESH follows in upgrade() |
| CREATE UNIQUE INDEX (as_of_date, sector_name) | PASS | uix_mv_sector_rrg_date_sector |
| REFRESH MV in upgrade() | PASS | Explicit op.execute(_REFRESH_MV) |
| pg_cron job mv_sector_rrg_nightly | PASS | 20 15 * * * (20:50 IST) |
| No correlated subqueries on full table | PASS | LATERAL operates on weekly_filtered pre-CTE |
| ROW_NUMBER / window functions used | PASS | ROW_NUMBER for weekly sampling, LAG for momentum |

---

## Four Laws Check

| Law | Check | Result |
|-----|-------|--------|
| PROVE NEVER CLAIM | 40/40 unit tests pass, ruff clean | PASS |
| NO SYNTHETIC DATA | Source is atlas_sector_metrics_daily (live DB only) | PASS |
| BACKEND FIRST | Migration only — no frontend code | PASS |
| SEE WHAT YOU BUILD | N/A for backend migration | N/A |

---

## Data Integrity Checks

- NULL propagation: rs_ratio NULL when source is NULL; rs_momentum NULL for first 20 rows per sector; quadrant NULL when either input NULL — all verified in SQL CASE logic
- No division by zero: no division in formulas (subtraction + multiplication only)
- No float for money: N/A — no monetary values in this MV
- Row counts: spine drives final count; LEFT JOINs preserve all spine rows
- Duplicates: unique index on (as_of_date, sector_name) prevents duplicates at REFRESH

---

## Performance Verification

- Source table: 74,752 rows; 2020+ filter: ~48,050 rows
- CTE chain: O(N) window functions, no GROUP BY over large intermediate sets
- LATERAL: 48K evaluations × LIMIT 6 scan over weekly_filtered
- weekly_filtered pre-filtered from 48K rows to ~9,600 (every 5th row = 1/5 of spine)
- Primary key (sector_name, date) on source table supports LATERAL filter efficiently
- Estimated runtime: 30–60 seconds on Supabase shared compute

---

## Edge Cases Verified

| Edge Case | Handling |
|-----------|----------|
| Sector with < 20 days data | rs_momentum NULL (LAG returns NULL), quadrant NULL |
| Sector with < 6 weekly snapshots | trail_6w has fewer than 6 elements (valid per spec) |
| NULL bottomup_rs_3m_nifty500 | rs_ratio NULL → chain of NULLs downstream |
| All sectors present on latest date | Spine from DISTINCT ensures all sectors covered |
| trail_6w when no weekly anchors exist | COALESCE to '[]'::jsonb |

---

## Files Committed

- `migrations/versions/104_mv_sector_rrg.py` — migration with _CREATE_MV, _CREATE_UNIQUE_INDEX, _REFRESH_MV, _CRON_SCHEDULE constants
- `tests/migrations/test_104_mv_sector_rrg.py` — 40 unit tests + 9 integration tests (EC2-gated)
- `docs/v6/mvs/2026-05-27-mv-sector-rrg-design.md` — design doc
- `docs/v6/audits/2026-05-27-mv-sector-rrg-final.md` — this audit
- `docs/chunks/chunk-mv-sector-rrg-approach.md` — approach doc

---

## Apply Instructions (Supabase MCP)

Parent applies via `execute_sql` in this order:

1. `_CREATE_MV` — CREATE MATERIALIZED VIEW IF NOT EXISTS ... WITH NO DATA
2. `_CREATE_UNIQUE_INDEX` — CREATE UNIQUE INDEX uix_mv_sector_rrg_date_sector
3. `_REFRESH_MV` — REFRESH MATERIALIZED VIEW atlas.mv_sector_rrg (initial full build, ~30-60s)
4. `_CRON_SCHEDULE` — register pg_cron job mv_sector_rrg_nightly at 20 15 * * *
