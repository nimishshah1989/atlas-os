# Atlas v6 — Canonical Backend Inventory (LOCKED)

**Date:** 2026-05-26
**Status:** This is the authoritative list of tables the v6 product depends on. Anything NOT in this document is either pre-v6 archive, drop candidate, or unrelated workstream.
**Verified against:** Live Supabase atlas-os project (`nanvgbhootvvthjujkvs`) on 2026-05-26 via MCP.

---

## Schema namespacing

| Schema | Owner | Purpose |
|---|---|---|
| `atlas.*` | Atlas engine | All v6 + legacy compute output |
| `public.*` (de_* tables) | JIP data engine | Raw market data (OHLCV, NAVs, indices, corporate actions) |
| `us_atlas.*` | Atlas US workstream | S&P 500 universe + state machinery (parallel) |
| `auth.*` | Supabase | User auth |

---

## Core v6 surface (the 30-table contract)

### Universes + master data (8 tables)

| Table | Rows | Purpose |
|---|---|---|
| `atlas_universe_stocks` | 750 | M1 universe with symbol/sector/tier/in_nifty_50/100/500 flags |
| `atlas_universe_etfs` | 126 | ETF universe with ticker/category/linked_sector |
| `atlas_universe_funds` | 592 | MF universe with mstar_id/category/AMC/aum_cr |
| `atlas_universe_indices` | 75 | Atlas indices universe (linked to de_index_master) |
| `atlas_sector_master` | 31 | Sector definitions + primary NSE index + rollup parents |
| `atlas_benchmark_master` | 0 | Benchmark registry (config) |
| `atlas_fund_category_benchmark_map` | 0 | Fund category → benchmark mapping |
| `atlas_thresholds` | 87 | Global thresholds config (regime cutoffs, friction params, etc.) |

### v6 cell + signal infrastructure (7 tables)

| Table | Rows | Purpose |
|---|---|---|
| `atlas_cell_definitions` | 21 | Per-cell rule_dsl, IC, friction_adjusted_excess, confidence_by_regime (24-cell methodology — 3 missing per audit) |
| `atlas_cell_rule_candidates` | 89 | Per-cell rule candidates with archetype, IC, BH-FDR q |
| `atlas_signal_calls` | 363 | Active signal calls (INACTIVE→ACTIVE cell triggers) |
| `atlas_etf_signal_calls` | 9 | ETF cell triggers (sub-category aware) |
| `atlas_friction_params` | 12 | 3 tiers × 4 friction components (bid-ask, impact, brokerage, slippage) |
| `atlas_brief_cache` | 0 | TTL-cached LLM briefs per signal_call (fills on first request) |
| `atlas_ledger` | 0 | Realized excess after signal_call exits (fills as tenures expire) |

### v6 daily snapshot tables (4 tables — all 2026-05-22 snapshot)

| Table | Rows | Purpose |
|---|---|---|
| `atlas_scorecard_daily` | 747 | Per-iid 5-family R/A/G states + features JSONB (100% populated) |
| `atlas_conviction_daily` | 2,988 | 747 × 4 tenures: verdict (POS/NEU/NEG) + ic + friction_adjusted_excess + eli5 |
| `atlas_etf_scorecard` | 34 (leaders only — EXPAND to 126 in Phase C1.c) | 6 score components per ETF + composite |
| `atlas_fund_scorecard` | 587 | 4 score components per fund + composite + top_holdings JSONB (99.7% populated) |

### v6 paper portfolio + briefs (3 tables — RLS protected)

| Table | Rows | Purpose |
|---|---|---|
| `atlas_paper_portfolio` | 0 | User paper positions (RLS isolates by user_id from JWT) |
| `atlas_user_lots` | 0 | Real-lot tracking (deferred post-v6.0) |
| `atlas_mf_recommendation_daily` | 0 (BACKFILL in Phase C1.b) | Per-fund recommendation (BUY/HOLD/SWITCH/AVOID) + peer_quartile + consistency_months |

### Time-series tables (the 10-year backbone)

