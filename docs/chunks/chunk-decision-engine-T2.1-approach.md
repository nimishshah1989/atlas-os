# Chunk: Decision Engine Task 2.1 — Migration 092 atlas_portfolio_policy

## Findings

### Real revision IDs found
- Migration 091 revision string: `"091_fund_recommendation_enum_fix"`
- This is the correct `down_revision` for migration 092.

### Portfolios table
- Table: `atlas.strategy_fm_custom_portfolios`
- PK: `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
- Declared in migration 020
- `portfolio_id` FK in `atlas_portfolio_policy` will reference `atlas.strategy_fm_custom_portfolios(id)` and is nullable (NULL = house-default row)

### Migration style
- Schema constant `_SCHEMA = "atlas"` used in recent migrations (073, 075)
- `op.create_table(...)` with SA typed columns for new tables (not raw SQL text)
- UUID columns: `UUID(as_uuid=True)` from `sqlalchemy.dialects.postgresql`
- Timestamps: `sa.DateTime(timezone=True)` with `server_default=sa.text("NOW()")`
- `sa.Numeric(precision, scale)` — never float
- CHECK constraints: `sa.CheckConstraint("col IN (...)", name="ck_...")`
- FK: `sa.ForeignKeyConstraint(...)` inside `op.create_table` or `op.create_foreign_key` after
- Partial index: `op.create_index(..., postgresql_where=sa.text("is_house_default"))`

### Test style
- All migration tests use `_SKIP_INTEGRATION = pytest.mark.skipif(not os.environ.get("ATLAS_INTEGRATION_TESTS"), ...)`
- Tests require live DB — skipped locally
- For migration 092: write lightweight import-level tests (no DB) asserting revision, down_revision, upgrade/downgrade callable, plus integration-skipped structural tests

### Partial unique index
- `CREATE UNIQUE INDEX uix_portfolio_policy_house_default ON atlas.atlas_portfolio_policy (is_house_default) WHERE is_house_default`
- Implemented via `op.create_index("uix_portfolio_policy_house_default", "atlas_portfolio_policy", ["is_house_default"], unique=True, schema=_SCHEMA, postgresql_where=sa.text("is_house_default"))`

### Numeric precision decisions
- Percentages (pct columns): `Numeric(6, 4)` — stores values like 0.0500 (5%)
- Rank columns (min_within_state_rank, min_rs_rank): `Numeric(5, 4)` — 0–1 range
- Stop percentages (hard_stop_pct, trailing_stop_pct): `Numeric(6, 4)`

### Edge cases
- `portfolio_id` nullable — NULL identifies the house-default row
- `trailing_stop_pct` nullable — optional trailing stop
- `state_exit_trim`/`state_exit_full` nullable — policy may not specify exit states
- `buy_states` is ARRAY(Text) — requires `postgresql.ARRAY`
- Partial unique index only fires on rows where `is_house_default = TRUE`, allowing multiple non-default rows

### Local DB note
Mac psycopg2 is broken — `alembic upgrade` is deferred to EC2. Tests are written to skip without ATLAS_INTEGRATION_TESTS=1.
