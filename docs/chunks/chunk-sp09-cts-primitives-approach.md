# SP09 CTS Primitives — Approach

## Actual data scale
- Local DB not accessible from Mac (psycopg2 socket issue). EC2 required for prod data.
- CTS primitives are pure in-memory pandas compute functions; they take a DataFrame of OHLCV bars as input, not a DB table directly.
- Typical universe for NSE: ~500 instruments x ~252 bars = ~126K rows per rolling window. Fully vectorised groupby+transform handles this in <1s on t3.large.

## Chosen approach
Pure pandas vectorised via `groupby(group_col, observed=True).transform(...)`. Same pattern as `atlas/compute/primitives.py` which has been production-validated. No row loops.

- `add_trp`: column arithmetic on the full DataFrame, then `groupby.transform(rolling.mean)` for avg_trp. Zero Python loops.
- `add_sma_slope`: `groupby.transform(rolling.mean)` for SMA, then `groupby.transform(diff/slope_days)` for slope.
- `add_volume_ratio`: same rolling-mean pattern.
- `add_atr14`: uses `pandas_ta.atr` per group via `groupby.apply`, then `groupby.transform(rolling.apply(polyfit))` for slope.

SQL windowing was considered (pattern: SQL Window Computation) but rejected — CTS primitives are called from a nightly Python pipeline that already has a DataFrame loaded; pushing back to SQL would require a round-trip with no gain at this scale.

## Wiki patterns checked
- [Computation Boundary Pattern](patterns/computation-boundary-pattern.md) — float internally for numpy ops, no premature Decimal conversion needed in primitives (primitives return DataFrames, not stored values).
- [SQL Window Computation](patterns/sql-window-computation.md) — considered, rejected: data already in-memory from intraday fetch.

## Existing code being reused
- `atlas/compute/primitives.py` — `add_atr14` and the `groupby.apply(_atr)` pattern are directly mirrored from the existing `add_atr` function in that file.
- `pandas_ta` already installed and used in `atlas/compute/primitives.py` and `atlas/compute/breadth.py`.

## Edge cases
- `avg_trp = 0`: guarded with `.replace(0, pd.NA)` so `trp_ratio` is NaN not inf.
- First `avg_window - 1` rows: `min_periods=avg_window` ensures NaN rather than partial mean.
- ATR slope: polyfit with `raw=True` skips NaN guard; handled via `np.isnan(arr).any()` check in the inner closure.
- Multi-instrument DataFrames: all functions accept the whole universe and apply groupby, not single-instrument only.
- Empty DataFrame: all pandas operations gracefully return empty columns.

## Expected runtime on t3.large
- 500 instruments x 252 bars = 126K rows: <100ms per function.
- `add_atr14` with polyfit `apply` is the slowest — estimated <1s for 500 groups.

## Files
- `atlas/compute/cts/__init__.py`
- `atlas/compute/cts/primitives.py`
- `tests/unit/cts/__init__.py`
- `tests/unit/cts/test_primitives.py`
