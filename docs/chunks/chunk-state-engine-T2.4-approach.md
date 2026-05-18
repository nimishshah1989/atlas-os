# Chunk: State Engine Task 2.4 — IC-Validated Vol/Volume Swap

**Date:** 2026-05-18
**Status:** approach

## Data scale

- `atlas_stock_metrics_daily`: 273k rows (from IC investigation)
- `atlas_state_thresholds`: ~20 active rows (tiny)
- Migration is a surgical UPDATE + INSERT, no bulk ops needed

## Chosen approach

Four surgical changes to existing classifiers + one new migration:

### Change 1: Stage 1 vol metric
- Remove `atr_14 / close < theta_low_vol` (IR -0.18, decorative)
- Add `atr_14 / atr_14_252d_avg < theta_contraction` (IR -0.48, validated)
- New param: `atr_14_252d_avg: float`
- NaN guard: if `atr_14_252d_avg <= 0` or NaN, predicate passes (conservative)

### Change 2: Stage 2A volume requirement
- Remove `volume_today` and `volume_50d_avg` params from `classify_stage_2a`
- Remove the `volume_today > θ_vol_mult × volume_50d_avg` conjunct (IR 0.15, decorative)
- Simpler function signature; volume columns stay in feature DF for other uses

### Change 3: Stage 3 OBV slope topping signal
- Add `obv_slope_50d: float` param to `classify_stage_3`
- Extend `topping_price` to: `close < sma_50 OR sma_50_slope < 0 OR obv_slope_50d < theta_obv_slope_neg`
- OBV deterioration is an alternative trigger (OR, not AND)
- θ_obv_slope_neg seeded at 0.0 (negative OBV slope triggers the signal)

### Change 4: within_state_rank formula
- Old: `(freshness + rs_rank_12m) / 2`
- New: `0.4 * freshness + 0.3 * rs_rank_12m + 0.3 * realized_vol_rank`
- `realized_vol_rank` = cross-sectional percentile of `realized_vol_63` per-day
- Load `realized_vol_63` via SQL join in `_apply_dwell_and_urgency`

## Wiki patterns used
- [Idempotent Upsert](patterns/idempotent-upsert.md) — ON CONFLICT DO NOTHING for migration
- [Computation Boundary](patterns/computation-boundary-pattern.md) — NaN guards on new feature cols

## New feature columns needed in cli.py
- `atr_14_252d_avg`: `out["atr_14"].rolling(252, min_periods=252).mean()`
- `obv_slope_50d`: cumulative OBV → slope(obv, 50)
  - OBV: `(volume * sign(daily_ret)).cumsum()` — standard OBV definition
  - slope() helper from features.py handles NaN from window warm-up

## Migration 078 design
- Deactivate `theta_low_vol` (stage_1)
- Deactivate `theta_vol_mult` (stage_2a)
- Insert `theta_contraction` (stage_1, 0.95) as active
- Insert `theta_obv_slope_neg` (stage_3, 0.0) as active
- Downgrade: reverse all four with exact value matching

## LOC risk
- classifier.py: 373 LOC + ~20 new lines = ~393 → safe under 600 limit
- cli.py: 505 LOC + ~15 new lines = ~520 → safe
- cli_states.py: 317 LOC + ~30 new lines = ~347 → safe

## Edge cases
- `atr_14_252d_avg` will be NaN for first 252+14=266 rows per stock → NaN guard returns False for Stage 1 (stock stays uncategorized until enough history)
- OBV slope: 50-bar warm-up → NaN for first 50 rows per stock → NaN guard for Stage 3 (miss rate acceptable)
- realized_vol_63 may be NULL in DB for some stocks → use 0.5 median rank fallback in within_state_rank
- obv_slope_50d: OBV resets per stock (computed in _compute_features_for_stock, per-group)

## Expected runtime
- Migration: < 1s (row-level DML on 20-row table)
- Feature compute: adds 2 rolling operations per stock → ~10% overhead on classify run
- within_state_rank SQL join: 1 additional JOIN on atlas_stock_metrics_daily → < 1s on indexed table
