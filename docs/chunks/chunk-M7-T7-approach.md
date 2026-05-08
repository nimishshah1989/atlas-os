# Chunk M7-T7 Approach: 15 Strategy YAML Configs

## Task
Create 15 YAML strategy configuration files in `atlas/simulation/strategies/configs/`.

## Data scale
No database interaction. Pure config files. Loader (Task 8) will `glob` this directory and assert `len(configs) == 15`.

## Approach
Write YAML files directly — no Python, no SQL, no database. Three tiers:
- **stocks_only** (5): momentum_aggressive, momentum_moderate, momentum_conservative, sector_rotation_concentrated, sector_rotation_diversified
- **blend** (5): momentum_60_40, balanced_50_50, etf_led, defensive, sector_rotation_etf
- **fund_only** (5): l1_dominant, l2_dominant, l3_dominant, balanced, defensive

## Wiki patterns checked
- Binary Identity Tests Drive Config — YAML configs are the identity source for loader.py assertions
- No finance-critical patterns apply (no money/calculations in these files)

## Existing code reused
`atlas/simulation/strategies/` already existed with `__init__.py`. Created `configs/` subdirectory within it.

## Edge cases
- `name` field must match filename exactly (minus `.yaml`) — validated by acceptance check
- `threshold_overrides: {}` must be empty dict, not null — YAML `{}` is correct
- `fund_tier_filter` only present on fund_only configs; blend configs use `stock_allocation_pct` + `etf_allocation_pct`
- stocks_only configs omit allocation split fields (single-asset class)

## Expected runtime
Instantaneous — file writes only.

## Validation
`python -c "import yaml, glob; ..."` confirms all 15 files parse cleanly and name == filename.
