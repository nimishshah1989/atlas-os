# Atlas Full Table Audit — 2026-05-28

**Scope:** every base table in `atlas.*` and `public.*` schemas (excludes MVs, partition children, system tables).
**Total user tables:** ~165
**Methodology per table:** MV references (DB introspection) + code references (grep `frontend/src/lib/queries/`, `atlas/`, `scripts/`, `migrations/`) + write activity (pg_stat).

⚠️ **Lesson from yesterday:** `pg_stat n_live_tup=0` is unreliable post-bulk-load. Always do fresh `COUNT(*)` before declaring empty. Also grep `atlas-os-sl/` (sibling repo) — v2 nightly pipeline tables look unused but are written nightly.

---

## CATEGORY A — DEFINITELY KEEP (active v6 / cross-pipeline writes / many code refs)

These have either (a) ≥1 MV reference, (b) write activity in last 7 days, or (c) ≥10 code references. **Do not touch.**

| Table | MV refs | Last touched | Why |
|---|---:|---|---|
| atlas_stock_metrics_daily | 9 | 2026-05-22 | M4 + 9 MVs read it |
| atlas_stock_states_daily | 5 | 2026-05-21 | M4 + frontend |
| atlas_fund_metrics_daily | — | 2026-05-21 | M4 fund pipeline (read by atlas-os-sl) |
| atlas_fund_states_daily | — | 2026-05-21 | M4 fund pipeline |
| atlas_stock_decisions_daily | — | (post-load) | Atlas intelligence |
| atlas_etf_metrics_daily | 2 | 2026-05-27 | ETF pipeline |
| atlas_etf_states_daily | 2 | 2026-05-27 | ETF pipeline |
| atlas_etf_decisions_daily | 2 | (post-load) | ETF pipeline |
| atlas_etf_scorecard | 3 | 2026-05-27 | ETF pipeline + AMFI iNAV |
| atlas_etf_signal_calls | 2 | (post-load) | ETF intelligence |
| atlas_index_metrics_daily | 4 | 2026-05-21 | M3 |
| atlas_sector_metrics_daily | 6 | 2026-05-27 | M3 + all sector MVs |
| atlas_sector_states_daily | 3 | 2026-05-21 | M3 |
| atlas_stock_conviction_daily | 5 | 2026-05-27 | Atlas intelligence |
| atlas_scorecard_daily | 2 | 2026-05-27 | Atlas intelligence |
| atlas_signal_calls | 7 | 2026-05-27 | All cell MVs read |
| atlas_macro_daily | 3 | 2026-05-27 | mv_india_pulse + macro displays |
| atlas_market_regime_daily | 3 | 2026-05-21 | Regime MVs |
| atlas_universe_stocks | 12 | 2026-05-28 | Every stock MV reads |
| atlas_universe_etfs | 2 | 2026-05-28 | ETF pipeline + ISIN backfill |
| atlas_universe_funds | 3 | 2026-05-28 | Fund pipeline |
| atlas_cell_definitions | 5 | 2026-05-26 | 24-cell methodology |
| atlas_thresholds | 0 | 2026-05-13 | 30 code refs (static config) |
| atlas_fund_scorecard | 3 | 2026-05-25 | Fund pipeline |
| atlas_benchmark_master | 0 | (idle) | 14 code refs |
| atlas_data_health | 0 | 2026-05-28 | My health-check writer |
| atlas_macro_features_daily | 3 | (idle) | 3 code refs (macro engine) |
| atlas_cts_signals_daily | 0 | (post-load) | SP09 CTS (8K rows, written by intelligence chain) |
| atlas_cts_hit_rates | 2 | 2026-05-27 | SP09 |
| atlas_validator_findings | 0 | 2026-05-27 | 8 refs + actively written |
| atlas_validator_runs | 0 | 2026-05-27 | Actively written |
| atlas_pipeline_runs | 0 | 2026-05-27 | 11 refs |
| atlas_alembic_version | 0 | 2026-05-21 | Schema version (critical) |
| atlas_symbol_aliases | 0 | (new today) | NSE rename mappings (TATAMOTORS→TMPV etc.) |
| atlas_signal_calls + atlas_signal_weights* + atlas_weight_proposals* + atlas_weight_revert_log | 0-7 | 2026-05-25-27 | SP04 weight-tuning chain |
| **All v2 atlas tables** (`*_state_v2`, `atlas_conviction_daily`, `atlas_stock_state_daily` singular) | 0 | 2026-05-19-27 | Written by `atlas-os-sl/` (sibling repo) + frontend reads them |
| **All raw `public.de_*` ingest tables** (`de_equity_ohlcv_*`, `de_mf_nav_daily*`, `de_etf_ohlcv`, `de_index_prices`, `de_corporate_actions`, `de_mf_holdings`, `de_etf_holdings`, `de_instrument`, `de_index_constituents`, `de_trading_calendar`, `de_mf_master`, `de_mf_lifecycle`, `de_healing_log`, `de_pipeline_log`, `de_cron_run`, `de_source_files`, `de_adjustment_factors_daily`, `de_etf_master`, `de_global_prices`) | varies | 2026-05-28 | JIP infrastructure |

