# Atlas Backend Table Census — 2026-05-28

**Purpose:** inventory every table in Supabase atlas-os, categorize KEEP/ARCHIVE/DROP, identify cleanup candidates. Drops require explicit user approval per safety policy — this doc is a proposal, not an execution.

**Snapshot date:** 2026-05-28. Total tables ≈ 160 across `atlas.*` + `public.de_*` schemas.

---

## Active v6 surface — KEEP

These tables are read by the live frontend or write to the nightly chain. Do not touch.

### Raw ingest tables (`public.de_*`)

| Table | Size | Rows | Source | Used by |
|---|---|---|---|---|
| `de_equity_ohlcv` (partitioned y2007-y2026) | ~1.8 GB | 4.75M | NSE bhavcopy via JIP | M3, M4, atlas_compute_adjustments |
| `de_etf_ohlcv` | 110 MB | 450K | NSE bhavcopy | mv_etf_deepdive, ETF pipeline |
| `de_index_prices` | 41 MB | 267K | NSE bhavcopy | M3 sector compute |
| `de_mf_nav_daily` (partitioned) | ~150 MB | 2.2M | AMFI + Morningstar | M4 fund pipeline |
| `de_corporate_actions` | 2.9 MB | (re-ingested daily) | NSE | atlas_compute_adjustments |

### Calculated tables (`atlas.atlas_*`)

| Table | Size | Rows | Written by | Read by |
|---|---|---|---|---|
| `atlas_stock_metrics_daily` | 1869 MB | 1.39M | M4 daily | mv_stock_landscape, mv_stock_deepdive, mv_sector_deepdive |
| `atlas_stock_states_daily` | 820 MB | 1.39M | M4 daily | same |
| `atlas_fund_metrics_daily` | 380 MB | 1.05M | M4 fund pipeline | mv_fund_list_v6, mv_fund_deepdive |
| `atlas_fund_states_daily` | 374 MB | 980K | M4 fund pipeline | same |
| `atlas_stock_decisions_daily` | 270 MB | 6K | Atlas intelligence | mv_stock_landscape |
| `atlas_etf_metrics_daily` | 175 MB | 280K | ETF pipeline | mv_etf_list_v6, mv_etf_deepdive |
| `atlas_etf_states_daily` | 128 MB | 292K | ETF pipeline | same |
| `atlas_etf_decisions_daily` | 43 MB | 206 | ETF pipeline | mv_etf_list_v6 |
| `atlas_etf_scorecard` | 248 kB | 136 | ETF pipeline + AMFI iNAV | mv_etf_list_v6, mv_etf_deepdive |
| `atlas_index_metrics_daily` | 143 MB | 265K | M3 daily | mv_sector_deepdive, mv_markets_rs_* |
| `atlas_sector_metrics_daily` | 39 MB | 76K | M3 daily | All 4 sector MVs |
| `atlas_sector_states_daily` | 30 MB | 75K | M3 daily | mv_sector_cards, mv_sector_deepdive |
| `atlas_cts_signals_daily` | 154 MB | 8K | SP09 CTS pipeline | mv_stock_deepdive |
| `atlas_stock_conviction_daily` | 13 MB | 6K | Atlas intelligence | mv_top_conviction_daily, mv_sector_deepdive |
| `atlas_scorecard_daily` | 4 MB | 2K | Atlas intelligence | mv_stock_deepdive |
| `atlas_signal_calls` | 296 kB | 587 | Atlas intelligence | mv_calls_performance |
| `atlas_etf_signal_calls` | (small) | 9 | Atlas intelligence | mv_etf_list_v6 |
| `atlas_cell_definitions` | (small) | 21 | Methodology lock | mv_stock_landscape |
| `atlas_market_regime_daily` | 1.5 MB | 2K | Regime engine | mv_current_market_regime, mv_market_regime_landing |
| `atlas_macro_daily` | 1.7 MB | 2752 | JIP + yfinance | mv_india_pulse |
| `atlas_universe_stocks` | 600 kB | 750 | Static (refreshed weekly) | All MVs |
| `atlas_universe_etfs` | (small) | 34 | Static | ETF pipeline |
| `atlas_universe_funds` | 560 kB | 587 | Static | Fund pipeline |
| `atlas_fund_scorecard` | 1.6 MB | 587 | Fund pipeline | mv_fund_list_v6 |
| `atlas_data_health` (NEW today) | (small) | 36/day | atlas_health_check.py | ops queries |
| `atlas_thresholds` | (small) | 30+ | Static config | M3/M4 compute |
| `atlas_benchmark_returns_cache` | 8.6 MB | 24K | M3 | Tier anchor lookups |
| `atlas_factor_returns_daily` | 248 kB | 2571 | M3 | mv_market_regime_landing |
| `atlas_tier_membership_daily` | 1.7 MB | 9K | M2 | Cap-tier joins |

