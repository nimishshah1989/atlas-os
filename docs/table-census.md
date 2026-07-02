# Atlas Table Census — single-schema consolidation manifest

**Date:** 2026-07-01
**Target end-state:** exactly ONE Postgres schema `atlas_foundation` (today `foundation_staging`) holds every table the LIVE v4 product needs. Everything else is migrated in or dropped.

**Verdict legend**
- **KEEP** — already in `foundation_staging`, produced+read by live code. Stays (schema renamed to `atlas_foundation`).
- **MIGRATE** — live-needed but currently sourced from `atlas.*` or `public.*` (or currently written by a backfill/mirror, not the live nightly). Producer + data must move into `atlas_foundation`; original drops after cutover.
- **DROP** — dead producer AND no live consumer (retired methodology, redundant mirror, separate product, orphan, Optuna, year-partition of a migrated table, us/global/mfwatch).
- **DECIDE** — genuinely ambiguous; question stated.

> **Method note.** Classifications below were verified against the live crontab, `scripts/run_atlas_nightly.sh`, `scripts/foundation/consolidate_tables.py` (the MIRRORS list), and reachable v6 frontend queries. Where the merged classifier JSON disagreed with the evidence, this manifest overrides it and the correction is flagged in §7. Partition families (`de_equity_ohlcv_y*`, `de_mf_nav_daily_y*`) are treated as ONE logical entry. Duplicate entries in the source JSON (two classifier passes over `atlas.*` and over `foundation_staging.*`) were de-duplicated.

---

## 1. Summary counts

De-duplicated logical tables (partition families collapsed, double-classified rows merged): **~150** distinct logical tables across 6 schemas.

### By verdict
| Verdict | Count (approx) |
|---|---|
| KEEP | 39 |
| MIGRATE | 34 |
| DROP | 71 |
| DECIDE | 6 |

### By schema
| Schema | KEEP | MIGRATE | DROP | DECIDE | Fate |
|---|---|---|---|---|---|
| `foundation_staging` (→ `atlas_foundation`) | 39 | 21 | 12 | 5 | becomes the one schema |
| `atlas` | 0 | 20 | 47 | 0 | drains into `atlas_foundation`, then dropped |
| `public` (JIP raw + Optuna) | 0 | 4 (families) | 22 | 1 | drains, then dropped |
| `us_atlas` | 0 | 0 | 16 | 0 | **schema dropped (FM D7)** |
| `global_atlas` | 0 | 0 | 11 | 0 | **schema dropped (FM D7)** |
| `mfwatch` | 0 | 0 | 18 | 0 | **schema dropped (FM D6)** |

---

## 2. KEEP — already native in `foundation_staging`, live-produced + live-read

### 2a. Raw / ingested (Atlas-owned sources)
| Table | Producer (live) | Consumer (live) |
|---|---|---|
| `ohlcv_stock` | `ingest_bhavcopy.py` (NSE bhavcopy, nightly step [1c]); JIP dual-source retiring | technicals, lenses, regime; all stock queries |
| `ohlcv_etf` | `ingest_bhavcopy.py` + `etf_sector_backfill.py` (nightly) | technicals, lenses; ETF queries |
| `index_prices` | `ingest_bhavcopy.py` (+ global benches) (nightly) | technicals, lenses, regime, index metrics; all market queries |
| `de_mf_nav_daily` | `ingest_nav.py` (AMFI/mfapi, nightly, writes fs directly) | fund lens, fund ranking, funds/sector-funds pages |
| `de_mf_holdings` | `ingest_mf_holdings.py` (Morningstar, weekly pg_cron, writes fs) | `fund_rank_core`, `fund_view`; sector-funds/funds pages |
| `de_mf_master` | `ingest_fund_master.py` (Morningstar, nightly, writes fs) | fund ingestion/ranking, thresholds |
| `financials_annual` | Screener/XBRL ingestion (mirrored into fs) | fundamental lens (`load_fundamental_data`) |
| `financials_quarterly` | Screener/XBRL ingestion (mirrored into fs) | fundamental lens |
| `corp_action` | `atlas_compute_adjustments.py` (close_adj recompute) | close-adjust recomputation |
| `corp_action_event` | fund ingestion (`ingest_nav.py`/master) | fund corp-action handling |