| Table | Rows | Min Date | Max Date | Purpose |
|---|---|---|---|---|
| `atlas_market_regime_daily` (v5) | 2,609 | 2016-04-07 | 2026-05-22 | 35 cols: regime_state + deployment_multiplier + breadth + AD + McClellan + VIX + 52w highs/lows |
| `atlas_regime_daily` (v6) | 0 | — | — | v6 regime classifier output (smallcap_rs_z + dispersion etc.) — currently EMPTY; v5 hybrid pattern used |
| `atlas_macro_daily` | 2,711 | 2016-01-01 | 2026-05-19 | USDINR + DXY populated; india_10y/risk_free/fii_flow EMPTY (Phase C2 ingest) |
| `atlas_macro_features_daily` (v6) | 0 | — | — | v6 macro overlay — designed but no writer; not used by v6.0 pages |
| `atlas_stock_metrics_daily` | 1,392,776 | 2016-04-07 | 2026-05-22 | Per-iid: ret_*, rs_*, EMAs, vol_63, drawdowns, gates |
| `atlas_stock_states_daily` | 1,392,776 | 2016-04-07 | 2026-05-22 | Per-iid: rs_state, momentum_state, risk_state, volume_state, gates, tier |
| `atlas_etf_metrics_daily` | 280,077 | 2016-04-07 | 2026-05-25 | Per-ETF returns + RS |
| `atlas_etf_states_daily` | 280,077 | — | 2026-05-22 | Per-ETF states |
| `atlas_index_metrics_daily` | 264,203 | 2016-04-07 | 2026-05-22 | Atlas indices universe metrics |
| `atlas_sector_metrics_daily` | 74,752 | 2016-04-07 | 2026-05-22 | 31 sectors × ~2500 days; bottomup + topdown |
| `atlas_sector_states_daily` | 74,752 | 2016-04-07 | 2026-05-22 | 31 sectors RAG states |
| `atlas_fund_metrics_daily` | 1,049,825 | 2014-04-01 | 2026-05-20 | 12 yrs MF metrics |
| `atlas_fund_states_daily` | 979,635 | — | — | MF state machinery |
| `atlas_factor_returns_daily` | 2,571 | 2016-04-08 | 2026-05-18 | Factor returns (consolidation worktree) |

### Closed-loop methodology engine (8 tables — DO NOT TOUCH)

These are the LIVE production tables that the IC / weight / drift system writes to nightly. The pre-v6 SP01-SP10 work shipped to these.

| Table | Rows | Purpose |
|---|---|---|
| `atlas_signal_ic` | 8 | Historical IC by signal |
| `atlas_signal_ic_rolling` | 380 | Rolling IC over windows |
| `atlas_signal_weights` | 82 | Composite weights per (date, signal) |
| `atlas_signal_weights_live_perf` | 37 | Live performance of weighted composites |
| `atlas_weight_proposals` | 40 | Bayesian-smoothed weight candidates (SP04 Stage 4a) |
| `atlas_stock_hit_rate_daily` | 1,830 | Per-stock hit rate tracking |
| `atlas_stock_conviction_daily` | 5,635 | Conviction score [0,1] + confidence_label + backing_ic + tier — LIFTED for v6 composite |
| `atlas_tier_membership_daily` | 8,000 | Per-iid daily tier membership |

### CTS (Cell Timing Signal — SP09) live tables (4 tables — DO NOT TOUCH)

| Table | Rows | Purpose |
|---|---|---|
| `atlas_cts_signals_daily` | 6,725 | CTS signal events |
| `atlas_cts_sector_pivot_daily` | 270 | Sector-level CTS pivots |
| `atlas_cts_timing_ic` | 67 | CTS timing IC |
| `atlas_cts_hit_rates` | 40 | CTS hit rate tracking |

### Audit + governance (5 tables)

| Table | Rows | Purpose |
|---|---|---|
| `atlas_pipeline_runs` | 111 | Pipeline run audit log |
| `atlas_validator_runs` | 39 | Validator agent runs |
| `atlas_validator_findings` | 2,248 | Validator findings per run |
| `atlas_validator_results` | 27 | Validator results |
| `atlas_run_log` | 25 | Run log |
| `atlas_health_daily` | 270 | Daily health metrics |

### v6 engine governance (4 tables — EMPTY, awaiting v6 writer)

| Table | Rows | Purpose |
|---|---|---|
| `atlas_cell_walkforward_runs` | 0 | Per-(cell, OOS window) IC + TP |
| `atlas_drift_event_log` | 0 | Drift detector event log (G5 audit trail) |
| `atlas_provenance_log` | 0 | Per-run provenance (input dataset SHA, code commit, universe def) |
| `atlas_mf_switch_rules` | 14 | Seeded SWITCH selection rules per fund category |

### Strategy / trading / SDE tables (workstreams parallel to v6; LEAVE ALONE)

