# Approach: Migration 080 — v6 Prerequisite Tables

## Task
Create migration 080 adding 8 tables for the v6 trading model data prerequisites.

## Blocker Identified

The v6 worktree (`feat/v6-trading-model`) only contains migrations 001-065.
Migrations 066-079 exist on `feat/atlas-strategy-lab` branch (sibling branch,
not yet merged to main). Migration 080 requires `down_revision = "079"`.

Alembic will refuse to apply migration 080 if 079 is not in the chain.
Similarly, the test's `command.upgrade(alembic_config, "080")` will fail with
"Can't locate revision identified by '079'" if 066-079 are absent.

**Resolution required by user**: copy or merge migrations 066-079 from
`feat/atlas-strategy-lab` into `feat/v6-trading-model` before this migration
can be applied.

## Actual Data Scale
N/A — DDL-only migration. No data transform.

## Chosen Approach
- Use `op.execute()` with raw SQL DDL strings (consistent with migrations 042+
  in this codebase that use the same pattern for schema-qualified tables).
- All 8 tables in `atlas.` schema.
- Test pattern: unit mock tests (always run, no DB needed) + integration tests
  skipped unless `ATLAS_TEST_DB_URL` is set. This matches the project pattern
  in `tests/unit/migrations/test_migration_064.py`.

## Wiki Patterns Checked
- `tests/unit/migrations/test_migration_064.py` — project migration test template.
  Uses `unittest.mock` to patch `alembic.op.*`, never touches live DB in unit tests.
- Migration 042 (`create_intraday_tables.py`) — uses `op.execute()` with schema-
  qualified SQL for complex DDL.

## Existing Code Being Reused
- Migration test structure from `test_migration_064.py`.
- `op.execute()` SQL pattern from migration 042.

## Edge Cases
- Schema `atlas.` must exist (created by migration 001) — already present.
- `IF NOT EXISTS` on all `CREATE TABLE` calls — idempotent.
- `DROP TABLE IF EXISTS` in downgrade — safe if tables don't exist.
- `instrument_id UUID` references `atlas_instruments` logically but no FK
  constraint — avoids circular dependency issues during backfill.

## Test Design
Per project pattern: unit tests mock `alembic.op` and assert SQL strings.
Integration tests gated on `ATLAS_TEST_DB_URL` env var.

The spec's three tests (upgrade creates tables, downgrade drops them,
index present) are all integration-style. They will be `skipif`-gated
on `ATLAS_TEST_DB_URL` and also require migrations 066-079 to be in chain.

## Expected Runtime
DDL only — sub-second on any hardware.
