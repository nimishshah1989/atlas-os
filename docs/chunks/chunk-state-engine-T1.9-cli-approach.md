# Chunk: State Engine Task 1.9 — CLI `atlas-lab states classify`

## Data scale
Nifty 500 stocks: ~500 instruments × 5 trading days = ~2,500 rows per run (target window).
With 400-day lookback for SMA-200 warmup: up to 500 × 660 days = ~330,000 rows loaded from
`de_equity_ohlcv` + `atlas_stock_metrics_daily`. This is in the 100K–1M range so SQL with
WHERE date range filter is the right call. No full-table scan; `_load_data` already has
`WHERE m.date BETWEEN :s AND :e`. The extended `fetch_start = start - timedelta(days=400)` is
passed as the start for the data load.

After feature computation the `features` DataFrame is filtered back to the target window before
classifying. The classifier's `iterrows()` loop is intentional (state machine requires
sequential processing — no vectorized alternative for the prior-state tracking).

## Chosen approach
- Wire directly onto the existing `atlas/trading/cli.py` argparse tree as a nested subparser
  (`states` → `classify`). No new file needed; the CLI is well under 400 LOC after the addition.
- `_compute_features_for_stock`: per-stock vectorized pandas (rolling ops) on the full lookback
  window. Called once per instrument_id group; returns feature DataFrame.
- Cross-sectional `rs_rank_12m`: computed at the panel level (groupby date, rank pct=True) after
  all per-stock feature DataFrames are concatenated. This is correct: the classifier takes the
  scalar percentile, not the raw 12m return.
- `_states_classify_cmd`: loads data via `_load_data(fetch_start, end, universe)`, computes
  features, filters to `[start, end]` window, calls `classify_state_panel`, adds placeholder
  columns, persists.
- Volume column: `_load_data` for `stocks_nifty500` joins `de_equity_ohlcv` but does not
  SELECT `volume`. The feature helper needs it. Solution: add `p.volume` to the existing SQL
  query in `_load_data` for the stocks branch only — this is an in-place surgical extension
  of the existing helper, not a new function.

## Wiki patterns checked
- No matching wiki article for CLI wiring. Existing `_backtest_cmd` / `_discover_cmd` patterns
  are the reference.
- `iterrows` on the panel: the classifier intentionally uses it for sequential state-machine
  tracking. Row count is bounded by 500 stocks × 5 days = 2,500 rows in the filtered panel,
  not the 330K lookback rows. Acceptable.

## Existing code reused
- `_load_data(start, end, universe)` — reused as-is but `p.volume` added to stocks SELECT
- `atlas.intelligence.states.classifier.classify_state_panel` — called directly
- `atlas.intelligence.states.persistence.persist_state_panel` — called directly
- `atlas.intelligence.states.thresholds.load_active_thresholds` — called directly
- `atlas.intelligence.states.features.{sma, slope, atr_14, distribution_days_25d, up_down_volume_ratio_50d}` — called in `_compute_features_for_stock`

## Edge cases
- `_load_data` returns empty metrics → log error + return 1
- After filtering to `[start, end]` window, `features` is empty → log error + return 1
- Per-stock groups with < 200 rows (new listings): rolling windows return NaN; classifier
  handles NaN via `_is_nan` guards → state defaults to "stage_1"
- Volume NULL rows in de_equity_ohlcv: COALESCE not needed — volume is used only in rolling
  ratios; NaN propagates naturally into NaN features, classifier handles them
- `low_252_age_days`: for stocks with no 252d low (all new), the series is all-NaN until the
  rolling_min fills; `_compute_features_for_stock` fills NaN last_low_idx with 0, so
  `low_252_age_days` defaults to 0 (valid: new stock, no known low age)

## Expected runtime on t3.large
- Data load (330K rows over SQL): ~5–10s
- Feature computation (500 stocks × vectorized rolling): ~15s
- Classification (2,500 rows × iterrows state machine): < 1s
- Persist (2,500 upserts in batch): ~3s
- Total: ~25–30s for a 1-week window

## Files modified
1. MODIFY: `atlas/trading/cli.py` — add `states` subparser + `_compute_features_for_stock` +
   `_states_classify_cmd` + `p.volume` in `_load_data` stocks SQL
2. CREATE: `tests/cli/test_states_classify.py` — smoke test (integration-gated)