### 2b. Derived (native fs producers — the target scoring path)
| Table | Producer (live) | Consumer (live) |
|---|---|---|
| `atlas_scorecard_daily` | M2 → atlas, **mirrored** to fs (kept because live-read; see §3 for repoint) | `v6/sector_breadth`, `v6/snapshot`, `v6/cells` |
| `atlas_stock_metrics_daily` | M2 → atlas, **mirrored** to fs | `v6/stocks`, `v6/stock_detail`, `stocks.ts` |
| `atlas_etf_metrics_daily` | M2 → atlas, **mirrored** to fs | `v6/etfs` |
| `atlas_macro_daily` | M3 → atlas, **mirrored** to fs | `v6/market_pulse` |
| `atlas_market_regime_daily` | M3 → atlas, **mirrored** to fs | `v6/landing`, `v6/market_pulse`, `regime.ts` |
| `atlas_sector_metrics_daily` | M3 → atlas, **mirrored** to fs | `rollup_sectors.py` → `sector_lens_daily` |
| `atlas_sector_states_daily` | M3 → atlas, **mirrored** to fs | v6 sector pages |
| `atlas_fund_scorecard` | `run_fund_scorecard_for_date.py` (nightly step [5g]) | `v6/funds`, `v6/landing`, `v6/snapshot`, `v6/industry_snapshot` |
| `atlas_etf_scorecard` | `run_etf_scorecard_for_date.py` (nightly step [5h]) | `v6/etfs`, `v6/landing`, `v6/snapshot` |

> NOTE — the 7 mirrored derived tables above are KEEP *as fs destinations* but their **producers still write `atlas.*`** and reach fs only via `consolidate_tables.py` (broken since 2026-06-25). They are re-listed in §3 (MIGRATE) as producer-repoint work. Kept here because the fs table itself is the live-read object.

### 2c. Materialized views (mirrored from atlas M2/M3)
`mv_sector_cards`, `mv_sector_breadth`, `mv_sector_deepdive`, `mv_markets_rs_grid`, `mv_stock_landscape`, `mv_stock_landscape_trader`, `mv_etf_list_v6`, `mv_etf_deepdive` — all mirrored nightly by `consolidate_tables.py`; read by live board pages. **Producer-repoint tracked in §3.**

### 2d. Config / master / reference
| Table | Producer | Consumer |
|---|---|---|
| `atlas_thresholds` | mirror from `atlas.atlas_thresholds` (methodology config) | `calibrate_sectors`, `build_fund_rank_history`, `recompute_composite_fast`, lens pipeline |
| `atlas_sector_master` | mirror from `atlas.atlas_sector_master` | `v6/market_pulse` sector join |
| `atlas_universe_funds` | `ingest_fund_master.py` (writes fs directly) | `build_fund_rank_history`, fund queries |
| `atlas_universe_etfs` | mirror from `atlas.atlas_universe_etfs` (ETF ingest not yet repointed) | ingest pipeline (see §3 — should become Atlas-owned) |
| `policy_registry` | mirror from `atlas.policy_registry` | policy lens (`load_policy_registry`), policy alerts UI |
| `de_etf_holdings` | mirror from `public.de_etf_holdings` | `decile_core.py` (see §3 — JIP-sourced, mark for Atlas ingest) |
| `de_etf_master` | mirror from `public.de_etf_master` | ETF backend (see §3) |
| `de_index_constituents` | mirror from `public.de_index_constituents` | `build_breadth_series.py` |
| `de_trading_calendar` | mirror from `public.de_trading_calendar` | validation/housekeeping |

---

## 3. MIGRATE — the critical pre-drop worklist

Each row: **source → what must move into `atlas_foundation` (producer repoint + data-copy) → live reader.** Ordered by criticality (blockers first).

