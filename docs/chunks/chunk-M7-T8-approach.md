# Chunk M7-T8 Approach: loader.py + populate_strategy_configs()

## Data Scale
- 15 YAML files, each < 1KB. Pure file I/O, no large table reads.
- atlas.strategy_configs table: seeded by this chunk, starts at 0 rows.

## Approach
1. `StrategyConfig` dataclass — maps YAML fields. Optional fields (stock_allocation_pct, etf_allocation_pct, fund_tier_filter) default to None.
2. `load_config(name)` — reads single YAML from `configs/` dir by stem.
3. `load_all_configs()` — globs `*.yaml`, returns sorted list.
4. `populate_strategy_configs(engine)` — ON CONFLICT DO UPDATE upsert to `atlas.strategy_configs`, mirrors `populate_thresholds()` pattern.

## Key Bug Avoided: SQLAlchemy Param-Cast Collision
The spec provides `:config::jsonb` in the SQL — this is the known "SQLAlchemy Param-Cast Collision" bug from the wiki. SQLAlchemy's text() sees `:config::jsonb` and misparses it. Use `CAST(:config AS jsonb)` instead.

## Import Path
`from atlas.db import get_engine` — confirmed at `/Users/nimishshah/Documents/GitHub/atlas-os/atlas/db.py:def get_engine`.

## Edge Cases
- `threshold_overrides: {}` in YAML → `yaml.safe_load` returns `{}` (not None) but spec notes `or {}` fallback for safety
- blend-only fields absent from stocks/fund YAMLs → `raw.get(...)` returns None, stored as NULL in JSONB
- fund_tier_filter is a YAML list → loaded as Python list → JSON-serialized correctly

## Wiki Patterns Used
- Idempotent Upsert (45x seen) — ON CONFLICT DO UPDATE on `name` unique constraint
- SQLAlchemy Param-Cast Collision — CAST() not ::type inline

## Expected Runtime
< 1 second. 15 row upsert on t3.large is trivial.

## Tests
6 unit tests, no DB required for YAML loading. `populate_strategy_configs` tested by manual EC2 verification per spec.
