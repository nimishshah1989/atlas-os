# Chunk v6-A.0 — Data Availability Pre-flight + Source Map

## Context
Gate task for the v6 frontend build. Verifies every SQL table referenced in
`frontend/src/lib/queries/v6/*.ts` actually exists in `migrations/versions/`
and documents the full data-source map. Part of the Phase A serial gate.

## Data scale
Not applicable — this task is a static analysis script + documentation.
No DB reads in the Python script itself (DB check is HITL via SQL file).

## Chosen approach
Pure static analysis in Python (stdlib only: re, pathlib, sys, argparse).

1. Extract table names from v6 TS query files via regex (`FROM\s+atlas\.(\w+)`
   and `JOIN\s+atlas\.(\w+)`).
2. Build a set of all known tables from migration files (two patterns:
   `op.create_table(\n\s+"name"` and `CREATE TABLE IF NOT EXISTS atlas.name`).
3. Autonomous resolutions from plan patch header treated as special cases:
   - `atlas_universe_snapshot` → flag if found (should be `atlas_universe_stocks`)
   - `atlas_sector_breadth_daily` → flag if found (derive from JSONB)
   - `atlas_fund_holdings_history` → flag if found (use `atlas_fund_scorecard.top_holdings`)
   - `atlas_ledger_public` → flag if found (rename to `atlas_ledger`)
   - `atlas_stock_signal_unified` → known VIEW (not in Alembic; documented as
     pre-existing view applied directly to Supabase per signal-consolidation spec)
4. JSONB unpack patterns (e.g. `jsonb_to_recordset(top_holdings)`) recognized
   as non-table dependencies — not flagged as missing tables.

## Wiki patterns checked
- Data Completeness Audit — split missing into orthogonal buckets before acting
- Dual Code Path Divergence — audit script catches both `FROM` and `JOIN` patterns

## Existing code reused
- `atlas/preflight.py` references `de_index_constituents`, `de_index_prices`,
  `de_index_master` — these are `public` schema JIP tables; NOT in Alembic.
  The audit script handles this by treating `de_*` tables as a known-external
  schema (JIP/public) and not flagging them.

## Edge cases
- `atlas_stock_signal_unified` is a VIEW created directly in Supabase (via the
  signal-consolidation plan, not Alembic). Document it as "known external view"
  in data-source-map.md.
- `de_*` tables (de_index_prices, de_index_constituents) live in `public` schema,
  not `atlas` schema. Only `atlas.*` references are in scope for migration checks.
- The `instrument.ts` module delegates entirely to `stocks.ts` and `snapshot.ts`
  — it introduces no new table references.
- Fixture `.ts` files for tests use `atlas.` schema prefix to match real queries.

## Table coverage confirmed
Tables used in v6/ queries and their migration sources:
| Table | Migration |
|---|---|
| atlas_universe_stocks | 002 (CREATE TABLE) |
| atlas_stock_signal_unified | VIEW — signal-consolidation spec (not Alembic) |
| atlas_stock_metrics_daily | 004 (CREATE TABLE) |
| atlas_conviction_daily | 092 (op.create_table) |
| atlas_etf_scorecard | 093 (op.create_table) |
| atlas_universe_etfs | 002 (CREATE TABLE) |
| atlas_etf_metrics_daily | 004 (CREATE TABLE) |
| atlas_fund_scorecard | 093 (op.create_table) |
| atlas_universe_funds | 002 (CREATE TABLE) |
| atlas_fund_metrics_daily | 004 (CREATE TABLE) |
| atlas_sector_states_daily | 005 (CREATE TABLE) |
| atlas_sector_metrics_daily | 004 (CREATE TABLE) |
| atlas_market_regime_daily | 004 (CREATE TABLE) |
| atlas_scorecard_daily | 080 (op.create_table) |
| atlas_mf_switch_rules | 085 (op.create_table) |
| atlas_ledger | 083 (op.create_table) |
| de_index_prices | JIP public schema (not Alembic) |
| de_index_constituents | JIP public schema (not Alembic) |

## Expected runtime
< 1 second (grep on ~100 files).

## Implementation plan
1. `scripts/v6_data_availability_audit.py` — ~200 LOC, stdlib only
2. `docs/v6/data-source-map.md` — human+machine readable spec
3. `scripts/v6_data_availability_check.sql` — HITL DB seed verification
4. `tests/scripts/test_v6_data_availability_audit.py` — 3 pytest cases
5. `tests/fixtures/v6_query_samples/` — minimal .ts fixtures for tests