---

## CATEGORY B — KEEP, LIKELY-USED-BUT-IDLE (code refs exist, no recent writes)

Probably used by a feature that hasn't fired recently, OR is read-only reference data. **Don't touch without first running the dependent feature.**

| Table | Code refs | Notes |
|---|---:|---|
| atlas_signal_ic | 12 | SP04 IC tracking — written by Atlas intelligence (occasional) |
| atlas_signal_weights | 12 | SP04 weight registry |
| atlas_strategy_leaderboard | 12 | Strategy lab leaderboard |
| atlas_strategy_history, atlas_strategy_validation, atlas_strategy_insights, atlas_strategy_evolution_log, atlas_strategy_genomes, atlas_strategy_positions_daily, atlas_strategy_recommendations_daily | 5-8 each | Strategy lab — read by the `/strategies/lab/*` admin routes |
| strategy_backtest_results, strategy_paper_*, strategy_optimization_runs, strategy_fm_custom_portfolios, strategy_overlap_daily, strategy_configs | 3-7 | Strategy lab |
| atlas_regime_daily | 11 | Regime engine cache |
| atlas_sector_master | 11 | Sector taxonomy |
| atlas_pipeline_runs, atlas_validator_runs, atlas_run_log | 6-11 each | Pipeline observability |
| atlas_cell_rule_candidates, atlas_cell_walkforward_runs, atlas_cell_definitions | 5-33 each | SP04 cell rule system |
| atlas_brief_cache, atlas_daily_briefs | 6-8 | Daily brief generator |
| atlas_kite_session | 6 | Kite Connect session (live trading) |
| atlas_provenance_log, atlas_ledger | 8-9 each | Audit trail |
| atlas_threshold_history, atlas_decision_policy, atlas_decision_policy_history | 3-7 each | SP04 policy engine |
| atlas_state_thresholds, atlas_state_action_log, atlas_state_dwell_statistics, atlas_state_validation | 1-7 | State classifier |
| atlas_drift_event_log | 4 | SP04 weight drift detection |
| atlas_mf_switch_rules | 5 | MF switch engine |
| atlas_nifty_intraday | 5 | SP10 intraday |
| atlas_paper_portfolio, atlas_portfolio_config, atlas_portfolio_policy, atlas_portfolio_proposed_change, atlas_user_lots | 1-7 each | Portfolio system (/portfolios/* pages) |
| atlas_universe_indices, atlas_universe_membership_daily | 3-7 each | Universe management |
| atlas_friction_params | 3 | Cell methodology friction |
| atlas_cts_param_proposals, atlas_cts_timing_ic | 2 | SP09 internal |
| atlas_fund_holdings_changes | 5 | MF holdings analysis |
| atlas_fund_lens_monthly, atlas_fund_decision_scores, atlas_mf_recommendation_daily | written 2026-05-15-26 | Pre-v6 fund pipeline still alive |
| atlas_stock_hit_rate_daily | 3 | SP04 hit-rate engine |
| atlas_agent_invocations | 3 | SP07 Hermes agent log |
| atlas_etf_te_bands | 1 | ETF TE reference bands |
| atlas_stock_macro_overlay_map | 1 | Macro overlay mapping |
| atlas_signal_ic_rolling, atlas_signal_weights_live_perf, atlas_weight_proposals, atlas_weight_revert_log | 4-5 | SP04 Stage 4 weight tuning |
| atlas_macro_recommendation_daily | 3 | Macro engine |
| atlas_validation_results, atlas_validator_results | 2-5 | Validator output |
| atlas_factor_returns_daily | 0 ⚠ | **0 refs but 2571 writes** — possibly written by atlas-os-sl. Verify before drop. |
| atlas_health_daily | 4 | Pre-existing health rollup (predates atlas_data_health which I added today) |

---

## CATEGORY C — REVIEW (low refs + idle, possibly safe to drop after verification)

These have ≤2 code refs AND no writes in the last 7 days. Worth a closer look but not auto-safe.

| Table | Code refs | Write activity | Notes |
|---|---:|---:|---|
| atlas_fund_category_benchmark_map | 4 | 0 | Reference map; likely dormant config |
| atlas_component_validation | 4 | 19 | Validator output (small) |
| atlas_cts_sector_pivot_daily | 4 | 420 | SP09 sector pivot (5 MB) |
| atlas_v6_strategy_runs | 0 | 26 | v6 strategy lab run log |
| atlas_strategy_genomes | 8 | 26 | Strategy lab |
| atlas_v6_recommendations_daily | 0 | 0 | Empty + never written |
| atlas_v6_exclusions_log | 0 | 0 | Empty + never written |
| atlas_governance_master, atlas_governance_daily | 0 | 0 | Empty governance tables |
| atlas_index_membership | 0 | 0 | Empty |
| atlas_*_quarantine (4 tables: stock/etf/sector/index/fund) | 2 each | 0 | Quarantine buckets — empty means no bad data seen |
| atlas_macro_features_daily | 3 | 0 | Macro features engine — empty |

---

## CATEGORY D — DROP CANDIDATES (likely Optuna ML library scaffolding, 0 refs, 0 recent writes)

Python's **Optuna** library (used for hyperparameter optimization) auto-creates these tables. If we're not running Optuna studies, they're 100% scaffolding.

| Table | Rows | Last touched | Note |
|---|---:|---|---|
| `public.trials` | 1,494 | 2026-05-16 | Optuna study trials |
| `public.trial_params` | 35,442 | 2026-05-16 | Trial hyperparams |
| `public.trial_values` | 391 | 2026-05-16 | Trial output values |
| `public.trial_intermediate_values` | 0 | (never) | Empty Optuna |
| `public.trial_user_attributes` | 110 | 2026-05-16 | Optuna user metadata |
| `public.trial_system_attributes` | 0 | (never) | Empty |
| `public.trial_heartbeats` | 0 | (never) | Empty |
| `public.studies` | 19 | (never analyzed) | Optuna studies |
| `public.study_directions` | 1 | (never) | Optuna direction (max/min) |
| `public.study_system_attributes` | 0 | (never) | Empty |
| `public.study_user_attributes` | 0 | (never) | Empty |

⚠️ **Before dropping:** confirm no scheduled Optuna study runs. The most recent writes were 2026-05-16 — likely from SP04 weight-candidate generation experiment. If that experiment is shelved, safe to drop. If you're planning to re-run weight optimization, keep.

---

## CATEGORY E — TINY UNUSED public.de_* (≤24 KB, never written, 0 refs)

JIP scaffolding that never received data. Safe candidates if JIP doesn't plan to use them.

| Table | Size | Why dropping is safe |
|---|---|---|
| `public.de_data_anomalies` | 48 KB | Empty + 0 code refs |
| `public.de_global_instrument_master` | 56 KB | 0 rows, 0 refs |
| `public.de_global_technical_daily` | 16 KB | 0 rows, 0 refs |
| `public.de_goldilocks_market_view` | 16 KB | 0 rows, 0 refs (deprecated namespace) |
| `public.de_goldilocks_sector_view` | 16 KB | 0 rows, 0 refs |
| `public.de_goldilocks_stock_ideas` | 16 KB | 0 rows, 0 refs |
| `public.de_index_master` | 56 KB | 0 rows, 0 refs |
| `public.de_migration_errors`, `public.de_migration_log` | 24+16 KB | Empty migration tracking (replaced by alembic_version) |
| `public.de_recompute_queue` | 48 KB | 0 rows, 0 refs |
| `public.de_request_log` | 16 KB | 0 rows, 0 refs |
| `public.de_sector_mapping` | 32 KB | 0 rows, 0 refs (replaced by atlas_sector_master) |
| `public.de_symbol_history` | 24 KB | 0 rows — would be a USEFUL feature if populated (would replace my atlas_symbol_aliases) |
| `public.de_system_flags` | 32 KB | 0 rows, 0 refs |
| `public.de_mf_dividends` | 24 KB | 0 rows, 0 refs |
| `public.de_contributors` | 40 KB | 0 rows, 0 refs |
| `public.tv_alert_registry`, `public.tv_signal_reports` | 32+128 KB | TradingView alert provisioning — abandoned per [[v6-build-plan]] |
| `public.atlas_signal_alerts` | 80 KB | Misplaced in `public.` schema; 0 rows |
| `public.version_info` | 24 KB | 0 refs |

**Estimated drop savings: ~700 KB**. Tiny but cleans the schema list.

---

## Recommendation order

1. **Phase A (lowest risk, ~700 KB):** Category E — `public.de_*` empty scaffolding + `public.tv_*` + misplaced `public.atlas_signal_alerts`. Drop after one fresh-COUNT verification.

2. **Phase B (low risk, recovers MB):** Category D Optuna tables — **only if you confirm SP04 weight-tuning is not going to re-run**.

3. **Phase C (medium risk):** Category C empties (`atlas_v6_exclusions_log`, `atlas_v6_recommendations_daily`, `atlas_governance_*`, `atlas_index_membership`) — verify with grep one more time.

4. **Phase D / never:** Categories A + B — these are part of the active or idle-but-real Atlas surface. Leave them.

---

## Estimated impact

| Phase | Drop count | Size recovered | Risk |
|---|---:|---|---|
| A — `public.de_*` + `tv_*` + misplaced | 16 | ~700 KB | Very low (all 0-row + 0 refs) |
| B — Optuna scaffolding | 11 | ~9 MB | Low IF SP04 tuning is sunset |
| C — empty atlas_* | 6 | ~120 KB | Low (need final grep) |
| **Total potential** | **33 tables** | **~10 MB** | — |

**The bigger truth: we're not wasting much disk on dead tables.** The ~2.4 GB on stock_metrics_daily + 820 MB on stock_states_daily are real, active data. Cleanup here is for schema hygiene + reducing the "what does this do?" surface, not for storage recovery.