### Materialized views — KEEP all 23

| Category | Count | Examples |
|---|---|---|
| Canonical v6 page MVs | 17 | mv_india_pulse, mv_sector_*, mv_stock_*, mv_etf_*, mv_fund_*, mv_calls_performance |
| SP02 supporting MVs | 5 | mv_rs_leaders_daily, mv_breakout_candidates, mv_deterioration_watch, mv_sector_rotation_state, mv_current_market_regime, mv_top_conviction_daily |
| Intraday | 1 | mv_rs_intraday |

---

## ARCHIVE — older table versions superseded by current pipeline

These have data but are NOT read by v6 MVs. Keep for 30 days then drop.

| Table | Size | Rows | Why archive |
|---|---|---|---|
| `atlas.atlas_stock_state_daily` (SINGULAR) | 216 MB | 526K | Pre-v6 schema; v6 uses `atlas_stock_states_daily` (plural) |
| `atlas.atlas_etf_state_v2` | 6.7 MB | 33K | v2 schema; v6 uses `atlas_etf_states_daily` |
| `atlas.atlas_sector_state_v2` | 2.7 MB | 10K | v2; v6 uses `atlas_sector_states_daily` |
| `atlas.atlas_fund_state_v2` | 1.3 MB | 4.8K | v2; v6 uses `atlas_fund_states_daily` |
| `atlas.atlas_conviction_daily` | 1.6 MB | 3K | Pre-v6; v6 uses `atlas_stock_conviction_daily` |
| `atlas.atlas_validator_findings` | 2.9 MB | 2.2K | SP04 weight-tuning artifact; review separately |
| `atlas.atlas_signal_ic_rolling` | 256 kB | 435 | SP04 internal — review separately |
| `atlas.atlas_signal_weights_live_perf` | 200 kB | 42 | SP04 internal |
| `atlas.atlas_weight_proposals` | 168 kB | 60 | SP04 internal |
| `atlas.atlas_fund_lens_monthly` | 1.9 MB | 3.5K | Older fund analytics; check if used by /funds page |
| `atlas.atlas_fund_decision_scores` | 1 MB | 3.5K | Pre-v6 fund decisions |
| `atlas.atlas_mf_recommendation_daily` | 376 kB | 587 | Pre-v6 fund recommendations |
| `atlas.atlas_cts_sector_pivot_daily` | 5 MB | 330 | SP09 — review if used |
| `atlas.atlas_stock_hit_rate_daily` | 544 kB | 2.2K | SP04 hit-rate engine |

---

## DROP — executed 2026-05-28 (2 truly-empty tables)

| Table | Size | Status |
|---|---|---|
| `public.de_market_cap_history` | 1.5 MB | ✅ DROPPED — verified 0 rows, no MV references, no code references |
| `public.mf_nav_history` | 44 MB | ✅ DROPPED — verified 0 rows, no MV references, no code references |

Total recovered: ~45 MB.

ANALYZE run on 13 tables to fix stale `pg_stat_user_tables.n_live_tup` (which was incorrectly reporting 0 for several tables that were actually full).

---

## NOT DROPPED — looked legacy, turned out active

⚠️ The following tables LOOKED legacy (0-row pg_stat, v2 suffix, pre-v6 naming) but verification proved they're STILL ACTIVE in production. **DO NOT drop without re-verifying first.**

### Active-write-path tables that report 0 rows due to stale stats

Fresh `COUNT(*)` 2026-05-28:

| Table | True row count | Why it stays |
|---|---:|---|
| `public.de_mf_holdings` | 242,654 | Active MF holdings; large dataset |
| `public.de_etf_holdings` | 12,499 | ETF holdings |
| `public.de_corporate_actions` | 11,500 | Loaded daily by `atlas_compute_adjustments.py` |
| `public.de_trading_calendar` | 7,305 | Trading day calendar |
| `public.de_index_constituents` | 2,910 | Nifty index constituents |
| `public.de_instrument` | 2,743 | Stock master (cross-checked) |
| `public.de_mf_master` | 1,359 | MF master |
| `public.de_mf_lifecycle` | 1,330 | MF lifecycle events |
| `public.de_healing_log` | 479 | Pipeline self-healing log |
| `atlas.strategy_paper_performance` | 345 | Strategy lab paper-trading |

