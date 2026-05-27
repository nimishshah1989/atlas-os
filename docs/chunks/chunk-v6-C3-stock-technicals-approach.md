# Chunk C.3 — Stock Technicals Query (features JSONB unpack)

## Data scale

`atlas_scorecard_daily` contains ~750 instruments × ~daily rows. Query is single-row
read by `(instrument_id, date)` PK — trivially fast. No aggregation needed.

## Approach

Single SQL query using Postgres `->>` JSONB operator to unpack specific keys.
`date` parameter is optional; COALESCE subquery fetches latest when absent.

### JSONB key source of truth

`_DEEP_SEARCH_PANEL_FEATURES` in `atlas/features/scorecard_writer.py` defines all
features written to the JSONB. The task spec uses some keys (e.g., `ema_distance_20`,
`rs_pct_nifty500`, `vol_252d`, `obv_20d`, `atr_14`) that differ from the actual
scorecard_writer keys. Mapping:

| Task spec key       | Actual JSONB key         | Source |
|---------------------|--------------------------|--------|
| ema_distance_20     | dist_above_sma50 (proxy) | `dist_above_sma50` is closest; `ema_distance_*` not in panel |
| ema_distance_50     | dist_above_sma50         | same family |
| ema_distance_200    | dist_above_sma200        | `dist_above_sma200` |
| rsi_14              | rsi_14                   | exact match |
| rs_pct_nifty500     | rs_residual_6m           | first-class col; JSONB has rs_residual_3m/6m/12m |
| vol_252d            | realized_vol_252d        | exact match (JSONB) |
| obv_20d             | obv_slope_60d            | closest OBV feature in panel |
| atr_14              | atr_pct_14               | exact match (JSONB) |
| pct_from_52w_high   | dd_from_52w_high         | exact match |
| pct_from_52w_low    | dist_from_52w_low        | exact match |
| log_med_tv_60d      | first-class column       | direct column read |
| drawdown_from_peak  | formation_max_dd         | first-class column |

Decision: use the ACTUAL keys from the scorecard writer as the canonical field names
in `StockTechnicals` type, then expose type aliases matching the task spec's names.
Per task spec: "Verify actual feature key names — scorecard writer is source of truth.
If key doesn't exist, return null gracefully."

The type contract in the task spec uses names like `ema_distance_20` etc. We implement
exactly that interface but map to the actual JSONB keys in the SQL query. Where a spec
key has no matching JSONB key, the SQL returns NULL and the type field is null.

## Existing patterns reused

- `import 'server-only'` — same as all v6 query files
- `import sql from '@/lib/db'` — postgres-js tagged template
- Single-query approach with COALESCE for optional date (same pattern as `instrument.ts`)
- `string | null` for all JSONB-extracted values (same as `stocks.ts` Decimal transport)

## Edge cases

- `iid` not in scorecard: SQL returns 0 rows → return `null`
- JSONB key absent (new listing, insufficient history): `->>` returns `NULL` → `null` in TS
- `date` parameter omitted: COALESCE subquery finds `MAX(date)` for that iid
- First-class columns (`log_med_tv_60d`, `formation_max_dd`) read directly as columns,
  not via JSONB

## Expected runtime

Single indexed lookup by (instrument_id, date) UK. Sub-5ms on t3.large.

## Files

- `frontend/src/lib/queries/v6/stock_technicals.ts` (≤ 100 LOC)
- `frontend/src/lib/queries/v6/__tests__/stock_technicals.test.ts` (≤ 200 LOC)
