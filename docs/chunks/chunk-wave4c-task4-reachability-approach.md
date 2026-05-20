# Wave 4C Task 4 — Stage 2B/2C Reachability Fix

## Finding: CASE A — Gap exists

The reachability gap is real. In `classify_state_panel`, `in_stage_2` is computed as:

```python
in_stage_2 = is_currently_in_2 and trend_ok
```

where `is_currently_in_2 = prior in ("stage_2a", "stage_2b", "stage_2c")`.

A stock first observed with `prior = "stage_1"` (the default for new instruments) and `days_in_stage_2 = 0` will always enter Stage 2A (since the freshness gate `days_in_stage_2 <= 21` passes trivially). It then spends 21 days in 2A before advancing to 2B — even if its structural indicators already show a confirmed or mature uptrend.

## Approach

**Cold-start structural admission path.** When an instrument is observed for the first time in the panel (`is_cold_start = iid not in prior_state_per_instr`), and the full uptrend MA stack is confirmed (`trend_ok`), evaluate structural 2C/2B conditions before checking Stage 2A.

New helper: `_cold_start_2bc_state(close, sma_50, atr_14, atr_14_50d_avg, distribution_days_5d, thresholds)` returns "stage_2c", "stage_2b", or "" (falsy).

- 2C structural: `close/sma_50 > theta_extension` OR `atr_14/atr_14_50d_avg > theta_atr_expansion`
- 2B structural: `distribution_days_5d == 0` AND `close > sma_50` (MA stack already confirmed by caller)

The `days_in_stage_2` counter is initialised to `theta_fresh_days + 1` (=22) so subsequent rows continue in the normal 2B/2C range without re-entering 2A.

A sentinel `_cold_start_synthetic_days` is used to preserve the synthetic counter through the state-transition bookkeeping block (which would otherwise reset it to 1 on any state change).

## What stays unchanged

- Stage 1 → 2A → 2B → 2C normal progression: fully preserved. The cold-start path fires only on `is_cold_start = True`. On day 2+ of observation, `is_cold_start = False` and the standard path applies.
- Fresh breakout regression: a stock that was genuinely in stage_1 yesterday (seen in the panel, `is_cold_start = False`) still enters 2A on the transition day.
- No structural conditions loosened. The 2B/2C predicates themselves are untouched.
- Stage 1/3/4/uninvestable logic: untouched.

## Tests added (3 net new)

1. `test_stage_2b_direct_admission_from_cold_start` — cold-start 2B fixture (close/sma_50=1.05, no distribution) → stage_2b
2. `test_stage_2c_direct_admission_from_cold_start` — cold-start 2C fixture (close/sma_50=1.20 > theta_extension=1.10) → stage_2c
3. `test_stage_2b_normal_progression_from_stage_1_still_goes_through_2a` — regression: stock seen on day 1 (stage_1), transitions on day 2 → still stage_2a

## LOC

- Classifier source: 500 lines (limit 600) — passes
- Test file: 1006 lines (limit 800 with pre-existing `allow-large` marker) — marker retained

## IC re-validation note

This fix changes which stage stocks are assigned at first observation. Task 5 IC re-validation is required before shipping. The cold-start path affects only the first row per instrument in any panel run; subsequent rows are unaffected.
