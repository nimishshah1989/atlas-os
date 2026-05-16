# Chunk T13 Approach: Nightly Incubator Orchestrator

## Task
Implement `atlas/trading/incubator.py` — the top-level nightly orchestrator that chains all simulation modules.

## Data Scale
- `atlas_stock_metrics_daily`: estimated 2M+ rows (backfill to 2014). 12-year window = ~3000 trading days × ~500 stocks.
- `atlas_market_regime_daily`: ~3000 rows (one per trading day).
- Both are loaded once at run start with a date-bounded WHERE clause. Python does no GROUP BY or JOIN.

## Approach

### Why SQL for data load, Python for orchestration
- Metrics and regime data are loaded once via date-bounded SQL (not `SELECT *`) — conforms to the data-engineering constraint (WHERE clause on date range).
- All heavy computation (Optuna, DEAP, vectorbt) runs in Python. SQL is used only for data I/O.
- The orchestrator itself is pure Python glue — no pandas aggregations, no iterrows.

### Key design decisions
1. **`run_nightly()` returns a summary dict** — testable, loggable, scriptable.
2. **`_load_active_config()` falls back to `PortfolioConfig()`** — safe default for fresh environments.
3. **`sim_fn` closure** in the tournament loop intentionally captures `metrics_df`, `regime_df`, `config` from outer scope — avoids passing them as extra args through `TournamentEvaluator.evaluate()`.
4. **JSONB persist**: `importance` dict values are sanitized to `float` before `json.dumps()` — avoids Decimal-in-JSONB failure (seen 5x per wiki bug-patterns/decimal-in-jsonb-persist.md). The spec already includes `{k: float(v) for k, v in importance.items()}`.
5. **No bare `except:`** — individual modules handle their own errors; the orchestrator lets exceptions propagate so the cron wrapper can log them.
6. **`__main__` guard** — no module-level side effects (wiki: module-level-side-effect bug pattern).

## Wiki patterns checked
- `pipeline-abc-orchestration` — incubator is an orchestrator; follows the "call sub.execute() once" pattern.
- `decimal-in-jsonb-persist` — importance dict sanitized to float at persist boundary.

## Existing code reused
- `atlas.trading.optimizer.OptunaStudy` — `run_trials()` + `get_parameter_importance()`
- `atlas.trading.evolver.Evolver` — `select_survivors()`, `crossover()`, `mutate()`
- `atlas.trading.tournament.TournamentEvaluator` + `promote_to_leaderboard()`
- `atlas.trading.insight.generate_insights()`
- `atlas.trading.simulator.simulate_genome()` + `SimResult`
- `atlas.trading.config.PortfolioConfig`

## Edge cases handled
- Empty metrics_df: early return with `{"status": "aborted"}`.
- No walk-forward windows: early return.
- `len(survivors) < 2`: skip crossover, offspring list is empty.
- `bullets` empty (Groq unavailable): INSERT is skipped entirely.
- `db_url` absent: falls back to in-memory Optuna study.

## Expected runtime on t3.large
- 200 Optuna trials × ~1s per simulate_genome call = ~3-4 minutes.
- Tournament (10 genomes × 5 sim calls each) = ~50s.
- Total wall time: ~5-6 minutes. Fits within a 15-minute nightly cron window.

## Files
- Creates: `atlas/trading/incubator.py`
- Touches: nothing else
