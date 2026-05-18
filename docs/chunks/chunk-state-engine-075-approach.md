# Chunk: Migration 075 — atlas_state_action_log

## Data scale
- No row-count query needed: this creates a new empty table.
- Upstream tables (072 atlas_stock_state_daily ~0 rows, 073 dwell_statistics ~0 rows) exist in same schema.
- Expected near-term load: 1 row per (instrument, date, transition) — ~500 instruments × ~250 trading days = ~125K rows/year. Well within Postgres capacity with PK index.

## Chosen approach
- Pure DDL migration (Alembic op.create_table) — no Python compute, no pandas.
- Single composite PK on (instrument_id, date, transition): natural dedup key. One action per instrument-date-transition triple.
- CHECK constraint on `action` column — only 6 valid values (BUY/HOLD/TRIM/EXIT/WATCH/FORCE_EXIT). Transitions are NOT enumerated by design (new state pairs can appear without schema change).
- `suppressed_by` is nullable string (e.g. 'regime_filter', 'position_limit') — free-form within 32 chars.
- `position_size` Numeric(8,4) and `within_state_rank` Numeric(5,4) are NOT money columns; they are computed coefficients stored as Decimal per fintech hook rules regardless.
- `urgency_score` is String(12) not Numeric — the spec stores it as a label (e.g. 'HIGH', 'MEDIUM').
- downgrade drops the table cleanly.

## Wiki patterns checked
- [Idempotent Upsert](patterns/idempotent-upsert.md) — not needed here, PK handles dedup on insert.
- [Migration ABC Framework](architecture/migration-abc-framework.md) — follows existing atlas migration style (op.create_table, schema=_SCHEMA, no raw DDL strings).

## Existing code being reused
- Pattern from 074_atlas_state_thresholds.py (same _SCHEMA constant, same op.create_table style).
- conftest.py db_engine fixture in tests/migrations/.

## Edge cases
- `suppressed_by` NULL means the action fired (not suppressed) — this is by design per spec.
- `position_size` NULL means size not yet determined at log time — valid state.
- `within_state_rank` NULL valid for FORCE_EXIT actions.
- `instrument_id` UUID — no FK to atlas_instruments declared in this migration (the engine populates from its own universe; FK would require instruments to exist first and adds complexity without benefit for an audit log).

## Expected runtime
- DDL-only: sub-second on t3.large.
- Test: ~100ms including two network round-trips to RDS.
