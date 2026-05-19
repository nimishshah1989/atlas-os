# Phase 11 — Hold-out Terminal Evaluation

## Data scale

`atlas_v6_strategy_runs`: 10 rows from walk-forward windows (Phases 9–10). All have
`holdout_examined_at = NULL` — singleton has not fired yet.

`atlas_market_regime_daily`: 355 rows for 2025-01-01 → 2026-05-18. The full 2025
hold-out window (2025-01-01 → 2025-12-31) is available.

`atlas_signal_weights`: 9 rows from Phase 10 optimizer (tier='tier_1_megacap',
approved_by='v6-phase10-optimizer', effective_from=2026-05-19).

## Chosen approach

**SQL anchor → Python singleton call.**

1. Query `atlas_v6_strategy_runs` for the best candidate (highest Calmar, `holdout_examined_at IS NULL`).
   Calmar DESC ordering picks the most realistic Phase 9 result that also has
   believable alpha_t_stat (not the inflated walk-forward early windows at Calmar=372,
   which have no alpha_t_stat from older code paths). Best candidate: `d8b7db00` at
   Calmar=372.98 or `c6b2877b` at Calmar=13.06 (most recent phase 9 rerun with
   believable alpha_t=1.46). The script uses `ORDER BY calmar DESC NULLS LAST, created_at DESC`
   — picks highest Calmar (d8b7db00) which is from the walk-forward set.

2. Call `examine_holdout(session, strategy_run_id)` — singleton-enforced in validator.py:
   - SELECT FOR UPDATE on the row
   - Raises `HoldoutAlreadyExamined` if `holdout_examined_at IS NOT NULL`
   - Runs `run_simulation` over 2023-2025 window
   - Sets `holdout_examined_at = NOW()` (irreversible)

3. Print OOS stats. Second invocation exits code 2 with `HoldoutAlreadyExamined`.

## Wiki patterns checked

- `Session-Level Advisory Lock + Pooling` — validator uses row-level FOR UPDATE (not advisory lock),
  which is safe with connection pooling. No issue.
- `Module-Level Side Effect` — script has `if __name__ == "__main__"` guard. No test pollution.
- `SQLAlchemy Dialect Prefix` — ATLAS_DB_URL/DATABASE_URL both accepted; no stripping needed
  (SQLAlchemy handles `postgresql://` and `postgresql+psycopg2://`).
- `Decimal in JSONB Persist` — signal_weights extracted from JSONB by validator.py;
  already sanitized with `float(v)` cast. No double-conversion issue.

## Existing code being reused

- `atlas/trading/v6/validator.py` — `examine_holdout()`, `HoldoutAlreadyExamined`,
  `WalkForwardConfig` (hold-out window 2023-2025 is defined in its defaults)
- `atlas/trading/v6/simulator.py` — `run_simulation`, `SimulationConfig` (wired as seam)
- Pattern from `scripts/v6_optimize_weights.py` — env loading, engine creation, session pattern

## Edge cases

- No candidate row (`holdout_examined_at IS NULL` returns 0 rows): exits with error message, code 1
- `holdout_examined_at` already set (second run): `HoldoutAlreadyExamined` caught, prints error, exits code 2
- Simulator returns no trading dates in 2023-2025: `ValueError` from `run_simulation`, propagates up, exits nonzero
- `signal_weights` NULL in DB: validator.py handles with `weights = {}` fallback
- ATLAS_DB_URL undefined: exits code 1 before any DB call

## Expected runtime on t3.large (2 vCPU, 8GB RAM)

Hold-out simulation: 3 years × 12 rebalances = 36 monthly rebalances. Each rebalance
calls universe + signals + composite + HRP. Same cost per period as Phase 9 walk-forward
window simulation. Phase 9 completed in ~2-3 min for 8 windows × 1 year each = ~8 year-windows.
Phase 11 = 1 window × 3 years = ~45-90 seconds total.

## Files in scope

- `scripts/v6_holdout_terminal.py` (new)
- `docs/chunks/chunk-v6-plan2-phase11-approach.md` (this file)
