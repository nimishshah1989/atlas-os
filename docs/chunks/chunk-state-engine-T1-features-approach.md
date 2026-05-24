# Chunk: State Engine T1 — features.py approach

## Data scale
No DB I/O in this chunk. Pure in-memory pandas/numpy functions.
All inputs are Series/DataFrames passed by the caller. No table reads.

## Chosen approach
Pure pandas vectorized functions. No iterrows, no apply on >1K rows.
All rolling computations use pandas `.rolling()` with explicit `min_periods=window`
so pre-warmup rows return NaN rather than partial-window estimates.

## Wiki patterns checked
- `SQL Window Computation`: not applicable — these are in-memory functions
  used by the state classifier before DB writes.
- `PRD Golden Example Testing`: fixtures used as golden examples in conftest.

## Existing code being reused
- Pattern from `atlas/intelligence/conviction/composer.py` for module layout.
- Test fixture style from `tests/intelligence/conviction/conftest.py`.

## 12 functions specified
1. `sma(series, window)` — rolling mean
2. `ema(series, span)` — ewm with min_periods=span
3. `slope(series, window)` — normalized linear-regression slope via polyfit
4. `atr_14(high, low, close)` — Wilder ATR
5. `distribution_days_25d(close, volume)` — rolling count of dd events
6. `percent_off_52w_high(close)` — drawdown from 252d rolling max
7. `percent_off_52w_low(close)` — distance from 252d rolling min
8. `up_down_volume_ratio_50d(close, volume)` — up-vol / down-vol, NaN on no-down-vol
9. `base_depth(close, window=60)` — (high-low)/high in window
10. `base_length(close, threshold=0.15)` — trailing days within band of 60d high
11. `rs_rank_12m(stock_close, universe_returns)` — percentile rank vs universe
12. `breadth_above_ma(universe_closes, ma_window)` — % above rolling SMA

## Edge cases handled
- NaN before warm-up: all rolling calls use `min_periods=window`
- Zero down-day volume: `down_sum.replace(0, np.nan)` prevents inf in up_down_volume_ratio
- Zero high in base_depth: guard via `high_w` being non-zero on valid price series
- VIX / universe empty: rs_rank_12m guards `len(universe_day) < 10`
- Constant price in base_length: `high_60` equals close, `within` is True every day

## Expected runtime on t3.large
Pure pandas on 500-row Series: sub-millisecond per call.
rs_rank_12m loops per date — 500 iterations on 100-stock universe: ~50ms.
Acceptable for nightly batch; not intended for streaming.

## LOC estimates
- features.py: ~160 LOC (well under 600 limit)
- test_features.py: ~120 LOC
