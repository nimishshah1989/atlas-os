# chunk: state-engine-T1.6 — classify_state_panel orchestrator
date: 2026-05-18

## What we're building
Append `classify_state_panel` to `atlas/intelligence/states/classifier.py`.
It applies the 7 per-state predicates over a (instrument_id × date) feature
panel and returns a result DataFrame with state bookkeeping columns.

## Data scale
No DB query needed — the orchestrator receives a pre-built features DataFrame
from the caller. The DB-sourced thresholds are already loaded by the caller.
Panel size in production: ~2000 instruments × ~252 days = ~500K rows per
backfill run; ~2000 rows per nightly incremental.

## Approach chosen
`pd.iterrows()` with per-instrument state carry-forward (dict).
- Spec explicitly calls for iterrows in V1 and defers vectorization to Phase 2.
- Nightly incremental (~2K rows) finishes in <1s. Full backfill (~500K rows)
  will be slow (~5 min) but acceptable for a one-time backfill job.
- Correct > fast for V1.

## Existing code being reused
- All 7 predicates in `classifier.py` (Tasks 1.4 + 1.5).
- `_is_nan` helper already in classifier.py.
- `ThresholdValue` from `atlas.intelligence.states.thresholds`.

## Priority order
1. uninvestable  (disqualify first)
2. stage_4       (hard decline — clear disqualifier)
3. stage_3       (topping — must catch before re-entering 2x)
4. stage_2a      (fresh breakout — transition gate, prior must be 1 or 4)
5. stage_2c      (extended — must check before 2b so 2b only fires on "clean" runs)
6. stage_2b      (confirmed — residual mid-stage-2)
7. stage_1       (base — residual)

## State-transition bookkeeping
- `prior_state` seed: "stage_1" (safe default on first row per instrument)
- `state_since_date`: set to current date on transition, carried forward otherwise
- `dwell_days`: (current_date - state_since_date).days
- `days_in_stage_2`: increments each row when prior is 2a/2b/2c; resets to 0 otherwise

## Edge cases
- NaN/None in numeric columns: `_value_or_nan` normalizes before predicate calls
- Zero denominators: guarded inside predicates; orchestrator passes NaN for 0 denominators
- Instrument appears only once (single row): dwell_days = 0, state_since = that date
- Date type: features.date may be Python date or pd.Timestamp; pd.to_datetime handles both

## Expected runtime
- Nightly (~2K rows): <1s
- Full backfill (~500K rows): ~5min on t3.large (acceptable, background job)

## LOC budget
classifier.py is currently 211 LOC. Appending ~170 LOC brings it to ~381 LOC,
under the 400 LOC file-size hook limit. Tight but safe.

## Files modified
- atlas/intelligence/states/classifier.py (append)
- tests/intelligence/states/test_classifier.py (append 6 orchestrator tests)
