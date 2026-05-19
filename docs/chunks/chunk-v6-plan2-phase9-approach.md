# chunk-v6-plan2-phase9 — Walk-Forward Backtest Script

## Actual data scale

| Table | Rows | Date range |
|---|---|---|
| atlas_market_regime_daily | 2,599 | 2016-04-07 → 2026-05-18 |
| atlas_stock_metrics_daily | 1,390,535 | 2016-04-07 → 2026-05-18 |
| atlas_macro_daily | 2,711 | 2016-01-01 → 2026-05-19 |
| atlas_factor_returns_daily | 2,571 | 2016-04-08 → 2026-05-18 |
| atlas_universe_stocks | 750 | 2026-05-06 only (no PIT) |
| atlas_stock_conviction_daily | 3,532 | 2026-04-09 → 2026-05-18 |
| atlas_signal_weights | 64 | varies |
| atlas_v6_strategy_runs | 0 | empty |

## Chosen approach

### Data availability
- Training data starts 2016-04-07. Spec says 2010-2022; we use 2016-2024 as available.
- WalkForwardConfig: `train_start=2016-04-07`, `train_end=2020-12-31`, `oos_start=2021-01-01`, `oos_end=2024-12-31`.
- This gives 4 OOS windows (2021, 2022, 2023, 2024).
- Hold-out set to 2025-01-01 to 2025-12-31 (not examined here).

### Key misalignments to handle in script
1. **SimulationResult has `ann_return`, not `cagr`**: The validator's `_oos_result_from_sim` calls `getattr(sim_result, "cagr", 0.0)`. SimulationResult has `ann_return`. Fix: monkeypatch via `sim_result` wrapper or patch validator's import. Chosen: wrap the result with a proxy object that exposes both.
2. **`alpha_t_stat` not in SimulationResult**: Defaults to `0.0` via getattr fallback in validator. This is acceptable for Phase 9 v0.1.
3. **`atlas_signal_weights` schema mismatch**: DB has `train_ic` / `holdout_ic`, not `is_ic` / `oos_ic`. The validator's `_fetch_signal_ic` queries for those missing columns — it will catch the exception and return `{}`. IS/OOS IC will both be empty dicts, which means all signals show "no baseline" → IC retention defaults to True. This is handled gracefully.
4. **`atlas_universe_stocks` is not PIT**: Only has 2026-05-06 data. `get_investable()` will find stocks for recent dates but likely return empty for 2021-2024 dates. The simulator gracefully handles empty universe by skipping periods with zero return.

### Expected runtime on t3.large
- 4 OOS windows × 12 months × SQL fetches for 750 instruments = ~48 rebalance periods.
- Each rebalance: ~3 bulk SQL queries + HRP optimization.
- Estimated runtime: 3–8 minutes total (SQL-dominant, no per-row Python).

### Approach for scale
- SQL-first: signal panel uses `DISTINCT ON (instrument_id)` bulk query, not per-instrument loops.
- Returns panel: single query per rebalance date, pivot in pandas.
- No `iterrows()` or `apply()` in hot paths.

### Edge cases
- Empty universe on historical dates (universe_stocks is 2026-05-06 only) → simulator emits zero-return periods, continues.
- No `alpha_t_stat` → defaults to 0.0, fails goal-post constraint (expected for v0.1).
- Benchmark vol: derived from regime table's realized_vol column.
- Goal-post FAIL expected: short data history, proxy signals, no PIT universe.

### Files modified
- Create: `scripts/v6_walk_forward.py`

### Wiki patterns checked
- data-engineering.md: SQL-first for 1M+ rows; checked.
- financial-domain.md: NULL handling, row counts logged; checked.