| Table | Rows | Purpose | Owner |
|---|---|---|---|
| `strategy_configs` | 15 | Strategy configurations | Strategy Lab |
| `strategy_*` (paper portfolios, trades, performance, backtest, optimization) | 0 each | Strategy Lab paper trading | Strategy Lab |
| `atlas_strategy_*` (history, recommendations, validation, leaderboard, insights, evolution) | various | Strategy Lab outputs | Strategy Lab |
| `atlas_decision_policy` + `_history` | 12 + 2 | Decision policy config | Active product thread |
| `atlas_portfolio_config` + `_membership_daily` | 0 each | Custom portfolio config | Active |
| `atlas_stock_decisions_daily` + `etf_decisions_daily` + `fund_decisions_daily` | 5,392 + 188 + 631,289 | Daily decision history | Active |
| `atlas_fund_lens_monthly` | 3,506 | Monthly fund lens analytics | Active |
| `atlas_fund_holdings_changes` + `fund_decision_scores` | 98,163 + 3,507 | MF holdings tracking | Active |
| `atlas_sector_state_v2` + `fund_state_v2` + `etf_state_v2` | 10,623 + 4,788 + 33,170 | Consolidation worktree v2 states | Consolidation worktree |
| `atlas_state_*` (validation, dwell_statistics, thresholds, action_log) | various | State machinery | Active |
| `atlas_stock_state_daily` | 525,634 | Stock state daily (legacy state engine) | Legacy state engine |
| `atlas_component_validation` | 19 | Per-component validation | Active |
| `atlas_threshold_history` | 37 | Threshold change audit | Active |
| `atlas_strategy_genomes` | 3 | Genetic strategy evolution | Strategy Lab |
| `atlas_strategy_leaderboard` | 3 | Strategy leaderboard | Strategy Lab |
| `atlas_strategy_insights` | 7 | Strategy insights | Strategy Lab |
| `atlas_strategy_recommendations_daily` | 60 | Per-strategy recommendations | Strategy Lab |
| `atlas_strategy_validation` | 33 | Strategy validation results | Strategy Lab |
| `atlas_kite_session` + `atlas_nifty_intraday` + `atlas_stock_metrics_intraday` + `atlas_cts_param_proposals` | various | SP08 intraday | SP08 Live State Engine |
| `atlas_daily_briefs` + `atlas_agent_invocations` | 3 + 1 | SP07 agent runtime | SP07 Hermes |
| `atlas_benchmark_returns_cache` | 24,278 | Benchmark return cache | Compute |

### Quarantine tables (5 tables — sane safety nets, LEAVE ALONE)

`atlas_stock_metrics_quarantine`, `atlas_etf_metrics_quarantine`, `atlas_index_metrics_quarantine`, `atlas_sector_metrics_quarantine`, `atlas_fund_metrics_quarantine`. All 0 rows; safety nets for data anomalies.

### Alembic + system (1 table)

`atlas_alembic_version` (1 row) — current migration head.

---

## Tables flagged as drop candidates (8 tables — wait for morning sign-off)

| Table | Rows | DB comment |
|---|---|---|
| `atlas_governance_daily` | 0 | "ATLAS-REVIEW-UNUSED: no code reference - drop candidate pending review" |
| `atlas_governance_master` | 0 | Same |
| `atlas_index_membership` | 0 | Same |
| `atlas_portfolio_policy` | 1 | Same |
| `atlas_portfolio_proposed_change` | 0 | Same |
| `atlas_v6_exclusions_log` | 0 | Same |
| `atlas_v6_recommendations_daily` | 0 | Same |
| `atlas_v6_strategy_runs` | 16 | Same |

**Not dropped tonight** per overnight constraint. Documented in `docs/v6/drop-candidates.md` for morning sign-off.

---

## Public schema (JIP raw data — read-only from Atlas)

