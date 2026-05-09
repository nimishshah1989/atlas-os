# M7 Task 5 — custom/portfolio.py Approach

## Data Scale
- `atlas.strategy_fm_custom_portfolios`: new table, starts at 0 rows; each create_custom_portfolio() adds 1
- `atlas.strategy_backtest_results`: grows at 1 row per backtest; bounded, no scale concern
- No large table loads — individual row inserts and single-row reads only

## Chosen Approach
- `create_custom_portfolio()` = validate + DB INSERT (sync) + submit to ProcessPoolExecutor (returns immediately)
- ProcessPoolExecutor (max_workers=1): backtest is CPU-bound (vectorbt / NumPy); process bypasses GIL
- `_save_portfolio_record()`: uses `CAST(:instruments AS jsonb)` not `::jsonb` — avoids SQLAlchemy param-cast collision bug (wiki: 4x sightings)
- `run_custom_portfolio_backtest()` is public for testability / manual runs
- `_mark_backtest_failed()` touches updated_at only — no sentinel row; polling endpoint detects failure by updated_at advancing without backtest_id being set

## Wiki Patterns Checked
- **SQLAlchemy Param-Cast Collision** — `::jsonb` near `:instruments` would collide; using `CAST(:instruments AS jsonb)` instead
- **Decimal in JSONB Persist** — weight_pct is float (intentional: ratio not monetary); no Decimal concern here
- **Module-Level Side Effect** — `atlas.db` imported lazily inside `_run_backtest_subprocess()` to avoid circular import at module load

## Existing Code Reused
- `open_compute_session` from `atlas/compute/_session.py`
- `validate_custom_portfolio` + `InstrumentWeight` from `atlas/simulation/custom/builder.py`
- `run_backtest` from `atlas/simulation/backtest/engine.py`
- `write_backtest_result` from `atlas/simulation/backtest/report.py`
- `build_stock_etf_signal_matrix` from `atlas/simulation/core/signal_adapter.py`

## Edge Cases
- Validation failure: ValueError raised before any DB write; _save_portfolio_record never called
- Background process crash: `_run_backtest_subprocess` catches Exception, calls `_mark_backtest_failed` (touches updated_at)
- Portfolio not found in background process: raises ValueError with clear message
- `instruments` column may come back as string (if driver doesn't auto-parse JSONB) or dict — handled with `isinstance(instruments_data, str)` check before `json.loads`

## Expected Runtime (t3.large, 2 vCPU, 8GB)
- `create_custom_portfolio()`: <100ms (1 SQL INSERT + executor submit)
- `run_custom_portfolio_backtest()`: 5-30s depending on instrument count and vectorbt availability
