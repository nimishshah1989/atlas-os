# Chunk B.1 — Portfolio aggregation query approach

## Data scale
- `atlas_paper_portfolio` is EMPTY at v6.0 launch (by design — portfolio writer cron is out of scope).
  The query must handle zero-row tables gracefully: return `null` for `getHoldingState`, empty Set for `getHeldIidSet`.
- No row-count concern for SQL query planning — empty table, index scans trivial.

## Approach
- **Two exports**: `getHoldingState(iid)` (per-iid aggregation) and `getHeldIidSet()` (request-level memoized Set).
- **SQL aggregation** in Postgres: single `SELECT COUNT(*), MAX(entry_date) WHERE exit_date IS NULL AND instrument_id = $1`.
- `getHeldIidSet()` uses `React.cache()` for per-request memoization (same pattern as `isGoldAvailable()`).
- Connection: `@/lib/db` uses the service-role URL (bypasses RLS). No `user_id` filter needed at v6.0 single-user assumption. Comment documents multi-user-readiness.

## Schema gap: weight_range
The migration 084 schema has NO `weight_pct` column. Weight is not stored per-lot (only `entry_price`, `exit_date`, counts).
**Decision**: `weight_range = ["0.00", "0.00"]` for v6.0 with a `TODO(v6.1)` comment. The plan explicitly authorizes this: "return ["0.00", "0.00"] for now and document the gap."
`aggregate_weight = "0.00"` for same reason.

## Wiki patterns checked
- `gold_availability.ts` — React.cache + sql template tag + server-only pattern
- `funds.ts` / `stocks.ts` — type Row with string | null for NUMERIC columns, schema `atlas.atlas_*`

## Edge cases
- Empty table → `rows[0]` is undefined → function returns `null` (not error)
- NULL `instrument_id` filtering: WHERE clause on UUID exact match (no NULL risk)
- `getHeldIidSet()` with zero rows → empty Set (not null)
- `entry_date` MAX on empty result → NULL → `last_add_date: null`

## Expected runtime (t3.large, empty table)
- < 5ms per call (index scan on partial index `ix_atlas_paper_portfolio_user_open`)
- Once populated: still sub-10ms for typical <1K positions per user

## Files
1. `frontend/src/lib/queries/v6/portfolio_holdings.ts` (target ~80 LOC)
2. `frontend/src/lib/queries/v6/__tests__/portfolio_holdings.test.ts` (target ~120 LOC)
