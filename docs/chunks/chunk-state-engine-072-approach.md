# Chunk: State Engine — Migration 072 Approach

## Task
Create `migrations/versions/072_atlas_stock_state_daily.py` and a regression test.

## Data scale
New table — zero rows at creation. No migration of existing data. No scan of large tables required.

## Approach
- New CREATE TABLE migration following exact same pattern as 071 (op.create_table, op.create_index).
- No data backfill needed.
- Primary key: (instrument_id, date) — composite, no surrogate id (time-series table).
- Two CHECK constraints: ck_state_value (7 stage values + uninvestable) and ck_urgency_value (4 values).
- Two indexes: date alone (for nightly range scans) and (date, state) composite (for state-filtered queries).

## Test approach
- Follow the project's established pattern in tests/unit/migrations/: mock-based unit tests (no DB) + integration tests skipped unless ATLAS_INTEGRATION_TESTS env is set.
- The task spec provided a `db_engine`-based test at `tests/migrations/` — this directory doesn't exist. I'll create `tests/migrations/` with a conftest.py providing `db_engine` from `ATLAS_DB_URL`, matching the spec exactly.
- Integration tests guarded by `ATLAS_INTEGRATION_TESTS` env var to not break CI on Mac.

## Wiki patterns checked
- Idempotent Upsert: not applicable (new table, no data migration).
- SQL Window Computation: not applicable (DDL only).
- Migration ABC Framework: relevant — straight alembic op.create_table pattern.

## Existing code reused
- alembic op.create_table pattern from 071, 067, 064.
- UUID column type from existing migrations (sqlalchemy.dialects.postgresql.UUID).

## Edge cases
- `prior_state` nullable — stocks newly entering coverage have no prior state.
- `dwell_percentile` and `within_state_rank` nullable — require population data to compute.
- `distribution_days` nullable — not computable until sufficient history.
- `sma_200_slope` nullable — requires 200+ days of data.

## Expected runtime
DDL only — sub-second on any tier.