### 3a. Live scoring path still reading `atlas.*` (backend adapters/calibration)
| # | Source table | Move / repoint | Live reader |
|---|---|---|---|
| 1 | `atlas.atlas_lens_scores_daily` | **lens journal.** `atlas/lenses/pipeline.py` must be added to the live nightly and write `foundation_staging.atlas_lens_scores_daily` directly (today it is only written by non-live `lens_daily.py`; `calibration.py` still reads `atlas.*`). Data-copy: yes (journal history). | `calibrate_sectors`, `build_fund_rank_history`, foundation validation |
| 2 | `atlas.atlas_universe_stocks` | repoint `atlas/lenses/data/adapters.py` to `foundation_staging` (joins reuse `instrument_master`); migrate as reference. | live lens backend + stock queries |
| 3 | `atlas.atlas_decision_policy` / `atlas.policy_registry` | already mirrored to `foundation_staging.policy_registry`; repoint `adapters.py` reader to fs and stop reading `atlas.*`. | lens backend, policy alerts |

### 3b. Native fs builders NOT yet in the live nightly (produce fs, but must be wired into cron)
These already target `foundation_staging` but are only run by hand / backfill — they must join the nightly so the fs tables stay fresh.
| # | Table | Builder to wire into nightly | Live reader |
|---|---|---|---|
| 4 | `technical_daily` | `scripts/foundation/compute_all.py` — **BLOCKER**: master EMA/RSI/RS technicals for all instruments; only backfilled manually today. | lenses, regime; stock-detail technicals |
| 5 | `atlas_index_metrics_daily` (fs) | `build_index_metrics.py` — native calendar-anchored returns; NOT in nightly; fs copy currently stale/broken mirror. | `v6/stock_lens`, `v6/sector_index_rs` |
| 6 | `sector_lens_daily` | `rollup_sectors.py` (composite from sector metrics × weights) | `calibrate_sectors.py` |
| 7 | `fund_rank_daily` | `build_fund_rank_history.py` | `v6/fund_rank_history` |
| 8 | `mv_sector_rrg` | `build_sector_rrg.py` (JdK RS-ratio; native, corrected vs stale atlas snapshot) | v6 sector pages (via mv) |
| 9 | `breadth_nifty500_daily` | `build_breadth_series.py` (from `ohlcv_stock`+`technical_daily`) | reconcile_portal validation / breadth |

### 3c. Lens INPUT feeds not refreshed in the live pipeline (ingest scripts to wire in)
| # | Table | Ingest to wire into nightly | Live reader |
|---|---|---|---|
| 10 | `delivery_daily` | `fetch_delivery.py` (Flow lens delivery metric) | `load_technical_data` adapter |
| 11 | `lens_filings` | `ingest_filings.py` (BSE filings — catalyst lens) | `load_catalyst_data` |
| 12 | `lens_insider` | `ingest_insider.py` | `load_catalyst_data` |
| 13 | `lens_shareholding` | `ingest_shareholding.py` | `load_catalyst_data` |
| 14 | `lens_bulk_deals` | `ingest_bulk_deals.py` | `load_catalyst_data` |
| 15 | `screener_ratios` | `ingest_screener.py` (ROE/ROCE/PE/PB) | fundamental/valuation lens |
| 16 | `instrument_master` | integrate `build_universe.py`/`assign_sectors.py` refresh into nightly (sectors/ISIN/listing dates) | backend everywhere + frontend |

