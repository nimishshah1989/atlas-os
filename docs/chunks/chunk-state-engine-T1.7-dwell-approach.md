# Chunk: State Engine T1.7 — dwell.py (cohort baselines + urgency derivation)

## Data scale
Pure pandas — no DB I/O. Episode panels are expected in the range of 5K–50K rows
(~500 stocks × ~100 state transitions historically). Well under 100K so pandas
vectorised operations are fine.

## Chosen approach
- `compute_cohort_dwell_baselines`: vectorised groupby aggregation. Episode
  detection via `cumsum` on `dwell_days == 0` per (instrument, state) run.
  pandas `.agg()` with named lambdas for quantiles. No iterrows.
- `derive_urgency`: pure dict lookup + two inequality comparisons. O(1).
  Guards use `is not None` (not truthiness) to handle p25/p75 == 0 edge case.

## Wiki patterns checked
- PRD Golden Example Testing — tests use the spec's exact golden values.
- Zero-Value Truthiness Trap — `is not None` used for p25/p75 guards, not `if p25`.

## Existing code reused
- Module structure follows cohorts.py and classifier.py (from __future__ import
  annotations, type hints everywhere).
- No DB dependency (pure computation module, same as features.py).

## Edge cases
- Empty panel: early-return DataFrame with correct column schema.
- Missing cohort_baseline keys: function returns "normal" (or "n/a" for inactive
  states) without raising.
- p25 == 0: handled by `is not None` guard.
- State not in _URGENCY_RULES: defaults to ("n/a", "n/a").

## Urgency polarity rationale
- Stage 2A (entry): short dwell = fresh window = URGENT; long dwell = LATE.
- Stage 2B (hold): short = NORMAL; long = LATE.
- Stage 2C (exit): short = LATE (reversion coming); long = URGENT (trim now).
- Stage 3 (confirm): short = NORMAL; long = URGENT (exit).
- Stage 1 / Stage 4 / Uninvestable: "n/a" (not actionable).

## Expected runtime on t3.large
< 50ms for 50K-row panel. Pure pandas vectorised; no loops.
