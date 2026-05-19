# Chunk: v6 Simulator — Fix B: Daily NAV from Daily Returns

## Problem
`run_simulation()` appends one point to `equity_curve` per monthly period:
```python
equity_curve.append(equity_curve[-1] * (1.0 + period.book_return))
```
`_compute_aggregate_stats` then calls `drawdowns.min()` on that monthly series.
With 12 points/year, intra-month troughs are invisible → 2022 MDD reported as
-10.7% when actual Nifty 500 intraday MDD was ~17%.

## Data scale
- `atlas_stock_metrics_daily` contains `ret_1d` pre-computed for all instruments.
  Estimated scale: ~500 stocks × ~1500 days = ~750K rows (within 1K-100K per
  instrument per year — vectorized pandas is fine).
- Each holding period spans ~20 trading days; a 3-year simulation has ~36 periods
  with ~20 instruments each → bulk fetch of ~36 × 20 instruments = ~720 inst-periods,
  but we batch per period (not globally), so peak in-memory is ~20 instruments × 252
  rows = 5040 rows per fetch — well within RAM.

## Approach

### What changes
1. Add `_fetch_daily_portfolio_returns(session, book_weights, start, end) -> pd.Series`
   - SQL: fetch `ret_1d` for all holdings between period start and end from
     `atlas_stock_metrics_daily`. Fall back to `de_equity_ohlcv` if needed.
   - Returns a daily pd.Series of portfolio returns (weighted sum).
   - Slippage drag applied on the rebalance date only (first day of period).

2. In `run_simulation()`: replace the single monthly equity_curve.append() with
   a bulk extend of daily NAV points. Maintain a running `current_nav` float as
   the last equity_curve value; after each period, extend equity_curve with the
   daily points for that period.

3. `_compute_aggregate_stats()`: unchanged signature. The equity_curve passed in
   is now daily-granularity. MDD, vol, Sharpe computed from the same series.
   Vol changes: was `ret_series.std() * sqrt(12)` (monthly), now
   `daily_ret_series.std() * sqrt(252)` (daily). The `periods` list remains
   monthly for entry/exit and per-period stats — only the NAV series changes.

4. Add `daily_returns_series: list[float]` alongside `equity_curve` in the loop.
   Persist daily returns for vol computation in aggregate stats. Pass both to
   `_compute_aggregate_stats`.

### What does NOT change
- Monthly rebalance loop structure
- Entry/exit logic, HRP, regime, sleeve — all unchanged
- `PeriodResult.book_return` remains the compound return over the period
- DB schema (no migration needed)
- `_persist_strategy_run` — same MDD/vol/calmar, now more accurate

## Edge cases
- Period with no daily data (regime skip → book_return=0.0): emit 20 zero daily returns (approx one trading month), not one zero — keeps NAV flat but maintains daily granularity.
- Instruments exit mid-period: we use `book_weights` from the START of the period (post-rebalance weights are fixed for the month), same as current behavior.
- NULL ret_1d: already filtered in SQL (`ret_1d IS NOT NULL`), missing days treated as 0.0 return with a warning log.
- NaN in weighted sum if no data for any instrument on a day: fillna(0.0) before weighting — same defensive pattern as `_fetch_returns_panel`.

## Source table preference
Try `atlas.atlas_stock_metrics_daily.ret_1d` first (already used for HRP).
`de_equity_ohlcv` fallback not needed for this fix since ret_1d is already
computed and available in the metrics table.

## Vol computation change
Old: `monthly_returns.std() * sqrt(12)` — samples at month-end only, captures
regime-change vol poorly.
New: `daily_returns.std() * sqrt(252)` — standard annualization from daily.
This is strictly more accurate and expected by the strategy gate constraints.

## Expected runtime
~36 period × 1 SQL query each = 36 queries. Each query: ~20 IDs × 20 days =
400 rows. Trivial. Total simulation runtime on t3.large: <30s for a 3-year run.

## Wiki patterns checked
- Computation Boundary (float internally, Decimal at storage edge) — maintained.
- Per-Day Query Loop bug — avoided: one SQL fetch per period (not per day).
- NAV gaps must be logged before filling — applied to daily ret_1d NULLs.