### 3d. Derived producers still writing `atlas.*` (repoint M2/M3 + scorecards to write fs directly; kill the mirror)
The whole M2/M3 output set is KEEP-as-fs-destination (§2b/2c) but MIGRATE-as-producer. After repoint, the `atlas.*` originals in the table below DROP.
| # | atlas.* source | fs destination | Live reader |
|---|---|---|---|
| 17 | `atlas.atlas_stock_metrics_daily` | `atlas_stock_metrics_daily` | v6 stocks/detail |
| 18 | `atlas.atlas_etf_metrics_daily` | `atlas_etf_metrics_daily` | v6 etfs |
| 19 | `atlas.atlas_scorecard_daily` | `atlas_scorecard_daily` | v6 cells/snapshot |
| 20 | `atlas.atlas_market_regime_daily` | `atlas_market_regime_daily` | v6 landing/market_pulse/regime |
| 21 | `atlas.atlas_macro_daily` | `atlas_macro_daily` | v6 market_pulse |
| 22 | `atlas.atlas_sector_metrics_daily` | `atlas_sector_metrics_daily` | rollup_sectors |
| 23 | `atlas.atlas_sector_states_daily` | `atlas_sector_states_daily` | v6 sector pages |
| 24 | `atlas.atlas_fund_scorecard` (via `run_fund_scorecard_for_date.py`) | `atlas_fund_scorecard` | v6 funds/landing |
| 25 | `atlas.atlas_etf_scorecard` (via `run_etf_scorecard_for_date.py`) | `atlas_etf_scorecard` | v6 etfs/landing |
| 26 | `atlas.mv_sector_*`, `mv_stock_*`, `mv_etf_*` | same fs mv names | v6 board pages |
| 27 | `atlas.atlas_stock_decisions_daily` | `atlas_stock_decisions_daily` | `v6/stock_detail` decision logic |

### 3e. `public.*` JIP raw → Atlas-owned ingestion (producer already migrated; copy history + repoint consumers)
| # | Source (public) | Move | Live reader still on public |
|---|---|---|---|
| 28 | `public.de_index_prices` | Atlas `ingest_bhavcopy.py` → `foundation_staging.index_prices` (producer done); copy history; repoint `atlas/regime/cron.py` + `build_index_metrics.py`. **LIVE-CRITICAL (regime).** | regime cron, index metrics |
| 29 | `public.de_equity_ohlcv_y*` (family, 2000–2034 + `_default`) | → `foundation_staging.ohlcv_stock` (Kite/NSE, done); repoint `atlas/regime/cron.py` breadth read; copy history; drop all partitions. | regime breadth cron |
| 30 | `public.de_mf_nav_daily_y*` (family, 2006–2034 + `_default`) | producer already `ingest_nav.py` → fs; repoint `funds.ts`/`sector-funds.ts` off `public.de_mf_nav_daily`; copy history; drop partitions. | funds/sector-funds pages |
| 31 | `public.de_mf_holdings` | producer already `ingest_mf_holdings.py` → fs; repoint `sector-funds.ts`/`funds.ts`/`lens_holdings.py` off public; copy history. | sector/fund detail |
| 32 | `public.de_etf_ohlcv` | Atlas ETF ingest → `foundation_staging.ohlcv_etf` (repoint ETF source off JIP); copy history. | ETF metrics (`compute/etfs.py`) |
| 33 | `foundation_staging.de_etf_holdings` / `de_etf_master` | currently mirror-from-JIP-public; convert to Atlas-owned ETF holdings ingest (not yet built). | `decile_core.py`, ETF backend |

### 3f. Reference/config still in `atlas.*` that live compute reads
| # | Source | Move | Reader |
|---|---|---|---|
| 34 | `atlas.atlas_universe_indices`, `atlas.atlas_signal_ic`, `atlas.atlas_signal_weights`, `atlas.atlas_validator_results`, `atlas.atlas_universe_stocks` | migrate snapshot to fs as reference (validator results feed `/admin/data-status`); repoint readers. | sector lookups, health/data-status page |

---

## 4. DROP — grouped by cluster

