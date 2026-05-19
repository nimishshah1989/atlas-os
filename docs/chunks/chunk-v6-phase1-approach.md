# Chunk: v6 Phase 1 — Foundation (Tasks 1.1–1.5)

## Data scale
- `atlas_universe_stocks`: ~500 rows (Nifty 500)
- `atlas_stock_metrics_daily`: ~1M+ rows (500 stocks × 2000+ days)
- Compute is SQL (ADV filter) + NumPy vectorized (signals) — appropriate for scale

## Chosen approach
- Task 1.1: SQL CTE with PERCENTILE_CONT for median ADV, Python dataclass wrappers
- Tasks 1.2–1.5: Pure NumPy/pandas vectorized signal math — no DB required
- All signal modules are stateless pure functions; DB fixture only needed for universe.py

## Wiki patterns checked
- `atlas/trading/data_loader.py` — source for compute_natr_14, compute_beta_alpha_63d, compute_mom_low_vol (copy, not import)
- `tests/data_prereqs/v6/conftest.py` — tmp_db_session fixture pattern

## Existing code being reused
- `tmp_db_session` fixture from `tests/data_prereqs/v6/conftest.py` — copied to `tests/trading/v6/conftest.py`
- Signal math copied verbatim from `atlas/trading/data_loader.py` lines 132–188

## Edge cases
- NULLs: SQL COALESCE, Python float() guard on median_adv_cr
- ADV window: ~40 calendar days to get 20 trading days
- Zero close price: guarded with np.where(close > 0, ..., 0.0)
- Zero benchmark variance: guarded with np.abs(var_63) > 1e-12
- FIP smoothness: min_periods=window//2 to avoid all-NaN at start

## Expected runtime
- universe.apply(): <100ms on 500 stocks, 40 days of data
- Signal functions: vectorized NumPy, <10ms per function on 500×252 panel

## Status: approach complete, proceeding to implementation
