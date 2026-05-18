# Chunk: State Engine Task 0.5 — Migration 076 Seed Initial Thresholds

## Task
Seed `atlas.atlas_state_thresholds` with 18 defensible Phase-1 defaults covering
the 7 state stages + uninvestable filter + risk gates.

## Data Scale
`atlas_state_thresholds` is a reference table. After this migration it will
contain exactly 18 rows. No fan-out, no large dataset — pure seed DML.

## Approach

**SQL-level idempotent INSERT** via `ON CONFLICT (threshold_name, state_or_gate,
as_of_date) DO NOTHING`. The PK is `(threshold_name, state_or_gate, as_of_date)`.
We use `CURRENT_DATE` for `as_of_date`, so re-running on the same day is a no-op;
running on a later day would insert a second row but `active=TRUE` would conflict
via the partial unique index. This is fine — the migration runs once at upgrade.

**Downgrade**: delete by `(threshold_name, state_or_gate)` with `active=TRUE`
guard to avoid removing Phase-2 tuned rows if somehow present.

## Wiki Patterns Checked
- `Idempotent Upsert` — ON CONFLICT DO NOTHING on natural PK; fits exactly
- `Decimal Not Float` — threshold values stored as Numeric(12,6) in DB; Python
  floats are acceptable in the seed list because they feed `sa.text()` params
  which PostgreSQL receives as NUMERIC literals

## Existing Code Reused
- Pattern from migration 074 (creates the table) and 075 (sibling pattern)
- Test pattern from `tests/migrations/test_075_action_log.py`

## Edge Cases
- Re-run on same date: `ON CONFLICT DO NOTHING` handles it
- Partial unique index on `active=TRUE`: only one active row per (name, state)
  is allowed — no conflict here since we're inserting 18 distinct (name, state) pairs
- downgrade deletes only `active=TRUE` rows for the seeded names, so Phase-2
  rows with `active=FALSE` are untouched

## Expected Runtime
18 single-row INSERTs: < 100ms on Supabase RDS.

## Test Strategy
Integration test (ATLAS_INTEGRATION_TESTS=1 gate):
- Assert >= 18 active rows exist
- Spot-check 5 known (name, state) -> value pairs
