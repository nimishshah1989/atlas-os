# Chunk C.6 — Recent Signal Calls Query

## Task
Query module for `atlas_signal_calls` — three functions covering (a) recent-N calls in last N days, (b) per-iid audit trail, (c) per-cell history.

## Data scale
`atlas_signal_calls` is currently 0 rows at v6.0 launch (migration 096 backfill ~363 rows dispatched but pending). Query must handle empty table → returns `[]`. With 363 rows, any approach works; even full-table scan is fine. Scale stays small long-term (1 signal call per trigger event, not per-day per stock).

## Schema mapping
Migration 080 `atlas_signal_calls` columns used:
- `signal_call_id` UUID — primary key
- `instrument_id` UUID — FK to atlas_universe_stocks
- `cell_id` UUID — FK to atlas_cell_definitions
- `date` DATE — the trigger date (mapped to `entry_date` in output per task spec)
- `cap_tier_at_trigger` enum — denormalized tier at trigger time
- `tenure` enum
- `action` enum
- `confidence_unconditional` NUMERIC(5,4)
- `predicted_excess` NUMERIC(10,6) — nullable
- `exit_date` DATE — nullable; NULL = active position
- `computed_at` TIMESTAMPTZ — used for secondary ORDER BY

Note: `entry_price` column does NOT exist in the schema. Task spec lists it but it's not in migration 080. Output type is `string | null` and SQL returns `NULL::text`.

`atlas_universe_stocks` used for `symbol` (ticker) enrichment — LEFT JOIN on `instrument_id` (no effective_from range join needed for display purposes; universe stocks are current).

## Approach
- 3 exported async functions, all hitting Supabase postgres-js direct
- `getRecentSignalCalls(limit=50, days=7)` — WHERE `sc.date >= CURRENT_DATE - INTERVAL 'N days'` LIMIT
- `getSignalCallsByIid(iid, limit=20)` — WHERE `sc.instrument_id = $1::uuid` ORDER entry_date DESC
- `getSignalCallsByCell(cell_id, limit=20)` — WHERE `sc.cell_id = $1::uuid` ORDER entry_date DESC
- ticker fallback: LEFT JOIN on atlas_universe_stocks; if NULL, fall back to `iid` string
- is_active: `(exit_date IS NULL)` computed in SQL
- cell_name: `CONCAT(cap_tier_at_trigger, ' ', tenure, ' ', action)` — e.g., "Mid 12m POSITIVE"

## Pattern reuse
- `import 'server-only'` + `import sql from '@/lib/db'` pattern from matrix_diff.ts, funds_holding_stock.ts
- Mock pattern from matrix_diff.test.ts: `vi.mock('server-only', () => ({}))` + `vi.mock('@/lib/db', ...)`

## Edge cases
- Empty table → postgres-js returns `[]` — no guard needed
- NULL ticker (iid not in universe) → COALESCE(us.symbol, sc.instrument_id::text)
- NULL predicted_excess → preserved as null string
- NULL exit_date → is_active = true

## Expected runtime
Under 10ms on any realistic dataset. 363 rows → single-pass index scans.

## Files
- `frontend/src/lib/queries/v6/recent_signal_calls.ts` (target ≤200 LOC)
- `frontend/src/lib/queries/v6/__tests__/recent_signal_calls.test.ts` (target ≤280 LOC)
