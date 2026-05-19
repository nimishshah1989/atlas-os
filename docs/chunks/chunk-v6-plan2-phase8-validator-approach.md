# Chunk: v6 Plan 2 Phase 8 — Walk-forward validator

**Date:** 2026-05-19
**Files:** `atlas/trading/v6/validator.py`, `tests/trading/v6/test_validator.py`

## Data scale

No DB query possible (EC2 access is SSH-only from this env). From migration 087:
- `atlas_v6_strategy_runs` is a new table with minimal rows — no scale concern.
- Walk-forward operates on in-memory OOSResult lists (8 windows).

## Chosen approach

Pure Python module — no pandas in the validator itself. The validator:
1. Builds 8 `WindowSpec` objects (growing-train, annual OOS)
2. Calls `run_simulation(session, config)` from `atlas.trading.v6.simulator` (Phase 7) —
   mocked in tests since Phase 7 is not yet committed
3. Computes OOS-IC retention per signal
4. Evaluates 9 goal-post constraints
5. Enforces holdout singleton via DB timestamp read-before-write

**Singleton enforcement:** Read `holdout_examined_at` from DB row inside a SELECT FOR UPDATE,
raise `HoldoutAlreadyExamined` if non-NULL, then write NOW(). This prevents race conditions
without an application-level lock.

## Wiki patterns checked

- `advisory-lock-concurrency.md` — considered, but a SELECT FOR UPDATE on the single run row
  is simpler and sufficient for non-concurrent usage.
- `decimal-not-float.md` — OOSResult fields use float (not money values); goal-post thresholds
  are constants, not financial storage. Decimal not required here.
- `idempotent-upsert.md` — used for `persist_oos_result` INSERT to `atlas_v6_strategy_runs`.

## Simulator import seam

Since `simulator.py` is not yet committed, `validator.py` does:
```python
try:
    from atlas.trading.v6.simulator import run_simulation, SimulationConfig, SimulationResult
except ImportError:
    run_simulation = None  # type: ignore[assignment]
    SimulationConfig = None  # type: ignore[assignment]
    SimulationResult = None  # type: ignore[assignment]
```
Tests monkeypatch `atlas.trading.v6.validator.run_simulation` with a fake that returns a
`SimulationResult`-compatible dict-or-dataclass.

## Edge cases

- `build_windows`: OOS end capped at 2022-12-31, hold-out is 2023-2025 (separate)
- `check_ic_retention`: IS_IC = 0.0 → division by zero; return `pass=True` (no signal to degrade)
- `evaluate_goal_post`: missing benchmark_vol → raise ValueError (not silent)
- `examine_holdout` on non-existent run_id → raise ValueError before DB check

## Expected runtime

Walk-forward on synthetic data (no real sim): < 1s. Full sim across 8 × 12 months of real
data on EC2: ~30-60 min (dominated by the simulator, not the validator harness).

## LOC estimate

Source: ~320 LOC (within 600 limit). Tests: ~280 LOC (within 800 limit).