### 4a. Retired IC / conviction / strategy / CTS / decisions / signal cluster (`atlas.*`)
`atlas_signal_ic_rolling`, `atlas_signal_weights_live_perf`, `atlas_weight_proposals`, `atlas_weight_revert_log`, `atlas_threshold_history`, `atlas_state_thresholds`, `atlas_state_action_log`, `atlas_state_dwell_statistics`, `atlas_state_validation`, `atlas_stock_conviction_daily`, `atlas_stock_hit_rate_daily`, `atlas_stock_macro_overlay_map`, `atlas_stock_signal_unified`, `atlas_signal_calls`, `atlas_sector_signal_unified`, `atlas_regime_daily` (superseded by `atlas_market_regime_daily`), `atlas_run_log` (superseded by `atlas_pipeline_runs`), `atlas_strategy_evolution_log`, `atlas_strategy_genomes`, `atlas_strategy_history`, `atlas_strategy_insights`, `atlas_strategy_leaderboard`, `atlas_strategy_performance_daily`, `atlas_strategy_positions_daily`, `atlas_strategy_recommendations_daily`, `atlas_strategy_validation`, `atlas_tier_membership_daily`, `atlas_validation_results`, `atlas_validator_findings`, `atlas_signal_alerts` (public), `atlas_provenance_log`, `atlas_symbol_aliases`, `atlas_universe_membership_daily`, `atlas_v6_clean_ohlcv`, `atlas_v6_exclusions_log`, `atlas_v6_recommendations_daily`, `atlas_v6_strategy_runs`, `atlas_ledger`, `atlas_ledger_public`, `atlas_portfolio_config`, `atlas_portfolio_policy`, `atlas_user_lots`, `atlas_brief_cache`, `_wa2_daily_features`, `_wa2_weekly_persist`.

### 4b. `us_atlas` schema — FM Decision D7 (drop entirely; producers live but feed only orphan us-* routes)
`atlas_benchmark_master`, `atlas_benchmark_returns_cache`, `atlas_breadth_daily`, `atlas_etf_metrics_daily`, `atlas_etf_rs_states`, `atlas_etf_states_daily`, `atlas_market_regime_daily`, `atlas_run_log`, `atlas_stock_metrics_daily`, `atlas_stock_rs_states`, `atlas_stock_states_daily`, `atlas_thresholds`, `atlas_universe_etfs`, `atlas_universe_stocks`, `instruments`, `stock_ohlcv`. → also remove `us_stocks_daily.py`/`us_daily.py`/`stooq_daily_update.py` from `run_atlas_nightly.sh`.

### 4c. `global_atlas` schema — FM Decision D7 (drop entirely)
`atlas_benchmark_master`, `atlas_benchmark_returns_cache`, `atlas_etf_metrics_daily`, `atlas_etf_rs_states`, `atlas_etf_states_daily`, `atlas_market_regime_daily`, `atlas_run_log`, `atlas_thresholds`, `atlas_universe_etfs`, `instruments`, `stock_ohlcv`. → remove `global_daily.py` from nightly.

### 4d. `mfwatch` schema — FM Decision D6 (separate product; drop schema + pg_cron job 47 + Supabase edge fn)
Tables: `alert`, `benchmark_map`, `config`, `fund_attr_snapshot`, `news_item`, `portfolio`, `run_log`. Views: `v_allocation`, `v_benchmark_beating`, `v_category_avg`, `v_fund_benchmark`, `v_holdings_diff`, `v_holdings_summary`, `v_latest_nav_all`, `v_performance`, `v_portfolio`, `v_sector_by_date`, `v_sector_diff`.

### 4e. `public` Optuna leftovers
`studies`, `study_directions`, `study_system_attributes`, `study_user_attributes`, `trials`, `trial_heartbeats`, `trial_intermediate_values`, `trial_params`, `trial_system_attributes`, `trial_user_attributes`, `trial_values`.

### 4f. `public` JIP transitional / logs / retired (drop after JIP retired; not §3 migrations)
`alembic_version` (public), `atlas_signal_alerts`, `de_adjustment_factors_daily` (adj embedded in ohlcv), `de_contributors`, `de_corporate_actions`, `de_cron_run` (→ `atlas_pipeline_runs`), `de_pipeline_log`, `de_data_anomalies`, `de_global_instrument_master`, `de_global_prices`, `de_healing_log`, `tv_signal_reports`, `version_info`.

### 4g. `foundation_staging` mirror-cruft / retired M4/M5 / operational-metadata / orphan
- Retired M4/M5 in fs (no live producer, no reachable reader): `atlas_fund_metrics_daily`, `atlas_fund_states_daily`, `atlas_signal_ic`, `atlas_signal_weights`, `atlas_stock_conviction_daily`.
- Redundant: `atlas_universe_stocks` (frontend uses `instrument_master`), `equity_marketcap` (not in pipeline).
- Ingest resumption / operational metadata (not served data): `backfill_state`, `compute_state`, `ingest_run`, `lens_filings_state`, `lens_insider_state`, `lens_shareholding_state`, `screener_state`, `xbrl_state`.