| Table | Rows | Coverage |
|---|---|---|
| `de_equity_ohlcv` | 4,745,195 | 2007 → 2026 (19 yrs; partitioned by year) |
| `de_mf_nav_daily` | 2,221,164 | 2006 → 2026 (20 yrs; partitioned by year) |
| `de_etf_ohlcv` | 450,699 | 2016 → 2026 |
| `de_index_prices` | 266,912 | 2014 → 2026; 8 Nifty indices all live |
| `de_global_prices` | 304,838 | ^GSPC 1789+; URTH 2012+; VWO 2016+; GLD 2016+ |
| `de_corporate_actions` | 11,500 | 2019 → 2026 |
| `de_index_constituents` | 2,910 | Nifty 500 = 500 rows ✅ |
| `de_index_master` | 139 | Curated index metadata |
| `de_etf_master` + `de_etf_holdings` | various | ETF metadata + holdings |
| `de_mf_master` + `de_mf_holdings` + `de_mf_dividends` + `de_mf_lifecycle` | various | MF data |
| `de_market_cap_history` | various | Per-iid market cap history (proxy for `atlas_instruments` which doesn't exist) |
| `de_adjustment_factors_daily` | various | Corp action adjustment factors |
| `de_sector_mapping` | various | Sector mappings |

---

## New tables to be added in Phase B (migration 097)

| Table | Purpose | Page(s) |
|---|---|---|
| `atlas_stock_macro_overlay_map` | Per-(sector, business_mix_tag) → 3 macro series ids | 05a |
| `atlas_etf_te_bands` | Per-category TE acceptable range config | 07 + 07a |
| `atlas_etf_ter_components` | Per-ETF per-quarter TER breakdown (mgmt fee, storage, audit, etc.) | 07a |
| `atlas_etf_physical_disclosure` | Per-ETF per-month physical holdings (commodity ETFs) | 07a |
| `atlas_stock_fundamentals_quarterly` | Per-stock per-quarter P/E, ROE, EPS, margins, growth rates | 05a |
| `de_fno_bhavcopy_daily` | NSE F&O daily bhavcopy (partitioned by year) | 05 + 05a |
| `de_fno_oi_daily` | Per-stock rolled-up OI | 05 + 05a |
| `de_fno_participant_oi_daily` | FII/DII/Pro/Retail OI breakdown | 02 + 05a |
| `atlas_stock_fno_metrics_daily` | Per-stock derived F&O metrics (PCR, IV, basis, OI build-up) | 05a |

---

## New columns to be added in Phase B (migration 097)

| Table | New columns |
|---|---|
| `atlas_cell_definitions` | `display_name VARCHAR(64)`, `explain_text TEXT` |
| `atlas_sector_metrics_daily` | `rs_1w`, `rs_1m`, `rs_6m`, `rs_12m`, `pct_above_ema20`, `pct_above_ema200`, `pct_52wh`, `hhi` (8 cols) |
| `atlas_macro_daily` | `dii_flow`, `us_10y_yield`, `brent_inr`, `cpi_yoy`, `vix_9d` (5 cols; usdinr + dxy + india_10y already exist) |
| `atlas_etf_scorecard` | `premium_bps`, `te_60d`, `adv_20d_inr` (3 cols) |

---

## v6 frontend page → backend MV map

| Page | MV name | Source tables |
|---|---|---|
| 01 Market Regime | `mv_market_regime_landing` | regime_daily, market_regime_daily, signal_calls, cell_definitions, conviction_daily, scorecard_daily, mf_recommendation_daily, etf_signal_calls |
| 02 India Pulse | `mv_india_pulse` | market_regime_daily, macro_daily, sector_metrics_daily, de_index_prices |
| 03 Markets RS | `mv_markets_rs_grid`, `mv_markets_rs_detail_charts` | de_index_prices, de_etf_ohlcv, de_global_prices, atlas_macro_daily.usdinr |
| 04 Sectors | `mv_sector_cards`, `mv_sector_breadth`, `mv_sector_rrg`, `mv_sector_deepdive`, `mv_sector_rotation` | atlas_sector_metrics_daily (post-Phase B col adds), atlas_sector_states_daily, atlas_sector_master |
| 05 Stocks | `mv_stock_list_v6`, `mv_stock_landscape`, `mv_stock_deepdive` | atlas_scorecard_daily, signal_calls, cell_definitions, stock_conviction_daily, universe_stocks, stock_metrics_daily, stock_states_daily, de_market_cap_history |
| 06 Funds | `mv_fund_list_v6`, `mv_fund_deepdive` | atlas_fund_scorecard, universe_funds, fund_metrics_daily, mf_recommendation_daily (post-backfill), mf_switch_rules, de_mf_holdings |
| 07 ETFs | `mv_etf_list_v6`, `mv_etf_deepdive` | atlas_etf_scorecard (post-expand), universe_etfs, etf_metrics_daily, etf_te_bands, etf_ter_components |
| 08 Calls Performance | `mv_calls_performance` | atlas_signal_calls, atlas_ledger (when fills), de_equity_ohlcv (for in-flight T+N) |

**Total v6 MVs: 14.**

---

## Operating principles

1. **Anything NOT in this document is NOT a v6 dependency.** Don't add columns to mystery tables; don't read from undocumented sources.
2. **All time-series MVs must have 5-year minimum backfill, 10-year ideal.** No rolling-window shortcuts.
3. **No direct user-data writes from MV refresh paths.** `atlas_paper_portfolio` + `atlas_user_lots` are RLS-isolated.
4. **Closed-loop engine tables are append-only or write-only-by-cron.** Frontend / MVs READ from them; never write.
5. **All migration changes via Alembic.** No `apply_migration` MCP tool.
6. **Drop candidates wait for explicit sign-off.** Never drop in autonomous mode.

---

**This document is the source of truth for what backend exists. Update inline when migrations land.**
