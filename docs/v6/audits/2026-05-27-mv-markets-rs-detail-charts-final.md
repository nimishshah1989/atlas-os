# MV Markets RS Detail Charts — Final Audit

**MV:** `atlas.mv_markets_rs_detail_charts`
**Migration:** `101_mv_markets_rs_detail_charts.py`
**Date:** 2026-05-27
**Status:** CODE COMPLETE — PENDING SUPABASE APPLY

---

## Acceptance Criteria Checklist

| Criterion | Status | Notes |
|---|---|---|
| MV name: `atlas.mv_markets_rs_detail_charts` | PASS | Present in migration |
| ONE row per (as_of_date, baseline_code) | PASS | GROUP BY in aggregated CTE |
| 180 trading days per row in JSONB arrays | PASS | `rn_asc BETWEEN (ref.rn_asc - 179) AND ref.rn_asc` |
| price_series JSONB array | PASS | `{d, o, h, l, c}` per element |
| rs_series JSONB array | PASS | `{d, v}` per element, NULL-filtered |
| volume_series JSONB array | PASS | `{d, v, up}` per element, NULL-filtered |
| ma20_series JSONB array | PASS | `{d, v}` per element, 20-day rolling avg |
| rs_new_high_dates sparse array | PASS | Dates where RS > MAX prior 90 days |
| rs_new_low_dates sparse array | PASS | Dates where RS < MIN prior 90 days |
| support_level scalar | PASS | MIN(close) over 180 rows |
| resistance_level scalar | PASS | MAX(close) over 180 rows |
| USD baselines INR-converted | PASS | Lateral FX join, carry-forward |
| RS from atlas_index_metrics_daily (India) | PASS | rs_3m_nifty500 used directly |
| RS computed for non-index baselines | PASS | (close/close_63 - 1) - (n500/n500_63 - 1) |
| 5-year coverage (>= 2020-01-01) | PASS | `dated` CTE filters date >= '2020-01-01' |
| WITH NO DATA on creation | PASS | Present in CREATE MV |
| UNIQUE INDEX on (as_of_date, baseline_code) | PASS | `uix_mv_markets_rs_detail_charts_date_baseline` |
| REFRESH MATERIALIZED VIEW after index | PASS | Correct order in upgrade() |
| pg_cron at 20:35 IST (14:35 UTC) | PASS | `'35 14 * * *'` schedule |
| pg_cron uses CONCURRENTLY | PASS | Present in cron body |
| Alembic migration chain: 100 → 101 | PASS | `down_revision = "100"` |
| 23 unit tests passing | PASS | All pass, 5 integration skipped |
| Ruff clean | PASS | Both migration and test file pass |
| Python syntax valid | PASS | `ast.parse()` clean |

---

## Data Source Mapping (verified from existing spec docs)

| Baseline | Source | Date from | Row count |
|---|---|---|---|
| NIFTY_50 | `de_index_prices` / `atlas_index_metrics_daily` | 2016-04 | ~2,500 |
| NIFTY_100 | same | 2016-04 | ~2,500 |
| NIFTY_MIDCAP_150 | same | 2016-04 | ~2,500 |
| NIFTY_SMLCAP_250 | same | 2016-04 | ~2,500 |
| NIFTY_500 | same | 2016-04 | ~2,500 |
| GOLD | `de_etf_ohlcv` (GOLDBEES) | 2016-04-01 | 2,516 |
| SP500 | `de_global_prices` (^GSPC) | 1928-01-02 | 39,702 |
| MSCI_WORLD | `de_global_prices` (URTH) | 2012-01 | 3,406 |
| MSCI_EM | `de_global_prices` (VWO) | 2016-01 | 2,588 |

All baselines have data coverage ≥ 2020-01-01. DoD criterion met.

---

## SQL Architecture Notes

### Performance approach
The MV uses a self-join pattern (`dated ref JOIN with_flags win ON win.rn_asc BETWEEN (ref.rn_asc - 179) AND ref.rn_asc`) rather than correlated subqueries. This avoids O(n) subquery per row.

The key CTEs:
1. `fx_raw` — lateral join for FX carry-forward (no IGNORE NULLS syntax risk)
2. `with_flags` — single-pass window functions: LAG, AVG (MA20), MAX/MIN (RS flags)
3. `dated` — filters to 2020-01-01+ output rows
4. `windowed` — self-join producing 180 rows per output row
5. `aggregated` — GROUP BY with jsonb_agg produces final JSONB arrays

Expected refresh time: 90–180 seconds on Supabase shared compute.
Expected row count: ~14,800 (9 baselines × ~1,644 trading days from 2020-01-01).

### Edge cases handled
- NULL close: propagated as NULL in JSONB arrays (FILTER WHERE ... IS NOT NULL)
- NULL RS first 63 rows: CASE guard on close_63d_ago / n500_c_63
- NULL usdinr: LATERAL join uses last available FX rate (carry-forward)
- RS flag with NULL: CASE WHEN rs IS NOT NULL guards both new-high/low
- rs_delta_3m with NULL rs_180d_ago: ROUND(NULL - NULL) = NULL, not error

---

## Pending: Supabase MCP Apply

MCP `execute_sql` tools are not available in the implementer subagent context.
The parent session must apply the following 4 statements (in order):

1. `_CREATE_MV` — CREATE MATERIALIZED VIEW ... WITH NO DATA
2. `_CREATE_UNIQUE_INDEX` — CREATE UNIQUE INDEX
3. `_REFRESH_MV` — REFRESH MATERIALIZED VIEW (blocking; 90–180s)
4. `_CRON_SCHEDULE` — SELECT cron.schedule(...)

Each DDL statement requires `.supabase-delete-approved-1` + `.supabase-delete-approved-2`
markers (CREATE is classified as destructive by the gate).

After apply, verify with:
```sql
SELECT baseline_code, COUNT(*), MAX(as_of_date)
FROM atlas.mv_markets_rs_detail_charts
GROUP BY baseline_code
ORDER BY baseline_code;
```
Expected: 9 rows, each with COUNT ≥ 1,640.

---

## Files Created

- `migrations/versions/101_mv_markets_rs_detail_charts.py` — full migration
- `tests/migrations/test_101_mv_markets_rs_detail_charts.py` — 23 unit tests + 5 integration
- `docs/v6/mvs/2026-05-27-mv-markets-rs-detail-charts-design.md` — design doc
- `docs/v6/audits/2026-05-27-mv-markets-rs-detail-charts-final.md` — this file
