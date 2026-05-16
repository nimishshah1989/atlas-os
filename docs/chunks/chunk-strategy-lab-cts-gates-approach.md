# Approach: Weinstein/CTS Stage Gates + RS Hysteresis — Genome Engine

## Data scale
- atlas_stock_metrics_daily: ~2M rows (US backfill complete)
- All computation is in-memory numpy on (n_stocks × n_days) arrays — no DB calls in this module
- genome.py, perception.py, decision.py, simulator.py are pure Python/numpy layers

## Chosen approach
- Pure dataclass field additions + numpy vectorized functions
- No new DB dependencies; CTS columns are optional (safe defaults via `_safe_pivot`)
- Backward-compatible: `stage`, `ppc`, `npc`, `contraction` params are all optional with defaults

## Changes

### genome.py
- Add 7 new `Layer1Perception` fields with Python defaults (all have `= <default>` so old JSON round-trips still work via `from_dict`)
- Add 3 `__post_init__` assertions for hysteresis invariants
- Update `GenomeFactory.random()` and `from_optuna_trial()` with new field generation
- `stage3_blocks_entry` is hardcoded `True` in both factories — never optimized away

### perception.py
- Add `derive_rs_exit_state()` mirroring `derive_rs_state()` but using exit (lower) thresholds
- Uses `rs_strong_exit_pct` and `rs_leader_exit_pct` instead of entry cutoffs

### decision.py
- `compute_conviction`: add `ppc` and `contraction` kwargs with defaults=0; additive boost after base clip formula, before final clip
- `apply_entry_rules`: add `stage` optional ndarray; when present, apply Weinstein gate after existing heat/regime/drawdown blocks
- `apply_exit_rules`: add `npc` and `npc_overrides_min_hold` kwargs; NPC triggers immediate exit ignoring min_hold_days

### simulator.py
- `_safe_pivot()` helper for optional CTS columns (defaults Stage=2, PPC/NPC/contraction=0)
- `derive_rs_exit_state` computed once alongside `rs_state`
- `_run_window` receives new arrays; exit uses `rs_exit_state` (hysteresis); entry uses `cts_stage`
- `prev_rs` tracks exit state for continuity

## Edge cases
- Old metrics_df without CTS columns: `_safe_pivot` returns full-grid defaults
- NaN in CTS columns: `fillna(default)` before `.astype(np.int8)`
- hysteresis invariant: `rs_leader_exit_pct < rs_leader_cutoff_pct` enforced in `__post_init__`
- `from_dict` with old JSON (no new fields): Python dataclass defaults handle this automatically

## Expected runtime
- No additional DB queries; pure numpy matrix ops; negligible overhead (<1% of simulation time)

## Wiki patterns checked
- `atlas/trading/perception.py`: existing `derive_rs_state` pattern reused for exit variant
- `atlas/trading/simulator.py`: existing `_pivot` pattern extended with `_safe_pivot`
