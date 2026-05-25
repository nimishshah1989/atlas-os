# Chunk C.1 — Cells Query Module (atlas_cell_definitions accessor)

## Data scale
- `atlas_cell_definitions`: expected 21-24 rows (24 cell max, audit found 21 live)
- `atlas_signal_calls`: scale unknown but open positions indexed via `ix_atlas_signal_calls_open` partial index (exit_date IS NULL)
- All queries are tiny result sets — no pagination needed

## Approach
Pure TypeScript/postgres-js query module following the pattern of `gold_availability.ts` and `portfolio_holdings.ts`:
- `import 'server-only'` at top
- `import { cache } from 'react'` for `getAllCells` and `getMatrixCells`
- `getCellById` NOT memoized (different input per call) — implemented as a bare async function
- All Decimal columns cast to `::text` in SQL to arrive as strings
- `predicted_excess` subqueried from `atlas_signal_calls` latest ACTIVE (exit_date IS NULL ORDER BY entry_date DESC LIMIT 1)

## Migration confirmed columns
From migration 080 `atlas_cell_definitions`:
- `cell_id` UUID PK
- `cap_tier` atlas_cap_tier enum: Small | Mid | Large
- `action` atlas_cell_action enum: POSITIVE | NEUTRAL | NEGATIVE
- `tenure` atlas_tenure enum: 1m | 3m | 6m | 12m
- `rule_dsl` JSONB
- `confidence_unconditional` Numeric(5,4)
- `friction_adjusted_excess` Numeric(10,6)
- `confidence_by_regime` JSONB nullable
- `stable_features` JSONB nullable
- `methodology_lock_ref` String(64)
- `rule_version` Integer
- `drift_status` atlas_drift_status enum: healthy | drift_warn | deprecated
- `walkforward_run_id` UUID nullable
- `validated_at` DateTime nullable
- `deprecated_at` DateTime nullable
- `created_at` DateTime

`atlas_signal_calls` has `predicted_excess` Numeric(10,6) nullable — confirmed.
`bh_fdr_q` does NOT exist on `atlas_cell_definitions` per migration 080 — return null via SQL literal.

## Edge cases
- NULL confidence_unconditional / friction_adjusted_excess: cast to ::text returns NULL (correct)
- bh_fdr_q: column does not exist in migration 080 → return NULL::text in SQL
- Empty table: getAllCells returns [], getCellById returns null, getMatrixCells returns []
- No active signal_calls for a cell: predicted_excess subquery returns NULL (correct)
- `deprecated_at IS NULL` used in getMatrixCells LATERAL to count only active cells; for firing_today count we use open signal calls on max date

## Wiki patterns checked
- `gold_availability.ts` — React.cache() memoization pattern
- `portfolio_holdings.ts` — React.cache() + non-cached getCellById analog
- `etfs.ts` — postgres-js tagged-template style, schema-qualified tables

## Expected runtime
- getAllCells: <5ms (21-24 rows, indexed PK)
- getCellById: <2ms (PK lookup)
- getMatrixCells: <10ms (tiny table + LATERAL on indexed partial index)
