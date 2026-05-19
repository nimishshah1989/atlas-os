# Chunk: Consolidation Phase 4 — IC Harness for Legacy Signals

## Task context
Implement Tasks 4.1, 4.2, 4.3 from the atlas-signal-consolidation plan (Phase 4).

## Schema discoveries (from static analysis — DB not directly probed due to permission gate)

### Migration chain
- 087: `087_views_inline` (already applied)
- 088: `088_alembic_marker` (no-op reconciliation, down_revision=087_views_inline)
- 089: reserved by Agent A
- **090**: our migration (`090_legacy_validation_kind`), down_revision=`088_alembic_marker`

### atlas_component_validation PK (from migration 079)
PK = `(component_name, badge, horizon_days, as_of_date)` — NOT `(as_of_date, component_name, badge)` as the plan's UPSERT SQL incorrectly states. Must use the actual PK in ON CONFLICT clause.

### Non-null required columns (from migration 079)
`threshold_range` and `implied_action` are NOT NULL. The harness must supply sentinel values for legacy candidates (e.g. `'continuous'` and `'investigate'`).

### ICResult.q5_q1_spread
`ICResult` has no `q5_q1_spread` field (confirmed from `ic_engine.py`). The plan's `hasattr` guard handles this, but we need to call `compute_quantile_spread` separately from `ic_engine.py` to get the actual spread value. This avoids returning 0.0 for all signals.

### CTS columns
Plan assumes `ppc_score`, `npc_score`, `contraction_score` in `atlas_cts_stock_signals`. Cannot confirm without DB access. Added NOT EXISTS guard: if query returns 0 rows, signals get `status='decorative'` with `n_observations=0` (honest, not fabricated).

### Legacy boolean triggers
`transition_trigger` and `breakout_trigger` assumed in `atlas_stock_states_daily`. Same NOT EXISTS guard.

## Approach

### Task 4.1 — Migration 090
- revision = `090_legacy_validation_kind`
- down_revision = `088_alembic_marker`
- Adds `component_kind VARCHAR(32) NOT NULL DEFAULT 'state_engine_tier'`
- CHECK constraint: `component_kind IN ('state_engine_tier','legacy_candidate')`

### Task 4.2 — ic_harness.py
- `classify_ic_status(ic_ir, q5_q1_spread) -> str` uses plan's thresholds verbatim
- `LegacySignal` dataclass: name, horizon_days, loader, description
- `LEGACY_SIGNAL_CATALOG`: 6 entries matching plan exactly; nav_state loader returns empty DF
- `run_legacy_ic_harness`: calls `compute_quantile_spread` separately (not via ICResult.q5_q1_spread)
- `persist_legacy_ic_results`: uses correct PK `(component_name, badge, horizon_days, as_of_date)` in ON CONFLICT; badge='Continuous', threshold_range='continuous', implied_action='investigate' as sentinels

### Task 4.3 — CLI validate-legacy
- argparse pattern (not click), matching existing `cli.py` + `cli_states.py` convention
- `_states_validate_legacy_cmd(args)` function in `cli_states.py`
- Registered in `cli.py` under `states_sub` as `validate-legacy` subcommand
- Appends Phase 4 section to `docs/audits/state-engine-phase2-ic-2026-05.md` (cannot run live because DB permission gate — verdicts will be set based on schema availability)

## Edge cases
- Empty CTS table: signals get `n_observations=0`, `status='decorative'`
- nav_state: skipped by design (fund-level harness deferred)
- NULL handling: plan's `IS NOT NULL` WHERE clause handles NULLs
- Missing `component_kind` column until 090 runs: migration gate ensures upgrade runs first

## Files to create/modify
- CREATE: `migrations/versions/090_legacy_validation_kind.py`
- CREATE: `atlas/intelligence/states/ic_harness.py`
- CREATE: `tests/intelligence/states/test_ic_harness.py`
- MODIFY: `atlas/trading/cli_states.py` (add `_states_validate_legacy_cmd`)
- MODIFY: `atlas/trading/cli.py` (register `validate-legacy` subparser)
- MODIFY: `docs/audits/state-engine-phase2-ic-2026-05.md` (append Phase 4 section)

## LOC budget
- ic_harness.py: ~150 LOC (well under 400 limit)
- cli_states.py: +35 LOC (stays under 400 limit)
- test_ic_harness.py: ~100 LOC (well under 800 limit)