### `*_v2` suffix tables that are STILL written by the v2 nightly pipeline

The v2 pipeline lives in a separate repo at `/home/ubuntu/atlas-os-sl/` (not in this repo's `atlas/`), which is why the in-repo grep showed 0 references. Cron job `0 16 * * 1-5 /home/ubuntu/atlas-os-sl/scripts/nightly_v2.sh` writes these.

| Table | Size | Active write evidence |
|---|---|---|
| `atlas.atlas_fund_state_v2` | 1.3 MB | n_tup_ins=9473, last analyzed 2026-05-27 (yesterday) |
| `atlas.atlas_sector_state_v2` | 2.7 MB | n_tup_ins=10,654, n_tup_upd=7,270 |
| `atlas.atlas_etf_state_v2` | 6.7 MB | Referenced by `frontend/src/lib/queries/etfs.ts` (LIVE) |

### Other "pre-v6" tables that turn out to be in the live code path

| Table | Size | Reference |
|---|---|---|
| `atlas.atlas_stock_state_daily` (singular!) | 216 MB | 6 references: frontend (`states.ts`, `regime-scorecard.ts`) + Python (`intelligence/states/persistence.py`, `tune_catalog.py`, `component_validator.py`, `trading/cli_states.py`). **HEAVILY USED.** |
| `atlas.atlas_conviction_daily` | 1.6 MB | Referenced by an MV definition |
| `atlas.atlas_mf_recommendation_daily` | 376 kB | Referenced by an MV definition |
| `atlas.atlas_fund_lens_monthly` | 1.9 MB | 8 code references |
| `atlas.atlas_validator_findings` | 2.9 MB | 8 references (SP04 validator chain) |
| `atlas.atlas_signal_ic_rolling` | 256 kB | 5 references (Atlas intelligence) |
| `atlas.atlas_signal_weights_live_perf` | 200 kB | 4 references |
| `atlas.atlas_weight_proposals` | 168 kB | 4 references (SP04 admin proposals page reads this) |
| `atlas.atlas_fund_decision_scores` | 1 MB | 3 references |
| `atlas.atlas_cts_sector_pivot_daily` | 5 MB | 4 references (SP09 CTS) |
| `atlas.atlas_stock_hit_rate_daily` | 544 kB | SP04 hit-rate engine |

---

## Lesson learned (write up for future cleanups)

**Never trust `pg_stat_user_tables.n_live_tup`** without a fresh `COUNT(*)`. The stat is updated by autovacuum/autoanalyze, which lags bulk inserts. A 0 there is NOT a guarantee of empty.

**Always grep `atlas-os-sl/` and other sibling repos** before declaring an atlas table unused. The v2 pipeline lives outside this repo.

**Always check `n_tup_ins` / `n_tup_upd` from pg_stat** — even if current row count looks "small for legacy", if those numbers are growing, the table is being actively written.

---

## Cleanup execution plan

**This week (low risk):**
1. Drop the 0-row public.de_* tables (legacy ingest scaffolding)
2. ANALYZE the universe tables to fix the stat lag

**Next sprint (medium risk):**
3. Migrate any code still referencing `atlas_stock_state_daily` (singular) to `atlas_stock_states_daily` (plural)
4. Drop the 5 v2-suffix tables (`*_state_v2`)
5. Drop SP04 artifacts if SP04 is fully retired

**Deferred (revisit after live-data accumulates):**
6. SP09 CTS tables — keep until walk-forward IC is locked
7. Strategy lab tables — keep until lab is sunset

---

## Verification queries

```sql
-- Confirm a table is truly unused: no references in MV definitions
SELECT m.matviewname
FROM pg_matviews m
WHERE definition ILIKE '%<table_name>%';

-- Confirm no recent writes
SELECT relname, n_tup_ins + n_tup_upd + n_tup_del AS writes_since_stats_reset
FROM pg_stat_user_tables
WHERE schemaname = 'atlas' AND relname = '<table_name>';

-- Confirm size before drop
SELECT pg_size_pretty(pg_total_relation_size('<schema>.<table>'::regclass));
```
