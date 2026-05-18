# Chunk T2.2 Approach: atlas-lab states tune CLI

## Data scale check
- atlas_stock_state_daily: classified rows (instrument_id x date). Estimated ~500 instruments x ~500 dates = ~250K rows for a typical 2-year window. Within 100K–1M range → SQL aggregation.
- atlas_stock_metrics_daily: same key space. Factor reads use WHERE date BETWEEN :s AND :e.
- de_equity_ohlcv: ~2M+ rows (partitioned by year). load_price_matrix uses date WHERE clause.

## Chosen approach
- Load factor panels via targeted SQL with date range predicates (not SELECT *).
- Load price matrix ONCE via existing `load_price_matrix` (date range bounded). Reuse across all horizons.
- `compute_forward_returns` called ONCE with all unique horizons; sliced per threshold.
- Three catalog entries execute (theta_rs, theta_vol_mult, theta_distribution). breakout_ratio raises NotImplementedError → logged and skipped.

## Wiki patterns checked
- [SQL Window Computation] — factor values already precomputed in atlas_stock_state_daily (rs_rank_12m, volume_ratio_50d, distribution_days). No recompute needed in Python.
- [SQLAlchemy Dialect Prefix in psycopg2/psql] — strip `postgresql+psycopg2://` before passing to create_engine for synchronous use.
- [Decimal in JSONB Persist] — `per_candidate_ic` dict contains floats (_safe_float already applied in threshold_optimizer). No extra sanitization needed for JSON output.

## Existing code being reused
- `atlas.intelligence.validation.forward_returns.{load_price_matrix, compute_forward_returns}` — already used in _discover_cmd.
- `atlas.intelligence.states.threshold_optimizer.{tune_single_threshold, apply_tuned_threshold}` — the entire optimizer; cli is just the orchestrator.
- DB URL stripping pattern from existing `_states_classify_cmd` and `_discover_cmd`.

## LOC estimate
- cli_states.py: 213 + ~150 = ~363 (under 400 limit, no split needed).
- cli.py: +8 lines for subparser (under 600 limit easily).
- tests: +55 lines integration test (under 800 limit).

## Edge cases handled
- Empty factor panel → skip that threshold, log warning, record status="no_data" in summary.
- breakout_ratio builder → NotImplementedError → log warning, record status="skipped".
- price matrix empty → return 1 early.
- dry_run=True → `apply_tuned_threshold` call is skipped entirely.
- `--as-of` defaults to `--end` when not provided.
- `fwd[f"return_{N}d"]` is the correct accessor for the MultiIndex DataFrame produced by compute_forward_returns.

## Expected runtime on t3.large
- Price matrix for 2-month window (~500 instruments, ~40 trading days) ≈ 20K rows wide pivot: <5s.
- 3 catalog entries × 7 candidates each = 21 IC sweeps. Each sweep is a cross-sectional correlation per date: <2s each. Total ≈ 1 min.
