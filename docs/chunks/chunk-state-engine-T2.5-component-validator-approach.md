# Chunk T2.5: Per-Component IC Validation — Approach

## Task
Consolidated Task 2.5.1 + 2.5.2 + 2.5.3: migration 079, component_validator.py, CLI subcommand.

## Data scale (skipped live DB query — psycopg2 not available on Mac per MEMORY.md)
Expected: atlas.atlas_stock_state_daily ~273K rows (from migration 078 context).
atlas_stock_metrics_daily: similar scale. de_equity_ohlcv: multi-million rows (partitioned by year).
The OBV/ATR computation loads per-instrument with WHERE date BETWEEN; acceptable.

## Approach
- Migration 079: new table `atlas.atlas_component_validation` with PK (component_name, badge, horizon_days, as_of_date). CHECK constraint on status. Follows pattern from migration 072-076.
- component_validator.py: ~280 LOC. Reuses ic_engine.compute_ic_over_window + forward_returns module. Factor loading from atlas_stock_state_daily (rs_rank_12m), atlas_stock_metrics_daily (realized_vol_63), and on-the-fly OHLCV computation (obv_slope_50d, atr_contraction_ratio). Caches factor panels per component_name to avoid recomputation across tiers.
- CLI: adds `validate-components` to `states` subparser. Function in cli_states.py imported into cli.py.

## Wiki patterns checked
- Idempotent Upsert: ON CONFLICT DO UPDATE on PK — used in _persist()
- SQLAlchemy Dialect Prefix: strip postgresql+psycopg2:// prefix when constructing raw psycopg2 URL

## Existing code reused
- atlas/intelligence/validation/ic_engine.py: compute_ic_over_window (ICResult dataclass)
- atlas/intelligence/validation/forward_returns.py: load_price_matrix, compute_forward_returns
- tests/migrations/test_076_seed.py + test_078_vol_volume_swap.py: same pattern for integration tests

## Edge cases
- Empty factor panel: log warning, skip entry, continue
- NaN/inf in OBV slope or ATR ratio: filtered with pd.notna(v) and np.isfinite(v) before appending
- Zero ic_std: ir defaults to 0.0 → "decorative"
- neutral_informational implied_action: any |IR|>0.4 returns "validated"
- Q5-Q1 spread with only one tier present (all factor=1 or all factor=0): returns 0.0

## LOC counts
- component_validator.py: ~270 LOC (under 400 limit)
- cli_states.py: 356 + ~25 = ~381 LOC (under 600 limit)
- cli.py: 518 + ~10 = ~528 LOC (under 600 limit)

## Expected runtime on t3.large
- RS rank: SQL load only, fast (<5s for 273K rows)
- Realized vol 63: SQL load, fast
- OBV slope + ATR ratio: Python rolling on OHLCV; ~500 instruments x 2 years = ~250K rows → <2 min total
- Full validate_all_components: ~5-10 min on t3.large
