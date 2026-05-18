# Chunk: State Engine Task 2.1 — threshold_optimizer.py

## Data scale

atlas.atlas_state_thresholds: 18 active rows (from Task 1.3 approach doc).
factor + returns_wide passed in as DataFrames by caller — no direct DB reads
during optimization. Only apply_tuned_threshold() writes to DB (UPDATE + INSERT
on 18-row config table). No bulk I/O concern.

## Chosen approach

Pure Python/pandas/numpy IC grid sweep. Single-threshold sensitivity:
hold all other thresholds at current active values, vary one θ candidate
at a time, compute Spearman IC of the resulting 1/0 membership boolean
against forward returns, score with IR + Q5-Q1 spread.

Reuses `atlas.intelligence.validation.ic_engine.compute_ic_over_window()`.
The factor passed to ic_engine is the 1/0 membership boolean (not a
continuous factor) — Spearman rank correlation on a binary factor is
equivalent to a point-biserial correlation, which is the right metric for
state-membership predictive power.

## Wiki patterns checked

- Idempotent Upsert — apply_tuned_threshold uses ON CONFLICT DO UPDATE on
  (threshold_name, state_or_gate, as_of_date) to handle rerun safety.
- Decimal Not Float — threshold_value stored as Numeric; converted to float
  at python boundary (not money, pure classifier input). Acceptable per
  computation-boundary pattern.
- Binary Identity Tests Drive Config — gate constants _IR_THRESHOLD=0.4 and
  _Q5_Q1_MIN_ABS=0.005 match what the state validator (Chunk 9) used. Tests
  validate that a clearly-better cutoff is selected.

## Existing code reused

- `atlas/intelligence/validation/ic_engine.py` — compute_ic_over_window()
  signature: (factor: pd.DataFrame, returns_wide: pd.DataFrame) -> ICResult
  where factor has MultiIndex(date, instrument_id) and column 'factor'.
- `atlas/intelligence/states/thresholds.py` — module header / structlog style.
- `tests/intelligence/states/conftest.py` — existing test conftest (no changes needed).

## Edge cases

- Empty factor or returns_wide → return ThresholdTuningResult with optimal_value=None.
- All candidates have identical IC (constant returns) → no candidate passes gates;
  fallback to max-|IR| candidate, passed_gates=False.
- IR computation: ic_std=0 → IR=0.0 (not NaN) to avoid division-by-zero.
- _quantile_spread on binary factor: groups by 1.0 and 0.0; degenerate if only
  one group exists for a date (guard via nunique < 2 check).
- NaN propagation: mean_ic, ic_std may be NaN from compute_ic_over_window when
  n_observations < 2. Guard with `float(x) if not np.isnan(x) else 0.0`.

## Expected runtime

On t3.large (2 vCPU, 8GB RAM):
- 100 stocks × 60 days × 5 candidates: trivial — <1s total.
- 500 stocks × 252 days × 10 candidates: ~5-10s (pandas groupby on ~1.26M rows,
  pure vectorized — acceptable for a nightly sweep job).
- No memory concern: each candidate sweep processes the same factor DataFrame;
  no duplication across candidates.

## Files

- `atlas/intelligence/states/threshold_optimizer.py` (new, ~210 LOC)
- `tests/intelligence/states/test_threshold_optimizer.py` (new, 4 tests)
