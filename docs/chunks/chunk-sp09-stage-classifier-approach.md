# Chunk SP09-T3 Approach: Weinstein Stage Classifier

## Data Scale
- This is a pure compute module, no direct DB reads
- Input: DataFrame of daily price bars per instrument (200 rows typical for tests)
- At production scale: ~1K instruments x 252 bars = ~252K rows — pandas vectorized is fine
- No SQL needed; all computation is rolling window arithmetic on in-memory frames

## Chosen Approach
Pure pandas vectorized via `add_sma_slope` from primitives. No row loops.

Stage logic:
- 4 conditions built as boolean Series masks
- `np.select(conditions, choices, default=np.nan)` — single vectorized pass
- Stage is stored as Python `object` array (None for pre-SMA rows, int for valid rows)
- `is_stage1b` computed as boolean Series: stage==1 AND proximity <= 3%

Key boundary: `prox <= Decimal("0.03")` uses `<=` not `<` — boundary test verifies exactly-3% case.

## Wiki Patterns Checked
- `computation-boundary-pattern`: float internally (numpy), Decimal only at storage edge. Here the proximity comparison uses `Decimal("0.03")` directly — valid because pandas will coerce to float64 for the comparison. The `prox` Series is float.
- `decimal-not-float`: `is_stage1b` threshold is expressed as `Decimal("0.03")` per spec.

## Existing Code Reused
- `atlas/compute/cts/primitives.py::add_sma_slope` — appends `sma_{period}` and `sma_{period}_slope` columns
- Test pattern from `tests/unit/cts/test_primitives.py` — same `_uptrend_df` style fixture

## Edge Cases
- Rows before SMA computable (< 150 bars): `has_sma = out[sma_col].notna()` gates all conditions; `np.select` returns `np.nan` which becomes `None` in object array
- Slope NaN before `slope_days` additional rows: also guarded by `has_sma` (slope is NaN before SMA is computable)
- Flat price (slope == 0): Stage 1 uses `>= 0` for slope (flat or rising = basing), Stage 2 uses `> 0` strictly
- `is_stage1b` proximity: `(sma - close) / sma` — correctly zero when close == sma, and negative when close > sma (not stage 1)

## Expected Runtime on t3.large
- 252K rows vectorized: < 1 second
- Test suite (6 tests, synthetic 200-row frames): < 0.5 seconds

## Files
- `atlas/compute/cts/stage.py` (new)
- `tests/unit/cts/test_stage.py` (new)
