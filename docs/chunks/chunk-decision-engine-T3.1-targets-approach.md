# Approach: Task 3.1 — Migration 093 Portfolio Targets + Proposed Changes

## Findings

### Holdings table reality
`atlas.strategy_fm_custom_portfolios` (created migration 020) stores instruments as a `JSONB`
column called `instruments` — NOT a separate per-instrument rows table. There is no
`atlas_portfolio_holdings` or `atlas_fm_custom_portfolio_holdings` table anywhere in migrations
001-092. The instruments JSONB stores `[{instrument_id, instrument_type, weight_pct}]`.

Since the task says "add `target_weight` to the holdings table" and describes it as a
portfolio-level Numeric scalar (nullable, NULL = no target set), the correct interpretation is:
add `target_weight` to `atlas.strategy_fm_custom_portfolios` as a portfolio-level total-weight
target. This is the only table that holds the portfolio's current allocation. There is no
per-instrument row to attach a Numeric to.

### Existing weight column
`instruments` JSONB contains `weight_pct float` per instrument. There is NO `weight`,
`current_weight`, or `target_weight` Numeric column on the table. The `target_weight` column
to be added is genuinely new.

### Precision
Existing weight-adjacent Numeric columns in the codebase use `Numeric(6,4)` (e.g.
`cash_floor_pct`, `max_per_stock_pct` in migration 092) and `Numeric(10,4)` in strategy
lab (migration 067). For a portfolio-level target weight percentage (0–100 range), `Numeric(7,4)`
handles up to 999.9999 — use `Numeric(7,4)` consistent with the percentage convention.

### instrument_id FK decision
`atlas.atlas_universe_stocks` has a composite PK `(instrument_id, effective_from)` — not a
simple UUID PK. `atlas.atlas_universe_etfs` uses `(ticker, effective_from)`. There is no
single instruments table with a UUID PK suitable for a direct FK. The pattern established in
migration 067 (`atlas_strategy_positions_daily`) is to leave `instrument_id` as a plain indexed
UUID with a comment documenting why. Same pattern is used for `atlas_universe_membership_daily`.
We follow that precedent.

### Revision chain
- `down_revision = "092_atlas_portfolio_policy"` (confirmed from migration 092 source)
- New revision: `"093_portfolio_targets_holdings"`

### down_revision confirmed
`092_atlas_portfolio_policy` has `revision = "092_atlas_portfolio_policy"`.

## Approach

**TDD first.** Write `tests/migrations/test_093_portfolio_targets.py` first, then implement.

### Migration 093 changes
1. `op.add_column` on `atlas.strategy_fm_custom_portfolios`: add `target_weight Numeric(7,4) nullable`.
   - NULL = no target set yet (correct semantics per spec).
   - Precision matches weight-percentage convention in migration 092.

2. `op.create_table("atlas_portfolio_proposed_change", ...)`:
   - `id` UUID PK with `gen_random_uuid()` server default
   - `portfolio_id` UUID FK → `atlas.strategy_fm_custom_portfolios.id`, CASCADE, `index=True`
   - `instrument_id` UUID plain indexed (no FK — composite PK on universe tables; same pattern as migration 067)
   - `proposed_weight Numeric(7,4)` not null (a proposed weight must be a real value)
   - `status Text` CHECK IN ('pending','applied','rejected'), default 'pending'
   - `rationale Text` nullable
   - `created_at`, `updated_at` tz-aware timestamps, NOT NULL, server_default NOW()
   - FK constraint name: `fk_proposed_change_portfolio_id`
   - CHECK constraint name: `ck_proposed_change_status`

### Downgrade
- Drop `atlas_portfolio_proposed_change` table (indexes drop with it)
- Drop column `target_weight` from `atlas.strategy_fm_custom_portfolios`

### Test structure (import-level + env-gated integration)
Exactly mirrors `tests/migrations/test_092_portfolio_policy.py`.

Import-level tests:
- revision string
- down_revision = "092_atlas_portfolio_policy"
- upgrade/downgrade callable + zero positional args
- upgrade source contains table name + CHECK constraint name

Integration tests (ATLAS_INTEGRATION_TESTS=1):
- `atlas_portfolio_proposed_change` table exists with all required columns
- `target_weight` column exists on `strategy_fm_custom_portfolios`
- CHECK constraint rejects status values outside ('pending','applied','rejected')

## EC2 note
`alembic upgrade` is NOT run locally (Mac psycopg2 broken). Migration is written and tested
structurally. EC2 apply is deferred.

## Expected runtime
Migration is DDL-only (add column + create table). No data transforms. Sub-second on any sized DB.
