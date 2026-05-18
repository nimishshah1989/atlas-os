# Chunk: State Engine Task 1.4 — classifier.py (Uninvestable + Stage 4)

## Data scale
No DB query needed — classifier.py is a pure-function module. No table reads.
Thresholds are passed in as a pre-loaded dict (loaded once by caller via `load_active_thresholds()`).

## Chosen approach
Pure Python predicate functions (no pandas, no SQL). Each state is a standalone
function taking scalar float/int inputs and a thresholds dict. Tasks 1.5 and 1.6
will extend the same file with the remaining 5 states and the panel orchestrator.

Reasons:
- Per-row predicates are inherently scalar: no benefit from vectorization at this layer.
- The orchestrator (Task 1.6) will apply them over a DataFrame via vectorized `.apply()` or `np.vectorize`. The predicates themselves must be scalar and testable in isolation.
- NaN guard at entry: `_is_nan()` helper, checked before any arithmetic. Returns False (not the state) when inputs are missing.

## Wiki patterns checked
- `patterns/binary-identity-tests-drive-config.md` — PASS/FAIL tests are the right gate for threshold correctness.
- `patterns/decimal-not-float.md` — thresholds use float (ThresholdValue.value: float), inputs are float. No money column in classifier.py itself.

## Existing code being reused
- `atlas.intelligence.states.thresholds.ThresholdValue` — frozen dataclass with `.value: float`.
- `atlas.intelligence.states.thresholds.get()` — lookup helper; raises KeyError on missing key (no silent defaults). Classifier tests provide explicit threshold dicts to avoid DB dependency.

## Edge cases
- NaN in any input to `classify_stage_4` → returns False (not Stage 4). Explicit `_is_nan()` guard.
- `classify_uninvestable` inputs are `float` / `int` — NaN is not expected on liquidity_score and data_gap_count (they come from aggregated counts), but close can be NaN → treated as penny (< any positive threshold → uninvestable). Acceptable behavior.
- `get_threshold()` raises KeyError if threshold not present and no default — tests must supply complete threshold dicts.
- `sma_150_slope == 0.0` → disqualifies Stage 4 (condition is `< 0`, strict).

## Expected runtime
Not applicable — pure Python scalar functions. Zero I/O.

## Files
- Create: `atlas/intelligence/states/classifier.py`
- Create: `tests/intelligence/states/test_classifier.py`
