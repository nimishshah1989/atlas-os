# Task 9 — Optuna Optimizer Approach

## Summary

Thin wrapper around `optuna.Study` that exposes `run_trials`, `best_genome`, and
`get_parameter_importance`. All genome construction is delegated to the already-tested
`GenomeFactory.from_optuna_trial`.

## Data scale

No DB reads in this module. The optimizer is a pure compute wrapper; persistence of
study state is handled by Optuna's own RDB storage layer when `storage=` is set.
In tests, `storage=None` (in-memory).

## Chosen approach

- `optuna.create_study(direction="maximize")` with TPE sampler (seed=42 for
  reproducibility in tests) and MedianPruner for longer production runs.
- `run_trials` wraps the user objective so that Optuna sees `float` and the caller
  works with `Genome` objects only.
- `best_genome` reconstructs from `best_trial.params` using `FixedTrial`, which
  replays all `suggest_*` calls with the known-best values.
- `get_parameter_importance` uses `optuna.importance.get_param_importances` — needs
  at least 2 complete trials with a functional evaluator backend.
- `production()` classmethod wires to `RDBStorage` with pool settings matching
  the rest of the codebase (pool_size=5, max_overflow=10).

## Wiki patterns checked

- Bounded context rule: `atlas.trading.*` cannot import `atlas.compute`, `atlas.api`,
  etc. This module only imports `optuna` + `structlog` + local `atlas.trading.genome`.

## Existing code reused

- `GenomeFactory.from_optuna_trial(trial)` — handles all `suggest_int`/`suggest_float`
  calls and cascade constraint logic. No reimplementation needed.
- `FixedTrial(params)` — standard Optuna pattern for replaying best params.

## Edge cases

- No trials completed yet: `best_trial` raises `ValueError` — caught by try/except in
  `best_genome()`.
- `get_parameter_importance` requires a valid sklearn backend; wrapped in try/except to
  return `{}` on failure (e.g., insufficient data).
- Cascaded parameter constraints in `from_optuna_trial` (leader > strong > average > weak)
  mean `FixedTrial` replay must use the same parameter call order — it does because
  `from_optuna_trial` is called identically in both paths.

## Expected runtime

- 5-trial in-memory test run: < 1 second.
- Production 200-trial run with real objective: depends on simulator, typically 30–90
  minutes on t3.large (2 vCPU). TPE is sequential; parallel workers via `n_jobs` not
  used to avoid DB connection storms.

## Status: approved — proceeding to implementation
