# Chunk: v6 Plan 2 Phase 7 — Orchestrator + Simulator

## Actual data scale
- atlas_stock_metrics_daily: high row count (~10y × 500 stocks × 252d ≈ 1.26M rows); SQL windowing required
- atlas_market_regime_daily: ~2500 rows (one per trading day)
- atlas_macro_daily: 2711 rows
- atlas_factor_returns_daily: 2571 rows
- atlas_etf_metrics_daily: moderate (~50 ETFs × 252d × 10y)
- atlas_v6_strategy_runs: empty at start; grows 1 row per backtest run
- atlas_v6_recommendations_daily: empty at start

## Chosen approach

### simulator.py (~400 LOC)
- Monthly rebalance loop over trading dates from atlas_market_regime_daily
- At each rebalance date: call universe → governance → signals → composite → select → HRP → regime → vol_target → crisis_sleeve → apply orders
- Signal panel built via SQL bulk-fetch for all instruments at once (not per-instrument loop)
- Returns pulled from de_equity_ohlcv via SQL JOIN, aggregated to 1d returns per instrument
- Period returns computed as weighted sum of constituent returns minus slippage cost
- SimulationResult aggregate stats: CAGR, MDD, vol, Sharpe, Calmar, win_rate, n_trades
- DB write: one row to atlas_v6_strategy_runs per simulation run

### lab.py (~250 LOC)
- Thin orchestrator: create session, call simulator.run_simulation(), write to DB
- run_backtest() → delegates to run_simulation()
- live_rebalance() → single-date run, writes to atlas_v6_recommendations_daily
- intramonth_scan() → checks composite vs 0.85 threshold, returns candidate Orders
- evaluate_goal_post() → reads atlas_v6_strategy_runs, evaluates 9 constraints

## Wiki patterns checked
- Idempotent Upsert: used for atlas_v6_strategy_runs (ON CONFLICT DO UPDATE on run_id)
- Computation Boundary: float numpy internally, Decimal at storage boundary
- Per-Day Query Loop (ANTI-PATTERN): avoided — bulk-fetch all dates at once then slice
- SQL Window Computation: returns computed via SQL window over 252d lookback

## Existing code reused
- universe.get_investable() — PIT Nifty 500 + ADV
- governance.apply_exclusions() — batch exclusion check
- composite.compute_composite() + select() — scoring + buffer zones
- portfolio.HrpAllocator.allocate() — HRP weights
- regime.compute_regime() — 5-signal macro score
- risk.vol_targeted_gross() + slippage_bps() + per_name_trend_gate()
- crisis_sleeve.allocate() — TSMOM sleeve

## Schema deviations
- atlas_v6_strategy_runs has is_period/oos_period as TSRANGE — will store as literal ISO range strings, not TSRANGE type, via text() insert; using daterange syntax
- No `benchmark_return` column in strategy_runs — computed in memory; stored separately as context field in the period results only
- atlas_v6_recommendations_daily.confidence_band CHECK is IN ('HIGH', 'MED', 'LOW') — will use 'HIGH'/'MED'/'LOW' to match

## Tests approach
- test_simulator.py: 4 tests, all pure-Python synthetic (no DB needed for most)
  - test_simulator_runs_on_30_instruments_6_months: seeded synthetic universe, mock DB session using monkeypatch of module-level functions
  - test_simulator_respects_holdings_count_target: verify holdings within [20,45] range
  - test_simulator_handles_governance_exclusions: excluded name mid-period → exited
  - test_simulator_persists_to_strategy_runs: DB integration test (skip if no ATLAS_TEST_DB_URL)
- test_lab.py: 3 tests
  - test_run_backtest_returns_simulation_result: monkeypatch run_simulation
  - test_live_rebalance_writes_recommendations_daily: DB integration (skip if no URL)
  - test_evaluate_goal_post_returns_constraint_status: DB integration (skip if no URL)

## Edge cases
- Empty investable universe on a date: skip rebalance, carry prior holdings
- No regime row for date: raise ValueError (per existing regime.py behavior)
- All governance excluded: no holdings → cash allocation
- Holdings count below 20 after exclusions: issue warning, proceed with available names
- NaN returns from missing OHLCV data: log gap count, fill with 0 for period return calc
- First rebalance has no prior holdings: enter_rank_cutoff applies, held_yesterday = {}

## Expected runtime
- 6-month synthetic test (no DB): < 2s
- Full 10-year backtest on EC2 t3.large: estimated 8-15 min (500 stocks × 120 monthly rebalances × SQL round-trips per date)
