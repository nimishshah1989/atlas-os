# Chunk: State Engine Migration 074 — atlas_state_thresholds

## Task
Task 0.3: Migration 074 adding the `atlas_state_thresholds` table to the `atlas` schema.

## Data Scale
No existing data to migrate. This is a new table. No row-count impact.
Prior migration (073) created `atlas_state_dwell_statistics` with same PK pattern.

## Chosen Approach
Direct Alembic migration with `op.create_table` + `op.execute` for the partial unique index.

Why partial index over regular unique constraint:
- We need to allow multiple historical rows for the same (threshold_name, state_or_gate) pair
- Only one row per pair may have `active=TRUE`
- PostgreSQL partial unique index `WHERE active = TRUE` is the correct mechanism
- Standard UNIQUE constraint would block historical inserts

## Wiki Patterns Checked
- Migration 073 pattern: `PrimaryKeyConstraint(col1, col2, col3)` with schema=_SCHEMA
- test_073 pattern: `_SKIP_INTEGRATION` decorator, column membership check

## Existing Code Reused
- `tests/migrations/conftest.py` — `db_engine` fixture unchanged
- Migration 073 structure verbatim

## Edge Cases
- Partial index downgrade: `DROP INDEX atlas.uq_state_thresholds_active` — schema-qualified
- `active` default is FALSE (server_default) — new rows inert until explicitly activated
- `threshold_value`: Numeric(12,6) — adequate for θ values in financial classifiers
- `ic_at_threshold`, `ic_ir_at_threshold`, `q5_q1_spread`: nullable — not populated at insert time

## Expected Runtime
Migration: < 1 second (new table, no data). Tests: < 2 seconds (2 SELECT queries).