---

## 5. DECIDE — ambiguous, needs an explicit call

| Table | Schema | Question |
|---|---|---|
| `atlas_etf_signal_calls` / `atlas_signal_calls` (fs) | foundation_staging | Read by live `v6/landing`, `v6/recent_signal_calls`, `v6/book_diff`, `v6/cells`, `v6/audit_trail` — but M5 (their only producer) is retired and they are NOT mirrored. **Is the v6 board still surfacing "signal calls", or are these pages showing stale data that should be removed?** If the feature is live, a native producer must be built (MIGRATE); if the pages are being retired, DROP the tables *and* the queries. |
| `instrument_master` (fs) | foundation_staging | Critical for all lookups but **not refreshed in the live nightly** (only `build_universe.py`/`assign_sectors.py` by hand). KEEP the table, but decide: which script becomes the nightly maintainer of sectors/ISIN/listing-dates? (Listed as MIGRATE #16.) |
| `technical_stock` (fs) | foundation_staging | Alternate/historical technicals table — is it redundant with `technical_daily`, or does any live validation query still need it? If redundant → DROP. |
| `sector_index_returns` (fs) | foundation_staging | Read by `v6/sector_index_rs` but producer unclear (M3 vs `build_index_metrics.py`). Confirm the producer and wire it into the nightly, else the page goes stale. |
| `atlas_cell_walkforward_runs` (atlas) | atlas | Write-once cell-walkforward backtest (migration 081z). No live consumer found. Is the Cells page's gate display sourced from this, or from `atlas_cell_rule_candidates`? If unused → DROP. |
| `de_mf_lifecycle` (public) | public | Fund launch/closure metadata. No confirmed live reader. KEEP-as-reference (migrate with `de_mf_master`) or DROP? Depends on whether fund-detail shows lifecycle context. |

---

## 6. Double-calc / duplication findings (G4)

The same computation lives in more than one place. Canonical copy noted; the other is the drop/repoint target.

1. **`atlas_index_metrics_daily` computed twice.** `atlas.*` (M3, row-count-anchored returns — WRONG on gap-ridden series: Nifty50 3m 6.9% vs true 3.2%, Media/Tourism NULL) **vs** `foundation_staging.*` (native `build_index_metrics.py`, calendar-anchored). **Canonical = foundation_staging (native).** atlas.* copy is de-mirrored already; drop it. *(MIGRATE #5.)*

2. **`mv_sector_rrg` computed twice.** `atlas.*` carried a stale broken snapshot (21/30 sectors stuck "Leading", RS-ratios >100) **vs** `foundation_staging` native `build_sector_rrg.py` (JdK RS-ratio vs Nifty 500). **Canonical = foundation_staging (native).** *(MIGRATE #8.)*

3. **Full M2/M3 derived set mirrored across schemas.** `atlas_stock_metrics_daily`, `atlas_etf_metrics_daily`, `atlas_scorecard_daily`, `atlas_market_regime_daily`, `atlas_macro_daily`, `atlas_sector_metrics_daily`, `atlas_sector_states_daily`, and all `mv_*` exist in BOTH `atlas.*` (producer) and `foundation_staging.*` (mirror via `consolidate_tables.py`). The mirror has been **BROKEN since 2026-06-25** (Market Pulse staleness). **Canonical target = foundation_staging; drop atlas.* after producers repoint** (MIGRATE §3d). Two schemas holding the same daily metrics is the core duplication this consolidation removes.

4. **OHLCV computed/landed twice.** stock: `public.de_equity_ohlcv_y*` (JIP) **vs** `foundation_staging.ohlcv_stock` (Kite/NSE, corp-action-adjusted). ETF: `public.de_etf_ohlcv` **vs** `foundation_staging.ohlcv_etf`. index: `public.de_index_prices` **vs** `foundation_staging.index_prices`. **Canonical = foundation_staging (Atlas-owned).** Drop public partitions after history copy + regime-cron repoint. *(MIGRATE #28/29/32.)*

5. **NAV landed twice.** `public.de_mf_nav_daily_y*` (legacy JIP partitions) **vs** `foundation_staging.de_mf_nav_daily` (Atlas `ingest_nav.py`, already live). **Canonical = foundation_staging.** Frontend `funds.ts`/`sector-funds.ts` still read the public copy → repoint, then drop partitions. *(MIGRATE #30.)*

6. **MF holdings landed twice.** `public.de_mf_holdings` (Morningstar mirror) **vs** `foundation_staging.de_mf_holdings` (Atlas `ingest_mf_holdings.py`, weekly pg_cron, live). **Canonical = foundation_staging.** `sector-funds.ts` / `lens_holdings.py` still read public → repoint. *(MIGRATE #31.)*

7. **Master reference duplicated.** fund master: `public.de_mf_master` vs `foundation_staging.de_mf_master` (Atlas-owned, canonical). instrument master: `public.de_instrument` / `atlas.atlas_universe_stocks` vs `foundation_staging.instrument_master` (canonical). thresholds: `atlas.atlas_thresholds` vs `foundation_staging.atlas_thresholds` (mirror; canonical = the one the lens pipeline reads = fs). Consolidate to the fs copy.

8. **Market-regime computed in 3 schemas.** `atlas.atlas_market_regime_daily` (India, canonical for v4), `us_atlas.atlas_market_regime_daily`, `global_atlas.atlas_market_regime_daily`. **Only the India copy survives** (→ fs); us/global drop (D7).

9. **Pipeline-run logging duplicated.** `atlas.atlas_pipeline_runs` (live, read by `v6/health`) vs `atlas.atlas_run_log` vs `public.de_cron_run` vs `public.de_pipeline_log` vs per-schema `atlas_run_log`. **Canonical = `atlas_pipeline_runs` (→ fs);** all others DROP.

---

## 7. Sanity-check — classifications overridden vs the source JSON

Corrections applied above where the merged classifier JSON was wrong given the live evidence:

1. **`atlas_fund_scorecard` / `atlas_etf_scorecard` (fs): source JSON said DECIDE/DROP ("M4 retired") — OVERRIDDEN.** Evidence: `scripts/run_atlas_nightly.sh` steps **[5g]/[5h]** run `run_fund_scorecard_for_date.py` / `run_etf_scorecard_for_date.py` nightly, and live `v6/funds.ts`, `v6/landing.ts`, `v6/etfs.ts` read `foundation_staging.atlas_fund_scorecard` / `atlas_etf_scorecard`. These are live. Classified **KEEP** (§2b) with a producer-repoint caveat (§3d #24/#25) — the scorecard script currently writes `atlas.*` and reaches fs via the (broken) mirror even though the MIRRORS list excludes it, so the producer must be repointed to write fs directly. **This is a live data-integrity risk to confirm.**

2. **`atlas_fund_metrics_daily` (fs) — kept as DROP but note the conflict.** One classifier pass called it KEEP (health.ts consumer). health.ts only reads freshness aggregates, not the table's data, and M4 is retired with no reachable page reader → **DROP** stands.

3. **`atlas_index_metrics_daily` (fs): one pass said MIGRATE, another KEEP — reconciled to MIGRATE (§3b #5).** The fs table is the live-read object but is currently a stale/broken mirror; the native `build_index_metrics.py` must be wired into the nightly. Not a plain KEEP because it is not yet live-produced in fs.

4. **`atlas_signal_calls` (fs): source JSON split KEEP-of-atlas-producer vs DROP-of-fs.** Because the fs copy IS read by multiple live v6 queries yet has no live producer, it is a genuine **DECIDE** (§5), not a clean DROP. Flagged for FM.

5. **`de_etf_holdings` / `de_etf_master` (public): source JSON said KEEP.** They are JIP-sourced and JIP is being retired (FM lock). The **fs mirror** copies are KEEP-as-reference short-term, but the public originals + the mirror dependency are **MIGRATE** to Atlas-owned ETF ingestion (§3e #33). Do not treat public.de_etf_* as a permanent keep.
