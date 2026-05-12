# Chunk SP09 Pocket Pivot Volume — Approach

## Task
Add `add_pocket_pivot_volume()` to `atlas/compute/cts/primitives.py` using TDD.

## Data Scale
This is a compute primitive — it operates on in-memory DataFrames passed by callers.
Typical use: 500 instruments × 504 trading days = ~252K rows. Well under 1M, so
pandas vectorised is appropriate with per-group loop for the rolling max (same
pattern as `add_atr14`).

## Approach
- Pure pandas vectorised within each group (per-instrument groupby loop)
- `is_down = close < close.shift(1)` — strict less-than (Morales definition)
- `down_vol = volume.where(is_down, other=np.nan)` — mask non-down days to NaN
- `pp_thresh = down_vol.shift(1).rolling(window, min_periods=1).max()` — look at prior bars only (shift(1) excludes current bar from its own lookback)
- `is_pp_volume = pp_vol_threshold.notna() & (volume > pp_vol_threshold)` — NaN threshold means no prior down day, signal cannot fire

## Wiki Patterns Checked
- Existing `add_atr14` uses per-group loop with `pd.Series(index=out.index)` accumulation — same pattern adopted here
- `add_volume_ratio` uses groupby transform for simple rolling mean — pocket pivot needs per-group loop because `where` + shift + rolling.max on masked series doesn't vectorise cleanly across groups

## Existing Code Reused
- Same per-group loop pattern as `add_atr14` (lines 87–98 in primitives.py)
- Same `out.copy().sort_values([group_col, "date"])` preamble

## Edge Cases
- Short history (<= window bars): `min_periods=1` gives threshold once any down day appears; 0 prior down days → NaN threshold → `is_pp_volume=False`
- All up-close days in window: NaN threshold → signal cannot fire (correct)
- Volume = 0: NaN guard not needed here (volume=0 on a down day would set a 0 threshold, which is benign — any positive volume exceeds it; but real data never has 0 volume)
- Multi-instrument: per-group loop isolates each instrument's down-day history

## Expected Runtime
~252K rows, per-group loop over 500 instruments: each group processes ~504 rows.
Expected runtime < 5 seconds on t3.large.

## Files Modified
- `atlas/compute/cts/primitives.py` — add `add_pocket_pivot_volume`
- `tests/unit/cts/test_primitives.py` — add 4 test functions + update import
