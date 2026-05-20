# Chunk 2.2 — House-Default Policy Seed: Approach

## What this builds
A one-shot idempotent seed script (`scripts/seed_house_policy.py`) that inserts
the single house-default row into `atlas.atlas_portfolio_policy`. Tests live in
`tests/scripts/test_seed_house_policy.py`.

## Table schema (from migration 092)
- `Numeric(6,4)` for pct columns (cash_floor_pct, max_per_stock_pct, etc.)
- `Numeric(5,4)` for rank columns (min_within_state_rank, min_rs_rank)
- `ARRAY(Text)` for buy_states
- CHECKs: instrument_universe IN ('direct_equity','etf','mutual_fund','mixed'),
  rebalance_cadence IN ('daily','weekly','monthly'),
  NOT is_house_default OR portfolio_id IS NULL
- Partial unique index on (is_house_default) WHERE is_house_default

## Data scale
No query needed — this is a single-row INSERT. No scale concerns.

## Percentage storage convention
Percentages stored as **whole-number percent** (e.g. `5` for 5%, `15` for 15%).
Rationale: `Numeric(6,4)` with whole-number pct gives range 0-9999.9999, more
than enough headroom; readable at a glance in psql without mental division.
Rank columns (min_within_state_rank, min_rs_rank) stored as **fractions** (0..1)
because they ARE ranks, not percent. `Numeric(5,4)` max = 9.9999 which covers 0..1 well.

## DB-engine import
`from atlas.db import get_engine` — single process-wide engine via `@lru_cache`.

## Idempotency approach
`INSERT ... ON CONFLICT DO NOTHING` keyed on the partial unique index
`uix_portfolio_policy_house_default`. PostgreSQL will conflict on the second
run since the index is `UNIQUE WHERE is_house_default`. This is the same
pattern used in `seed_signal_weights.py`.

The script prints "Inserted 1 new house-default row" or "House-default row
already exists — no changes made." based on `result.rowcount`.

## Wiki patterns checked
- `seed_signal_weights.py`: ON CONFLICT DO NOTHING pattern confirmed
- `seed_strategy_backtests.py`: `engine = get_engine()` + `engine.begin()` conn context

## Existing code reused
- `from atlas.db import get_engine` — identical to all seed scripts
- structlog for logging (same as all seed scripts)

## Edge cases
- Second run: conflict fires, rowcount=0, prints "already exists"
- partial unique index guarantees at most one is_house_default row even if
  the ON CONFLICT somehow failed (belt-and-suspenders)
- NULL for trailing_stop_pct and portfolio_id explicit in the INSERT

## Test strategy (TDD)
Structural tests (no DB required):
1. HOUSE_POLICY_DEFAULTS constant exists and has all required keys
2. pct fields are Decimal and >0
3. rank fields are Decimal in [0,1]
4. buy_states is a list of strings
5. instrument_universe / rebalance_cadence pass their CHECK values
6. INSERT_SQL contains "ON CONFLICT DO NOTHING"
7. main() function exists and is callable
8. is_house_default=True in defaults
9. portfolio_id=None in defaults
10. trailing_stop_pct=None in defaults

DB-gated integration tests (behind ATLAS_INTEGRATION_TESTS env flag):
- Exactly one house-default row after seed
- Second run is idempotent (still exactly one row)
- All field values match the constants

## EC2 execution
Deferred. Mac has no DB connectivity. Script is correct and tested structurally;
EC2 step is: `python scripts/seed_house_policy.py` after migration 092 is applied.

## Expected runtime
Single-row INSERT — sub-second on any hardware.
