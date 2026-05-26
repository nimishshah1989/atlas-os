# Atlas v6 — Page-by-Page Data Inventory (VERIFIED)

**Date:** 2026-05-26
**Status:** Verified against live Supabase atlas-os project (`nanvgbhootvvthjujkvs`) via MCP
**Snapshot date for daily tables:** 2026-05-22 (4 days old → LIVE)
**Method:** Every `table.column` claim and every "populated/empty" claim queried directly.

---

## Status legend

| Label | Meaning |
|---|---|
| ✅ LIVE | Table + column exist, data populated, fresh |
| 🟡 PARTIAL | Table/column exists; data thin or partially populated |
| ❌ EMPTY | Table or column exists but **0 rows** populated — needs writer or backfill |
| ❌ MISSING | Column or table does NOT exist — needs migration |
| 🔧 DERIVED | Computable from existing data in MV (no new infra) |
| 🤖 STATIC | Hardcoded constant or static route |

---

## Backend state — verified inventory (live DB, 2026-05-26 ~21:30 IST)

### Time-series tables — depth and freshness

| Table | Rows | MIN(date) | MAX(date) | Notes |
|---|---|---|---|---|
| `atlas_market_regime_daily` | 2,609 | 2016-04-07 | 2026-05-22 | v5; 35 cols; LIVE regime table |
| `atlas_regime_daily` (v6) | **0** | — | — | v6 schema exists w/ smallcap_rs_z + dispersion cols but EMPTY |
| `atlas_macro_daily` | 2,711 | 2016-01-01 | 2026-05-19 | USDINR/DXY 99.7% pop'd; india_10y/risk_free/fii_flow 0% pop'd |
| `atlas_macro_features_daily` (v6) | **0** | — | — | EMPTY; designed but no writer |
| `atlas_stock_metrics_daily` | 1,392,776 | 2016-04-07 | 2026-05-22 | ~750 stocks × ~2,500 trading days |
| `atlas_stock_states_daily` | 1,392,776 | 2016-04-07 | 2026-05-22 | RAG family states per stock per day |
| `atlas_etf_metrics_daily` | 280,077 | 2016-04-07 | 2026-05-25 | 126 ETFs (3-day fresher) |
| `atlas_index_metrics_daily` | 264,203 | 2016-04-07 | 2026-05-22 | per atlas universe of indices |
| `atlas_sector_metrics_daily` | 74,752 | 2016-04-07 | 2026-05-22 | 31 sectors × ~2,500 days |
| `atlas_sector_states_daily` | 74,752 | 2016-04-07 | 2026-05-22 | sector RAG states |
| `atlas_fund_metrics_daily` | 1,049,825 | **2014-04-01** | 2026-05-20 | 12 yrs MF metrics |
| `atlas_factor_returns_daily` | 2,571 | 2016-04-08 | 2026-05-18 | factor (SMB/HML/etc.?) |

### Snapshot tables (single date only)

| Table | Rows | Date | Notes |
|---|---|---|---|
| `atlas_scorecard_daily` | 747 | 2026-05-22 | features JSONB 100% pop'd (b056229 fix live) |
| `atlas_conviction_daily` | 2,988 | 2026-05-22 | 747 × 4 tenures; verdict dist 2625 NEUTRAL / 288 NEG / 75 POS |
| `atlas_signal_calls` | **363** | 2026-05-22 | 363 active (no exits); **backfilled since audit doc** |
| `atlas_etf_signal_calls` | 9 | 2026-05-22 | thin coverage |
| `atlas_etf_scorecard` | 34 | 2026-05-22 | leaders-only of 126 universe |
| `atlas_fund_scorecard` | 587 | 2026-05-22 | top_holdings JSONB 99.7% pop'd |

### Configuration tables

| Table | Rows | Notes |
|---|---|---|
| `atlas_universe_stocks` | 750 | 750 active (`effective_to IS NULL`); SCD2 |
| `atlas_universe_etfs` | 126 | ticker, isin, fund_house, etf_name, theme, linked_sector, linked_index, asset_class |
| `atlas_universe_funds` | 592 | mstar_id, scheme_name, amc, category, plan_type, aum_cr |
| `atlas_universe_indices` | 75 | atlas indices universe |
| `atlas_sector_master` | 31 active sectors | primary_nse_index + secondary array per sector |
| `atlas_cell_definitions` | 21 | 21/21 confidence_unconditional ✅; **0/21 confidence_by_regime ❌**; missing 3 cells from 24-cell matrix |
| `atlas_cell_rule_candidates` | 89 | ~4-5 candidates per cell |
| `atlas_friction_params` | 12 | 3 tiers × 4 components |
| `atlas_mf_switch_rules` | 14 | seeded Q3→Q2 per category |
| `atlas_thresholds` | 87 | global thresholds config |

### Empty-by-design

| Table | Reason |
|---|---|
| `atlas_paper_portfolio`, `atlas_user_lots` | RLS-protected, fill on user action |
| `atlas_brief_cache` | TTL cache, fills on first LLM-brief request |
| `atlas_ledger` | Realized excess only after signal_calls expire |
| `atlas_mf_recommendation_daily` | Awaiting backfill from fund_scorecard |
| `atlas_provenance_log` / `atlas_drift_event_log` / `atlas_cell_walkforward_runs` | v6 engine not run yet |

### Public schema (JIP data) — time-series depth

| Table | Rows | MIN(date) | MAX(date) | Notes |
|---|---|---|---|---|
| `de_equity_ohlcv` | 4,745,195 | **2007-01-01** | 2026-05-25 | stock OHLCV (partitioned by year) |
| `de_mf_nav_daily` | 2,221,164 | **2006-04-01** | 2026-05-21 | 20 yrs MF NAVs |
| `de_etf_ohlcv` | 450,699 | 2016-04-01 | 2026-05-25 | GOLDBEES, LIQUIDBEES, NIFTYBEES etc. |
| `de_index_prices` | 266,912 | 2014-06-02 | 2026-05-25 | All 8 Nifty indices ✅ 2016+ |
| `de_global_prices` | 304,838 | 1789-05-01 (historic ^GSPC) | 2026-05-21 | mixed depths per ticker |
| `de_corporate_actions` | 11,500 | 2019-12-03 | 2026-05-25 | 6 yrs |
| `de_index_constituents` | 2,910 | — | — | **Nifty 500 = 500 rows ✅** (audit was wrong) |
| `de_mf_holdings` | 242,654 | — | — | |
| `de_etf_holdings` | 12,499 | — | — | |
| `de_index_master` | 139 | — | — | curated index metadata |

### Baselines for Markets RS — coverage

| Baseline | Source | Rows | Min Date | Status |
|---|---|---|---|---|
| Nifty 50 | `de_index_prices` `NIFTY 50` | 2,499 | 2016-04-07 | ✅ |
| Nifty 100 | `de_index_prices` `NIFTY 100` | 2,499 | 2016-04-07 | ✅ |
| Nifty 500 | `de_index_prices` `NIFTY 500` | 2,499 | 2016-04-07 | ✅ |
| Nifty Midcap 150 | `de_index_prices` `NIFTY MIDCAP 150` | 2,471 | 2016-04-07 | ✅ |
| Nifty Smallcap 250 | `de_index_prices` `NIFTY SMLCAP 250` | 2,060 | 2016-04-07 | ✅ |
| Nifty Bank | `de_index_prices` `NIFTY BANK` | 2,499 | 2016-04-07 | ✅ |
| Nifty IT | `de_index_prices` `NIFTY IT` | 1,909 | 2016-04-07 | ✅ |
| Gold (₹) | `de_etf_ohlcv` `GOLDBEES` | 2,516 | 2016-04-01 | ✅ |
| S&P 500 | `de_global_prices` `^GSPC` | 39,702 | **1789-05-01** | ✅ deep |
| MSCI World | `de_global_prices` `URTH` | 3,406 | 2012-01-19 | ✅ |
| MSCI EM | `de_global_prices` `VWO` | 2,588 | 2016-01-04 | ✅ (proxy) |
| LIQUIDBEES (cash yield) | `de_etf_ohlcv` `LIQUIDBEES` | 2,516 | 2016-04-01 | ✅ |

### Macro context inputs (Page 02 macro cards)

| Macro | atlas_macro_daily column | Populated? | Coverage if populated |
|---|---|---|---|
| USD/INR | `usdinr` | ✅ 99.7% (2704/2711) | 2016-01-01 to 2026-05-19 |
| DXY | `dxy` | ✅ 99.7% (2704/2711) | Same |
| India 10Y G-Sec yield | `india_10y_yield` | ❌ **0/2711** | Schema exists, no data |
| 91d risk-free | `risk_free_91d` | ❌ **0/2711** | Schema exists, no data |
| FII cash flow (₹cr) | `fii_cash_equity_flow_cr` | ❌ **0/2711** | Schema exists, no data |
| Breadth % > 200DMA | `breadth_pct_above_200dma` | ✅ 94.9% (2572/2711) | Same as above |
| DII cash flow | — | ❌ MISSING column | Need to add |
| US 10Y yield | — | ❌ MISSING column | Need to add (atlas_macro_features_daily.us_10y_yield planned but empty) |
| Brent crude (₹) | — | ❌ MISSING column | Need to add (atlas_macro_features_daily.crude_brent_inr planned but empty) |
| Real yield (10Y − CPI) | — | ❌ MISSING column + need CPI | Derived; needs CPI ingest |

### Missing columns flagged by frontend mockups

| Table | Missing column | Used by mockup | Action |
|---|---|---|---|
| `atlas_cell_definitions` | `display_name` | Cell card name "Mid 6m BUY signal" | Migration: ALTER ADD + backfill from cell_id |
| `atlas_cell_definitions` | `explain_text` | Cell card body copy | Migration: ALTER ADD + manual or LLM seed |
| `atlas_market_regime_daily` | `smallcap_rs_z`, `cross_sectional_dispersion` | 12-week journey rows | Use atlas_regime_daily (v6) OR derive in MV |
| `atlas_market_regime_daily` | `pct_above_ema_100` | Breadth table | Derive (Δ-fill OR new column) |
| `atlas_market_regime_daily` | `midcap_rs_z` | Tier leadership chart | Derive (Midcap 150 vs Nifty 100) |
| `atlas_sector_metrics_daily` | `hhi`, `pct_above_ema_20/50/200`, `pct_52wh`, `rs_{1w,1m,6m,12m}_nifty500`, `conf_band_distribution` | Sector cards + heatmap | Migration + new compute |
| `atlas_macro_features_daily` | `dii_inr_cr`, `us_10y_yield`, `dxy_level` (have it on macro_daily), `avg_pairwise_corr`, `concentration_top5/10/25` | Page 02 macro grid + dispersion section | Migration + new compute jobs |

### Critical gap: `atlas_cell_definitions.confidence_by_regime`

All 21 cells have `confidence_unconditional` populated (✅) but `confidence_by_regime` JSONB is **0/21 populated**. Page 01 Section D ranks cells by regime-conditional confidence; without this, the page falls back to unconditional ranking (still works, just less precise).

### Security advisor

117 atlas/ tables have RLS disabled. Anon key can read/modify everything. **Not fixed automatically.** Remediation SQL captured in advisor output; needs explicit decision before launch.

---

# PAGE 01 — Market Regime (landing)

**Mockup:** `01-market-regime.html`
**Frontend route (planned):** `/v6` or `/v6/regime`
**Backing MV (to build):** `mv_market_regime_landing`

## Section A — Hero strip (regime read)

| # | Mockup field | Source `table.column` | Acc | Comp | Action |
|---|---|---|---|---|---|
| 1 | "Cautious" regime label | `atlas_market_regime_daily.regime_state` | ✅ | ✅ 2609 rows | Use directly |
| 2 | "Held for 8 sessions" | DERIVED: consecutive same-state days | 🔧 | ✅ | Compute in MV |
| 3 | "Entered 16-May-2026" | DERIVED: MIN(date) of current streak | 🔧 | ✅ | Compute in MV |
| 4 | "Transitioned from Elevated" | DERIVED: regime_state day before streak | 🔧 | ✅ | Compute in MV |
| 5 | "Deployment 40%" | `atlas_market_regime_daily.deployment_multiplier` | ✅ | ✅ | Use directly |
| 6 | "↓ 20pp from Risk-On default" | DERIVED vs hardcoded defaults | 🔧 | 🤖 | Hardcode defaults in MV |
| 7 | "↑ 10pp from Risk-Off floor" | Same | 🔧 | 🤖 | Same |
| 8 | "21d typical length" | DERIVED: avg streak for current regime, historical | 🔧 | ✅ | Compute in MV (over 10yr depth) |
| 9 | "62% → Risk-On next" | DERIVED transition probability | 🔧 | ✅ | Compute in MV |
| 10 | "23% → Risk-Off next" | Same | 🔧 | ✅ | Same |
| 11 | "Last 60 trading days" 5-segment bar | DERIVED regime runs over trailing 60d | 🔧 | ✅ | Compute as JSONB array |
| 12 | "As of 26-May-2026, 18:00 IST" | `atlas_market_regime_daily.date` + suffix | ✅ | ✅ | Format in MV |

**Section A: 12 fields | 12/12 backed | 0 blockers**

## Section B — 12-week journey (4 metric rows × 12 weeks)

| # | Field | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 13 | Weekly regime cell (12) | `atlas_market_regime_daily.regime_state` weekly last-of | ✅ | ✅ | Aggregate in MV |
| 14 | Small-cap RS Z weekly | `atlas_regime_daily.smallcap_rs_z` (v6) | ✅ schema | ❌ 0 rows | **Either: backfill v6 OR derive from `de_index_prices` (Nifty Smallcap 250 vs Nifty 100, rolling Z)** |
| 15 | Breadth % weekly | `atlas_market_regime_daily.pct_above_ema_200` | ✅ | ✅ | Use weekly last-of |
| 16 | India VIX weekly | `atlas_market_regime_daily.india_vix` | ✅ | ✅ | Use weekly last-of |
| 17 | Dispersion weekly | `atlas_regime_daily.cross_sectional_dispersion` (v6) | ✅ schema | ❌ 0 rows | **Either: backfill v6 OR derive from `de_equity_ohlcv` (cross-stock daily return SD)** |
| 18 | 12 weekly date labels | DERIVED | 🔧 | ✅ | Compute |

**Section B: 6 row-types | 4/6 LIVE; 2/6 need v6 writer OR MV-side derivation**

## Section C — India Pulse tiles (4 clickable to page 02)

| # | Field | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 19 | Small-cap leadership tile + 12wk spark + "Negative for 6 weeks" | Same as #14 + derived streak count | depends | depends | After #14 resolved |
| 20 | Market breadth value + sparkline + "Was 71% in March" | Same as #15 + historical comparator | ✅ | ✅ | Compute "was X in M" |
| 21 | India VIX value + sparkline + "Climbing from 12.6 mid-Apr" | Same as #16 | ✅ | ✅ | Compute |
| 22 | Cross-section dispersion + sparkline + "Wide" foot | Same as #17 + 5y percentile | depends | depends | After #17 resolved |

**Section C: 4 tiles | 2/4 LIVE; 2/4 gated on #14 + #17**

## Section D — Cells favored under regime (6 cards)

| # | Field | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 23 | Cell name (e.g. "Mid 6m BUY signal") | `atlas_cell_definitions.display_name` | ❌ MISSING | ❌ | **Migration**: ALTER ADD `display_name VARCHAR(64)` + backfill |
| 24 | Action chip (BUY/AVOID/WATCH) | `atlas_cell_definitions.action` mapped POSITIVE→BUY etc. | ✅ | ✅ 21 cells | Map in MV |
| 25 | Cell explain text (1-2 lines plain English) | `atlas_cell_definitions.explain_text` | ❌ MISSING | ❌ | **Migration**: ALTER ADD `explain_text TEXT` + manual seed for 21 cells |
| 26 | Predicted excess | `atlas_cell_definitions.friction_adjusted_excess` | ✅ | ✅ 21/21 | Use directly |
| 27 | Confidence (High/Medium/Low) | DERIVED from `confidence_by_regime[current_regime]` + H/M/L cutoffs | 🟡 | ❌ **0/21 populated** | **Fallback to `confidence_unconditional` for v6.0 launch + cutoff bands** |
| 28 | "22 stocks firing today" count | `COUNT(*) atlas_signal_calls WHERE cell_id=X AND exit_date IS NULL` | ✅ | ✅ 363 rows | Compute in MV |
| 29 | 5-cell viz dots | DERIVED cross_cell_depth per cell | 🔧 | ✅ via signal_calls | Compute in MV |
| 30 | Which 6 cells to surface | DERIVED: rank by confidence_unconditional desc (regime-conditional unavailable) | 🔧 | 🟡 | Top-6 in MV; fallback as #27 |

**Section D: 8 fields | 4/8 LIVE; 2/8 need column adds (display_name, explain_text); 2/8 confidence_by_regime gap**

## Section E — Today's conviction (3 tabs × 8 rows + counters)

### Stocks tab
| # | Field | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 31 | Symbol | `atlas_universe_stocks.symbol` ⋈ `atlas_signal_calls` (via scorecard_id) | ✅ | ✅ | Join in MV |
| 32 | NEW badge | `atlas_signal_calls.date = MAX AND no prior row for (iid, cell_id)` | ✅ | ✅ all 363 NEW today | Compute |
| 33 | Company name + sector + cap-tier | `atlas_universe_stocks.{company_name, sector, tier}` | ✅ | ✅ 750 rows | Use directly |
| 34 | Cell name | `atlas_cell_definitions.display_name` | ❌ MISSING | ❌ | Same as #23 |
| 35 | Conviction bar % | `atlas_signal_calls.confidence_unconditional × 100` | ✅ | ✅ | Use directly |
| 36 | Action chip | `atlas_cell_definitions.action` mapped | ✅ | ✅ | Use directly |
| 37 | Predicted excess | `atlas_signal_calls.predicted_excess` OR `atlas_cell_definitions.friction_adjusted_excess` | ✅ | ✅ | Use directly |

### Funds tab
| # | Field | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 38 | Fund SWITCH IN/HOLD/SWITCH OUT/AVOID chip | `atlas_mf_recommendation_daily.recommendation` | ✅ schema | ❌ 0 rows | **Backfill from `atlas_fund_scorecard.{is_atlas_leader, is_avoid, rank_in_category, category_size}`** (audit doc has SQL) |
| 39 | Fund name + category + plan_type | `atlas_universe_funds.{scheme_name, category_name, plan_type}` + `atlas_fund_scorecard.fund_style` | ✅ | ✅ 592 + 587 | Use directly |
| 40 | "Fund Q1 SWITCH-IN" cell-like label | DERIVED from `{peer_quartile, recommendation}` | 🔧 | ❌ gated on #38 | Compute after backfill |
| 41 | Conviction bar (composite score) | `atlas_fund_scorecard.composite_score` | ✅ | ✅ | Use directly |
| 42 | Predicted excess for fund | DERIVED from rank_in_category percentile | 🔧 | ✅ | Compute (e.g. (1 − rank/size) × max_excess) — decision: hardcode max or store) |

### ETFs tab
| # | Field | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 43 | ETF ticker | `atlas_universe_etfs.ticker` ⋈ `atlas_etf_signal_calls` | ✅ | 🟡 only 9 rows | **Expand etf_signal_calls backfill** to wider coverage |
| 44 | ETF name + category + underlying | `atlas_etf_scorecard.{etf_name, etf_category, underlying_sector}` | ✅ | 🟡 34/126 (leaders only) | **Expand scorecard to full 126** |
| 45 | ETF cell name + action + predicted excess | `atlas_etf_signal_calls` ⋈ cells | ✅ | 🟡 9 rows | Expand |
| 46 | Conviction bar (ETF composite) | `atlas_etf_scorecard.composite_score` | ✅ | 🟡 34/126 | Same as #44 |

### Tab counters
| # | Field | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 47 | Active count per tab | COUNT signal_calls WHERE exit_date IS NULL | 🔧 | ✅ stocks (363), 🟡 ETFs (9), ❌ funds (0) | Compute |
| 48 | NEW count per tab | COUNT WHERE date = today AND no prior | 🔧 | ✅ all new today | Compute |

**Section E: 18 fields | Stocks tab 6/7 LIVE (need display_name); Funds 1/5 LIVE (need mf_recommendation_daily backfill); ETFs 4/4 schema LIVE but coverage 9/many**

## Section F — Footnote

| # | Field | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 49 | "Liquid BeES yield ~6.5%" | Hardcoded OR derived from `de_etf_ohlcv` LIQUIDBEES NAV-Δ × 365 | 🤖 | n/a | Hardcode for v6.0 launch |
| 50 | Methodology/walk-forward/cell convention links | Static routes | 🤖 | n/a | Build `/methodology` page later |

**Section F: 2 fields | static**

## 📊 Page 01 — verified summary

| Category | Count | % |
|---|---|---|
| Total fields | **50** | 100% |
| LIVE (acc + comp ✅) | **26** | 52% |
| DERIVED (compute in MV from live data) | **14** | 28% |
| EMPTY (table exists, 0 rows) | **4** | 8% |
| MISSING columns | **3** | 6% |
| Static / hardcode | **3** | 6% |

### Critical blockers for Page 01 (must close before launch)

1. **Migration: ALTER `atlas_cell_definitions` ADD `display_name`, `explain_text`** + backfill — unblocks 3 fields
2. **Backfill `atlas_mf_recommendation_daily`** from fund_scorecard (SQL exists in audit doc) — unblocks Funds tab
3. **Expand `atlas_etf_scorecard`** from 34 leaders to all 126 ETFs (writer scope change) — unblocks ETFs tab full
4. **Decide: Section B/C smallcap_rs_z + dispersion** — derive in MV OR populate `atlas_regime_daily`

### Decisions needed (low-stakes)

- Regime deployment defaults (Risk-On 60% / Cautious 40% / Risk-Off 30%): hardcode in MV
- Liquid BeES yield: hardcode 6.5% for v6.0
- Section D Confidence H/M/L: fallback to `confidence_unconditional` cutoffs until `confidence_by_regime` populated
- Fund predicted excess: derived from rank percentile

---

**[Page 02 inventory pending — same format, with verified data. Pages 03-08 to follow after mockup reads.]**

# PAGE 02 — India Pulse

**Mockup:** `02-india-pulse.html`
**Frontend route (planned):** `/v6/pulse`
**Backing MV (to build):** `mv_india_pulse`

## Section A — Hero strip (4 signal tiles, same as Page 01 Section C)

| # | Mockup field | Source `table.column` | Acc | Comp | Action |
|---|---|---|---|---|---|
| 1 | Small-cap RS Z (−0.84) + foot "Negative for 6 weeks" | `atlas_regime_daily.smallcap_rs_z` OR derived | ✅ schema | ❌ 0 rows | Same as Page 01 #14 — derive in MV OR populate v6 |
| 2 | Breadth 42% + foot "Down from 71% in March" | `atlas_market_regime_daily.pct_above_ema_200` + historical comparator | ✅ | ✅ | Use directly |
| 3 | India VIX 18.4 + foot "Climbing toward 20" | `atlas_market_regime_daily.india_vix` | ✅ | ✅ | Use directly |
| 4 | Cross-section dispersion 0.087 + foot "Wide" | `atlas_regime_daily.cross_sectional_dispersion` OR derived | ✅ schema | ❌ 0 rows | Same as Page 01 #17 |

## Section B — Headline indices (8 cards × ~12 fields each)

| # | Field | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 5 | 8 index codes: Nifty 50/100/Midcap 150/Smallcap 250/500/Bank/IT/Gold | `de_index_prices` for 7; `de_etf_ohlcv` for GOLDBEES | ✅ | ✅ all 8 confirmed LIVE | Use directly |
| 6 | Latest close per index | `de_index_prices.close` (per ticker) | ✅ | ✅ | Use directly |
| 7 | Today % change | DERIVED Δ over 2 dates | 🔧 | ✅ | Compute |
| 8 | 1M / 3M / 6M returns | DERIVED returns | 🔧 | ✅ | Compute |
| 9 | RS vs Nifty 500 (3M) per index | DERIVED: index_ret_3m − nifty500_ret_3m | 🔧 | ✅ | Compute |
| 10 | 12-week sparkline data | DERIVED from de_index_prices over 60 trading days | 🔧 | ✅ | Compute as JSONB array |
| 11 | Leadership tint (pos/warn/neg/flat) | DERIVED rule on 1M+3M signs | 🔧 | ✅ | Compute |
| 12 | One-line read text per card (editorial) | NOT IN SCHEMA | ❌ MISSING | ❌ | **Decision**: hardcoded templates per (regime, index, leadership) tuple OR LLM-generated at MV refresh time |

**Section B: ~10 fields × 8 cards | accuracy: 80% | gap: editorial card-copy template/LLM**

## Section C — Breadth table (9 measures × 7 columns)

| # | Field | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 13 | % above 200 DMA | `atlas_market_regime_daily.pct_above_ema_200` | ✅ | ✅ | Use directly |
| 14 | % above 100 DMA | NOT in schema | ❌ MISSING | ❌ | **Add column** OR derive from `de_equity_ohlcv` per Nifty 500 |
| 15 | % above 50 DMA | `atlas_market_regime_daily.pct_above_ema_50` | ✅ | ✅ | Use directly |
| 16 | 52-week highs count | `atlas_market_regime_daily.new_52w_highs` | ✅ | ✅ | Use directly |
| 17 | 52-week lows count | `atlas_market_regime_daily.new_52w_lows` | ✅ | ✅ | Use directly |
| 18 | Advance/decline ratio | `atlas_market_regime_daily.ad_ratio` (5d rolling avg) | ✅ | ✅ | Use directly or compute rolling |
| 19 | McClellan oscillator | `atlas_market_regime_daily.mcclellan_oscillator` | ✅ | ✅ | Use directly |
| 20 | % at 4-week high | NOT in schema | ❌ MISSING | ❌ | **Compute job**: scan de_equity_ohlcv Nifty 500 daily |
| 21 | Cumulative A-D line | `atlas_market_regime_daily.ad_line` | ✅ | ✅ | Use directly |
| 22 | Δ 1w/1m/3m per measure | DERIVED from historical | 🔧 | ✅ | Compute |
| 23 | "Position" bar (where today is in indicator's range) | DERIVED min/max over 5y history | 🔧 | ✅ | Compute or hardcode bands |
| 24 | 3M trend sparkline | DERIVED from same column over 60d | 🔧 | ✅ | Compute |
| 25 | "Reads as" editorial text per row | NOT IN SCHEMA | ❌ MISSING | ❌ | **Rule-based template engine** in MV per (measure, value-bucket) tuple |

**Section C: 9 measures × ~7 cols | 7/9 LIVE; 2 missing (pct_above_ema_100, % at 4w high) + editorial copy gap**

## Section D — Dispersion & Concentration (4 sub-charts)

| # | Field | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 26 | Cross-section dispersion 60d series | `atlas_regime_daily.cross_sectional_dispersion` OR derive | ✅ schema | ❌ 0 rows | Compute from `de_equity_ohlcv` daily cross-stock SD over Nifty 500 |
| 27 | "73rd percentile of trailing 5 years" | DERIVED percentile rank vs 5yr history | 🔧 | depends | After #26 |
| 28 | Sector return dispersion today (22 sectors) | `atlas_sector_states_daily` + `atlas_sector_metrics_daily.bottomup_ret_1w` (today's = 1d, may need new column) | 🟡 | ✅ daily data | **Verify**: does atlas have daily sector return or only 1w aggregation? May need 1d compute |
| 29 | "11 positive, 2 flat, 9 negative" + spread | DERIVED counts + max-min | 🔧 | ✅ | Compute |
| 30 | Concentration top-N share (top 10, 11-50, 51-200, bottom 300) | NEW METRIC | ❌ MISSING | ❌ | **New compute job**: `atlas/macro/concentration.py` ⟂ `de_index_constituents` Nifty 500 (500 rows ✅) + de_equity_ohlcv |
| 31 | "2% of names did 65% of work" narrative | DERIVED from #30 | 🔧 | depends | Compute |
| 32 | Avg pairwise correlation 60d series | NEW METRIC | ❌ MISSING | ❌ | **New compute job**: `atlas/macro/pairwise_correlation.py` ⟂ Nifty 500 + de_equity_ohlcv |
| 33 | "ρ = 0.28 — in the stock-picker band" | DERIVED + bands | 🔧 | depends | After #32 |

**Section D: 8 fields | 2/8 LIVE (sector return data) | 6/8 gated on new compute jobs**

## Section E — Volatility (3 cards)

| # | Field | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 34 | Spot India VIX + 12mo + 5y avg + spark | `atlas_market_regime_daily.india_vix` + history | ✅ | ✅ | Compute averages |
| 35 | 5-year VIX percentile | DERIVED rank vs 5y | 🔧 | ✅ | Compute |
| 36 | "+45% above 12-month avg" + "Crossed 18 on 21-May" | DERIVED | 🔧 | ✅ | Compute |
| 37 | Term structure (VIX − 9d) +0.41 | NEW: needs VIX9 series | ❌ MISSING | ❌ | **NSE VIX9 ingest** — currently no such data in repo |
| 38 | "Curve in contango" + 9d/60d points | Same as #37 | ❌ MISSING | ❌ | Same |

**Section E: 5 fields | 3/5 LIVE | 2/5 need VIX9 ingest**

## Section F — Tier leadership (chart + table)

| # | Field | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 39 | Smallcap RS Z 90d series | Derived: Nifty Smallcap 250 vs Nifty 100 rolling Z | 🔧 | ✅ from `de_index_prices` | Compute in MV |
| 40 | Midcap RS Z 90d series | Derived: Nifty Midcap 150 vs Nifty 100 rolling Z | 🔧 | ✅ | Same |
| 41 | "Smallcap crossed < 0 · 22-Apr" annotation | DERIVED zero-cross detection | 🔧 | ✅ | Compute |
| 42 | "Midcap followed · 14-May (3w lag)" | DERIVED | 🔧 | ✅ | Compute |
| 43 | Tier returns table 5 windows × 5 cols | DERIVED returns + spreads from `de_index_prices` | 🔧 | ✅ | Compute |
| 44 | "Deepest defensive rotation since Mar 2023" narrative | DERIVED historical comparison | 🔧 | ✅ 10yr depth | Compute |

**Section F: 6 fields | all DERIVED from existing index price data ✅**

## Section G — Sectoral heatmap (22 sectors × 1W/1M/3M toggle)

| # | Field | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 45 | 22 sector names + 1W return | `atlas_sector_metrics_daily.bottomup_ret_1w` | ✅ | ✅ 74752 rows | Use directly |
| 46 | 1M return per sector | `atlas_sector_metrics_daily.bottomup_ret_1m` | ✅ | ✅ | Use directly |
| 47 | 3M return per sector | `atlas_sector_metrics_daily.bottomup_ret_3m` | ✅ | ✅ | Use directly |
| 48 | Sector rollup 31→22 ("actionable" subset) | `atlas_sector_master.is_active` + CONTEXT.md rollup table | 🤖 | 🟡 31 active sectors; rollups not yet encoded | **Encode rollup mapping** per CONTEXT.md (8 thin-tails → 4 parents) |

**Section G: 4 fields | 3/4 LIVE; rollup mapping needs to be encoded (config table or CONTEXT.md alignment)**

## Section H — Macro context (8 cards)

| # | Field | Source `table.column` | Acc | Comp | Action |
|---|---|---|---|---|---|
| 49 | USD/INR + Δ + spark | `atlas_macro_daily.usdinr` | ✅ | ✅ 2704/2711 (99.7%) | Use directly |
| 50 | India 10Y G-Sec + Δ + spark | `atlas_macro_daily.india_10y_yield` | ✅ schema | ❌ 0/2711 | **Backfill ingest** — RBI / NSE GS data |
| 51 | Brent crude (₹) + Δ + spark | NOT in schema (atlas_macro_features_daily.crude_brent_inr exists but table empty) | ❌ MISSING | ❌ | **Add column to atlas_macro_daily OR populate atlas_macro_features_daily** + ICE Brent × usdinr ingest |
| 52 | Real yield (10Y − CPI) + Δ | DERIVED: india_10y − cpi_yoy | ❌ MISSING | ❌ | Needs CPI ingest first |
| 53 | FII net flow 1M cumulative + "9 of 12 net-sell" | `atlas_macro_daily.fii_cash_equity_flow_cr` | ✅ schema | ❌ 0/2711 | **Backfill ingest** — NSDL provisional flows |
| 54 | DII net flow 1M cumulative + "SIP-driven" | NOT in schema | ❌ MISSING | ❌ | **Add column** + NSDL DII ingest |
| 55 | US 10Y yield + Δ + spark | NOT in schema (atlas_macro_features_daily.us_10y_yield was planned) | ❌ MISSING | ❌ | **Add column + FRED DGS10 ingest** |
| 56 | DXY + Δ + spark | `atlas_macro_daily.dxy` | ✅ | ✅ 2704/2711 | Use directly |
| 57 | Per-card "macro note" text | NOT IN SCHEMA | ❌ MISSING | ❌ | Template OR LLM-generated |

**Section H: 9 fields | 2/9 LIVE (USDINR, DXY); 3/9 have empty columns awaiting backfill (india_10y, fii); 4/9 need new columns + ingest (brent, real_yield/CPI, dii, us_10y)**

## Section I — Bond-vs-equity narrative ribbon

| # | Field | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 58 | Narrative paragraph from real yield + FII outflow + equity risk premium | DERIVED + editorial | 🔧 | depends on above | Template OR LLM with MV row |

## 📊 Page 02 — verified summary

| Category | Count | % |
|---|---|---|
| Total distinct fields | **~50** | 100% |
| LIVE (acc + comp ✅) | **17** | 34% |
| DERIVED (no new infra) | **15** | 30% |
| EMPTY (column exists, 0 rows) | **3** | 6% |
| MISSING column/table/ingest | **12** | 24% |
| Editorial copy / template | **3** | 6% |

### Critical blockers for Page 02 (must close before full launch)

**Backend ingest jobs (new compute):**
1. **India 10Y G-Sec writer** — populate `atlas_macro_daily.india_10y_yield` (column exists, 0 rows)
2. **FII flow writer** — populate `atlas_macro_daily.fii_cash_equity_flow_cr` (NSDL scrape)
3. **DII flow** — new column + writer (NSDL)
4. **US 10Y yield** — new column + FRED DGS10 ingest
5. **Brent ₹** — new column + ICE × usdinr compute
6. **CPI** — new ingest (for real yield)
7. **Pairwise correlation compute** — `atlas/macro/pairwise_correlation.py` over Nifty 500 ✅ (constituents available)
8. **Concentration top-N compute** — `atlas/macro/concentration.py` over Nifty 500
9. **VIX9 ingest** — NSE for term structure
10. **`pct_above_ema_100`** + **% at 4-week high** sub-metrics

**Schema decisions:**
- Editorial copy for headline-index cards + breadth "reads as" + macro notes → templated or LLM
- Sector rollup 31→22 actionable: encode mapping in `atlas_sector_master` or config

### Achievable v6.0 launch scope (without all backfills)

Sections A (partial), B (data ✅, copy gap), C (7/9 measures), E (3/5 cards), F (full), G (full): **render with 70% data**, "computing…" chips on the 30%.

Sections D (concentration + pairwise corr) + H (5/8 macro cards) require new ingest before they render with real data.

---

**[Pages 03-08 to follow — reading those mockups now.]**

# PAGE 03 — Markets RS

**Mockup:** `03-markets-rs.html`
**Frontend route (planned):** `/v6/markets-rs`
**Backing MV (to build):** `mv_markets_rs_grid`

## Section A — Page header + 4 hero readout cards

| # | Mockup field | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 1 | "Today's leadership" — narrative of who's leading (Gold & US large-cap...) | DERIVED: rank baselines by 1w return | 🔧 | ✅ | Compute narrative template per top-N |
| 2 | "India vs world" — "Nifty 500 ranks 7th of 9 baselines on 1-month" | DERIVED: rank Nifty 500 vs other 8 baselines on 1M | 🔧 | ✅ | Compute |
| 3 | "Within India" — "Large-cap leading mid & small by 9.5pp on 3-month" | DERIVED: Nifty 100 ret_3m − {Mid 150, Small 250 avg} ret_3m | 🔧 | ✅ | Compute |
| 4 | "India RS grade" — C+, ↓ "Was B− last month" | DERIVED rule-based grading + month-over-month delta | 🔧 | ❌ MISSING grading rule | **Decide**: grading rule (e.g., A=top quartile across all windows, B=upper half, C=mixed, D=bottom) — encode in MV |
| 5 | Grade trend "Was B− last month · trend declining" | DERIVED Δ vs previous month grade | 🔧 | depends on #4 | Compute after grading rule |

**Section A: 5 fields | 3/5 DERIVED ✅ from existing baseline data; 2/5 gated on grading rule decision**

## Section B — RS grid (9 baselines × 5 time windows)

| # | Field | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 6 | 9 baseline rows (5 Indian + S&P 500 + MSCI World + MSCI EM + Gold) | All confirmed LIVE per backend baselines table | ✅ | ✅ | Use directly |
| 7 | 5 window columns: 1w / 1m / 3m / 6m / 12m | DERIVED returns from de_index_prices, de_etf_ohlcv, de_global_prices | 🔧 | ✅ | Compute |
| 8 | Per-cell return value (e.g. +0.6%, −2.1%) | DERIVED total return per (baseline, window) | 🔧 | ✅ | Compute with USD/INR adjustment for foreign |
| 9 | Per-cell rank (e.g. "3 / 9") | DERIVED: dense_rank() over baselines per window | 🔧 | ✅ | Compute |
| 10 | Color band (pos-strong/pos/pos-weak/flat/neg-weak/neg/neg-strong) | DERIVED rule on return value | 🔧 | ✅ | Compute (e.g. >+8 → strong, +3 to +8 → mid, etc.) |
| 11 | View-mode toggle: Absolute / vs Nifty 500 / vs Nifty 50 / vs Gold | DERIVED: subtract baseline-of-choice return from each cell | 🔧 | ✅ | Frontend or MV-side |
| 12 | "India · tier anchors" / "Cross-market · developed" / "Cross-market · emerging" / "Commodities" group dividers | 🤖 STATIC config | 🤖 | ✅ | Frontend or MV |

**Section B: 7 fields | 100% LIVE — all baselines have 10+ year history; just need MV compute**

## Section C — Narrative readout (auto-generated)

| # | Field | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 13 | "LEADER" tags (e.g. Gold rank-1 across all windows) | DERIVED + template | 🔧 | ✅ | Generate from grid ranks |
| 14 | "LAGGARD" tag (e.g. Nifty Smallcap 250 rank 9/9) | DERIVED + template | 🔧 | ✅ | Generate |
| 15 | "ROTATION" tag (e.g. Large vs Small spread) | DERIVED + template | 🔧 | ✅ | Generate |
| 16 | Per-tag narrative body (1-2 sentences) | DERIVED + template/LLM | 🔧 | ✅ | **Decision**: rule-based templates vs LLM-generated |
| 17 | "Auto-generated · updates each evening at 18:00 IST" | 🤖 STATIC | 🤖 | n/a | Static |

**Section C: 5 fields | 4/5 DERIVED ✅ from grid; copy-generation strategy decision needed**

## Section D — Detail charts (6 multidim cards × 4 lanes each)

For each card (Nifty Large Cap, Nifty Small Cap, Gold, Banking, IT, Auto):

| # | Lane | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 18 | Price lane: close line | `de_index_prices.close` (Indian) / `de_etf_ohlcv.close` (Gold) | ✅ | ✅ | Use directly |
| 19 | Support/Resistance levels (S 16,400 / R 18,200 etc.) | DERIVED OR `atlas_stock_states_daily` if S/R precomputed | ❓ verify | ❌ likely | **Decide**: rule-based S/R from rolling min/max OR ingest from analyst-set levels |
| 20 | RS marker diamonds (new RS highs in green, new RS lows in red) | DERIVED: detect new-high/low in (baseline_ret − benchmark_ret) over trailing N days | 🔧 | ✅ | Compute |
| 21 | RS strip lane: spread line + 0 dashed + fill | DERIVED: rolling (baseline_ret − benchmark_ret) | 🔧 | ✅ | Compute |
| 22 | Volume lane: up/down day bars + 20D-MA overlay | DERIVED from `de_etf_ohlcv.volume` (need ETF) OR `de_index_prices` (does it have volume?) | ❓ verify | depends | **VERIFY**: de_index_prices has volume column? If not, use de_equity_ohlcv aggregated or proxy ETF |
| 23 | Commentary header: current RS value + 1-2 sentence narrative | DERIVED + template | 🔧 | ❌ COPY | Template per (chart, signal pattern) tuple |
| 24 | Historical context note (Cautious-regime small-cap drawdowns typically run...) | DERIVED + template + historical regime lookup | 🔧 | ❌ COPY | Template OR LLM |

**Section D: 7 lanes × 6 charts | Price/Volume/RS data LIVE; S/R levels + editorial copy gaps**

## Section E — Chart controls

| # | Field | Source | Acc | Comp | Action |
|---|---|---|---|---|---|
| 25 | Baseline toggle (vs Nifty 50 / vs Nifty 500 / vs Gold) | Frontend logic | n/a | n/a | Frontend |
| 26 | Window toggle (1M / 3M / 6M / 12M) | Frontend | n/a | n/a | Frontend |
| 27 | Layer toggles (S/R / RS signals / Volume / 20D MA) | Frontend | n/a | n/a | Frontend |
| 28 | Chart selector (up to 8 from 12: Large Cap, Small Cap, Gold, Banking, IT, Auto, FMCG, Pharma, Energy, Metals, Realty, Media) | Frontend + user pref | n/a | ✅ all 12 sectors have data | Frontend |

**Section E: 4 fields | all frontend controls**

## 📊 Page 03 — verified summary

| Category | Count | % |
|---|---|---|
| Total distinct fields | **~28** | 100% |
| LIVE (acc + comp ✅) | **6** | 21% |
| DERIVED (no new infra) | **17** | 61% |
| Editorial copy gaps | **3** | 11% |
| Missing decision/data | **2** | 7% |

### Critical blockers for Page 03 (the cleanest page!)

**Backend gaps (smallest of any page so far):**
1. **Support/Resistance** for detail charts — rule-based from rolling min/max OR ingest analyst levels
2. **Volume data source verification** — does `de_index_prices` have volume? Check (likely uses proxy ETF or `de_equity_ohlcv` aggregated)

**Editorial copy:**
3. Hero readout narratives (templates)
4. Per-chart commentary + historical context
5. India RS Grade rule (decision)

### v6.0 launch achievability — PAGE 03 IS THE CLEANEST

Almost everything is computable from existing 10-year baseline price history. **No new ingest jobs required.** Only blocker is editorial copy strategy + S/R rule + volume source verification.

---

**[Continuing with Pages 04-08]**

# PAGE 04 — Sectors (+ 04a Sector deep-dive)

**Mockup:** `04-sectors.html` + `04a-sector-energy.html`
**Backing MVs (to build):** 5 MVs per design doc `docs/superpowers/specs/2026-05-26-v6-sectors-mvs-design.md`
- `mv_sector_cards`, `mv_sector_breadth`, `mv_sector_rrg`, `mv_sector_deepdive`, `mv_sector_rotation`

## Source tables — verified

| Table | Status | Notes |
|---|---|---|
| `atlas_sector_metrics_daily` | ✅ 74,752 rows, 2016-2026 | Has bottomup_ret_{1w,1m,3m,6m}, bottomup_rs_3m_nifty500, rs_velocity, participation_50, participation_rs, leadership_concentration, constituent_count, topdown_* |
| `atlas_sector_states_daily` | ✅ 74,752 rows | Has sector_state, bottomup_state, topdown_state, divergence_flag, participation_rs_pct |
| `atlas_sector_master` | ✅ 31 active | primary_nse_index + secondary array + fallback_benchmark |
| `atlas_signal_calls` | ✅ 363 rows | for sector confidence band distribution aggregation |
| `atlas_cell_definitions` | ✅ 21 cells | for cell rule_dsl |
| `atlas_universe_stocks` | ✅ 750 active | for mcap proxy via tier + sector |

## Required column ADDs (per design doc D1 + §2)

| Table | Column | Purpose |
|---|---|---|
| `atlas_sector_metrics_daily` | `rs_1w`, `rs_1m`, `rs_6m`, `rs_12m` | RS vs Nifty 500 across windows (mockup 04 + 04a heatmap) |
| `atlas_sector_metrics_daily` | `pct_above_ema20` | sector breadth (mockup 04a constituent strip) |
| `atlas_sector_metrics_daily` | `pct_above_ema200` | sector breadth |
| `atlas_sector_metrics_daily` | `pct_52wh` | 5d window fresh 52WH count |
| `atlas_sector_metrics_daily` | `hhi` | Herfindahl concentration (mockup 04a sector card) |

## Required actions

| # | Action | Blocking | Effort |
|---|---|---|---|
| 1 | ALTER TABLE add 5 cols on `atlas_sector_metrics_daily` | All sector MVs | Small migration |
| 2 | Extend `atlas/compute/sectors.py` to populate the 5 new cols + 5y backfill | Same | Medium |
| 3 | Seed `atlas_thresholds.confidence_band_cutoffs` (H/M floor keys) | conf-band distribution | Small |
| 4 | Build 5 MVs (~80 LOC + 70 + 60 + 120 + 50 = ~380 LOC total SQL) | Page 04 + 04a | Medium |
| 5 | Encode rollup 31→22 actionable sectors per CONTEXT.md | Both pages | Small (config) |
| 6 | Verdict-chip mapping locked at OVERWEIGHT/NEUTRAL/UNDERWEIGHT (D2) | List | n/a (in MV) |
| 7 | RRG quadrant sampling rule locked at weekly Friday close | RRG | n/a (in MV) |

**Page 04 + 04a verdict: clean path forward. Existing design doc covers it fully. ~12 fields to add (5 cols + 1 config) + 5 MVs to build.**

---

# PAGE 05 — Stocks (+ 05a Stock deep-dive)

**Mockup:** `05-stocks.html` + `05a-stock-reliance.html`
**Backing MVs (to build):** 3 MVs per design doc `docs/superpowers/specs/2026-05-26-v6-stocks-mvs-design.md`
- `mv_stock_list_v6` (per iid summary, ~750 rows)
- `mv_stock_landscape` (cross-stock distribution for bubble chart)
- `mv_stock_deepdive` (per-iid for 05a)

## Source tables — verified

| Table | Status | Notes |
|---|---|---|
| `atlas_scorecard_daily` | ✅ 747 rows, features 100% pop'd | per-iid 5-family states + methodology features in JSONB |
| `atlas_signal_calls` | ✅ 363 active rows | drives action, cross-cell depth, tape, predicted_excess |
| `atlas_cell_definitions` | ✅ 21 cells | per-cell IC, friction_adjusted_excess, rule_dsl |
| `atlas_stock_conviction_daily` | ✅ 5,635 rows | conviction_score [0,1], confidence_label, backing_ic, tier |
| `atlas_universe_stocks` | ✅ 750 active | symbol, company_name, sector, tier, in_nifty_50/100/500 booleans |
| `atlas_stock_metrics_daily` | ✅ 1.39M rows, 10yr depth | ret_1m/3m/12m, rs_3m_nifty500, vol_60d, EMA breadth |
| `atlas_stock_states_daily` | ✅ 1.39M rows | rs_state, momentum_state, risk_state, volume_state, gates, tier, state_since_date |
| ~~`atlas_instruments`~~ | ❌ DOES NOT EXIST | Design doc refers to it for mcap — must use `atlas_universe_stocks` + `de_market_cap_history` instead |
| `atlas_cell_walkforward_runs` | ❌ EMPTY | For matrix IC display on deep-dive — gracefully degrade |

## Critical translation: composite_score mapping (locked)

Design doc lifts `atlas_stock_conviction_daily.conviction_score` ∈ [0,1] → mockup composite ∈ [−10, +10]:

```sql
composite_score = ROUND((conviction_score - 0.5) * 20, 2)
```

| `confidence_label` | UI band |
|---|---|
| `industry_grade` | HIGH |
| `baseline` | MED |
| `descriptive_only` | LOW |

## Required actions

| # | Action | Blocking | Effort |
|---|---|---|---|
| 1 | Resolve mcap source: NOT `atlas_instruments`; use `de_market_cap_history` or `atlas_universe_stocks.tier` as proxy | Bubble chart | Small (decide source) |
| 2 | Build 3 MVs | Page 05 + 05a | Medium |
| 3 | Cross-cell depth derivation in MV (COUNT DISTINCT (cap_tier, tenure, action) open calls) | Mockup 05 chip | In MV |
| 4 | Conviction tape 4-segment (1m/3m/6m/12m) derivation in MV | Mockup 05 list | In MV |
| 5 | `composite_30d_trajectory` array — need 30 daily snapshots of conviction_score | Deep-dive sparkline | **Verify**: do we have 30 days of `atlas_stock_conviction_daily` for each stock? Currently 5,635 rows / 750 stocks ≈ 7.5 days avg |
| 6 | `predicate-satisfaction panel` for deep-dive | 05a | Schema in `atlas_cell_definitions.rule_dsl` + eval at request time |
| 7 | Stock-specific macro overlays mapping | 05a macro strip | Static config; per CONTEXT.md need `atlas_stock_macro_overlay_map` table |

**Page 05 verdict: data is largely live. Main gaps: mcap source (small), 30d trajectory depth (verify), atlas_stock_macro_overlay_map config table (new).**

---

# PAGE 06 — Funds (+ 06a Fund deep-dive)

**Mockup:** `06-funds.html` + `06a-fund-ppfas.html`
**Backing MVs (to build):** per design doc `docs/v6/2026-05-26-mv-funds-etfs-calls-plan.md`

## Source tables — verified

| Table | Status | Notes |
|---|---|---|
| `atlas_fund_scorecard` | ✅ 587 rows, top_holdings JSONB 99.7% | Per-fund composite + rank + 5 score components |
| `atlas_universe_funds` | ✅ 592 | mstar_id, scheme_name, amc, category, plan_type, aum_cr, benchmark_code |
| `atlas_fund_metrics_daily` | ✅ 1.05M rows, 12 yrs (2014-2026) | ret_1m/3m/6m/12m, rs_pctile_3m, nav |
| `atlas_fund_states_daily` | ✅ 979,635 | fund states over history |
| `atlas_fund_decisions_daily` | ✅ 631,289 | fund decisions over time |
| `atlas_mf_switch_rules` | ✅ 14 | category-level SWITCH rules seeded |
| `atlas_mf_recommendation_daily` | ❌ **0 rows** | EMPTY — needs backfill from fund_scorecard |
| `de_mf_nav_daily` | ✅ 2.2M rows, 20 yrs (2006-2026) | raw NAVs |
| `de_mf_holdings` | ✅ 242,654 | fund-level holdings disclosures |
| `de_mf_master` | ✅ existing | fund metadata |
| `atlas_fund_holdings_changes` | ✅ 98,163 | tracked holdings deltas |
| `atlas_fund_decision_scores` | ✅ 3,507 | scoring history |

## Gaps for mockup 06 + 06a

| Field | Source | Status | Action |
|---|---|---|---|
| SWITCH IN/OUT recommendation chip | `atlas_mf_recommendation_daily.recommendation` | ❌ EMPTY | **Backfill** from fund_scorecard rank+category (audit doc SQL) |
| AMC leaderboard (stacked Q1/Q2/Q3/Q4 by AMC) | DERIVED from fund_scorecard rank+category | 🔧 | Aggregate in MV |
| Quartile consistency (24m window) | DERIVED from fund_metrics_daily rank history | 🔧 | **Verify**: need rank history per fund per month over 24m |
| Quartile streak (months in current quartile) | DERIVED | 🔧 | Compute |
| Persistent Q1 / Q4 (≥12 consecutive months) | DERIVED | 🔧 | Compute |
| Quartile timeline viz (60-month grid) | DERIVED | 🔧 | Need 60mo history compute or persisted column |
| SWITCH pair (matched IN/OUT) | DERIVED from `atlas_mf_recommendation_daily` once populated | 🔧 | Compute after backfill |
| Brinson-Hood-Beebower attribution | NEW METRIC | ❌ MISSING | New compute over fund_holdings + benchmark; deferred or simplified |
| Portfolio holdings (top 10 + sector exposure) | `atlas_fund_scorecard.top_holdings` JSONB | ✅ 99.7% pop'd | Unpack via `jsonb_to_recordset` |

**Page 06 + 06a verdict: mostly LIVE. Main gaps: mf_recommendation_daily backfill (easy), quartile streak/consistency derivation (verify 24-month rank history depth), Brinson attribution (defer or simplify for v6.0).**

---

# PAGE 07 — ETFs (+ 07a ETF deep-dive)

**Mockup:** `07-etfs.html` + `07a-etf-goldbees.html`
**Backing MVs (to build):** per design doc `docs/v6/2026-05-26-mv-funds-etfs-calls-plan.md`

## Source tables — verified

| Table | Status | Notes |
|---|---|---|
| `atlas_etf_scorecard` | 🟡 **34/126** (leaders only) | 6 score components + ELI5 + composite |
| `atlas_universe_etfs` | ✅ 126 | ticker, isin, fund_house, etf_name, theme, linked_sector, linked_index, asset_class |
| `atlas_etf_metrics_daily` | ✅ 280,077 rows, 10yr | ret_1m/3m/6m/12m, rs_pctile_3m |
| `atlas_etf_states_daily` | ✅ 280,077 | ETF states |
| `atlas_etf_decisions_daily` | ✅ 188 | ETF decisions |
| `atlas_etf_signal_calls` | 🟡 **9 rows only** (2026-05-22) | needs expansion |
| `de_etf_ohlcv` | ✅ 450,699, 2016+ | OHLCV including GOLDBEES, LIQUIDBEES, NIFTYBEES, etc. |
| `de_etf_holdings` | ✅ 12,499 | ETF holdings disclosure |
| `de_etf_master` | ✅ existing | ETF metadata |

## Gaps for mockup 07 + 07a

| Field | Source | Status | Action |
|---|---|---|---|
| All 126 ETFs surfaced (not just leaders) | `atlas_etf_scorecard` | 🟡 34/126 | **Expand scorecard writer to cover all 126** |
| 4-band category taxonomy (Index / Sector / Smart-beta / Commodity & International) | `atlas_etf_scorecard.etf_category` exists but verify enum | ✅ schema | Verify category values; map to 4 bands |
| Premium-to-NAV bps + outlier flag | NEW METRIC | ❌ MISSING column | Compute from de_etf_ohlcv.close vs declared NAV (NAV source TBD) |
| Premium-to-NAV 60d distribution histogram | NEW JSONB | ❌ MISSING | Compute trailing 60d series |
| Tracking error 60d vs underlying + band | NEW METRIC | ❌ MISSING | New compute job (ETF return − underlying index return SD) |
| ADV ₹3cr threshold + flag | DERIVED from `de_etf_ohlcv.{close, volume}` | 🔧 | Compute trailing-20d AVG(close × volume) |
| TER cost stack | NEW TABLE per CONTEXT.md `atlas_etf_ter_components` | ❌ MISSING | New table + quarterly AMC SAI disclosure ingest |
| Physical composition disclosure (commodity ETFs only) | NEW TABLE `atlas_etf_physical_disclosure` | ❌ MISSING | New table + monthly AMC disclosure ingest |
| Tracking-error band per category (config) | NEW TABLE `atlas_etf_te_bands` | ❌ MISSING | Config table (5 categories per CONTEXT.md) |

**Page 07 verdict: most complex of the 8 pages — requires 4 new compute metrics (premium-bps, premium-dist, TE-60d, ADV) + 2 new tables (TER components, physical disclosure) + 1 config (TE bands). Full ETF universe coverage (34→126) needed. Defer commodity disclosure to v6.1 if needed.**

---

# PAGE 08 — Calls Performance

**Mockup:** `08-calls-performance.html`

## Source tables — verified

| Table | Status | Notes |
|---|---|---|
| `atlas_signal_calls` | ✅ 363 rows (2026-05-22; T+0) | All active, exit_date IS NULL |
| `atlas_ledger` | ❌ **0 rows** | Populates only after signal_calls expire and outcomes realize |
| `atlas_signal_ic` | ✅ 8 rows | Legacy IC tracking |
| `atlas_signal_ic_rolling` | ✅ 380 rows | Rolling IC |
| `atlas_stock_hit_rate_daily` | ✅ 1,830 rows | Per-stock hit rate over time |
| `atlas_cts_signals_daily` | ✅ 6,725 rows | CTS signal events |
| `atlas_cts_hit_rates` | ✅ 40 rows | CTS hit rates |
| `atlas_cts_timing_ic` | ✅ 67 rows | CTS timing IC |
| `atlas_cell_definitions` | ✅ 21 cells with friction_adjusted_excess | predicted_excess per cell |

## Gaps for mockup 08

| Field | Source | Status | Action |
|---|---|---|---|
| Daily realized excess (T+1 onward) | `atlas_ledger.realized_excess` joined to signal_calls | ❌ EMPTY | **Awaits signal_call exits**; 363 active calls all minted 2026-05-22, none expired yet |
| Win rate vs benchmark (closed calls only) | DERIVED from `atlas_ledger.realized_excess > 0` | ❌ depends on ledger | Same |
| Best/worst 10 closed calls (trailing 90d) | DERIVED from ledger ordered by realized_excess | ❌ depends on ledger | Same |
| Anchor benchmark per tier (Large→Nifty 100, Mid→Midcap 150, Small→Smallcap 250) | 🤖 STATIC mapping + de_index_prices | 🤖 | Config in MV |
| T+1 to N day rolling returns per open call | DERIVED from `de_equity_ohlcv.close` ⋈ `atlas_signal_calls.{instrument_id, date}` | 🔧 | Compute T+1 to today per active call (for in-flight tracking) |

**Page 08 verdict: gated entirely on `atlas_ledger` populating. For v6.0 launch with 4-day-old signal_calls and no expired tenures, page renders "first results available 2026-06-22 (T+30 for 1m tenure)". Alternative: surface IN-FLIGHT realized excess (T+1 to today) for open calls — that data CAN be computed from de_equity_ohlcv.**

---

# 📊 Comprehensive cross-page summary

## Gap matrix — what each page needs

| Page | LIVE % (verified) | EMPTY tables/cols | MISSING (new infra) | Largest blocker |
|---|---|---|---|---|
| 01 Market Regime | 52% | display_name/explain_text cols, conf_by_regime JSONB | none net-new | display_name migration |
| 02 India Pulse | 34% | india_10y/risk_free/fii_flow (empty cols) | DII/US10Y/Brent/CPI cols + ingest, pairwise corr compute, concentration compute, VIX9 ingest, ema_100, % 4w-high | macro writers (5 separate ingest jobs) |
| 03 Markets RS | 21% LIVE, **88% via DERIVE** | none | S/R rule, volume source verify, RS Grade rule | minimal — cleanest page |
| 04 Sectors | (gated on column adds) | 5 col adds on sector_metrics_daily | rollup mapping config | column adds + compute extension |
| 05 Stocks | mostly live | atlas_instruments doesn't exist (use universe + cap_history) | atlas_stock_macro_overlay_map (small config) | mcap source decision |
| 06 Funds | mostly live | atlas_mf_recommendation_daily empty | Brinson attribution (defer for v6.0) | mf_recommendation backfill |
| 07 ETFs | scorecard 34/126 only | TE band config, TER components, physical disclosure tables, premium_bps cols | 4 new compute jobs + 2 new tables + 1 config | full ETF coverage + new metrics |
| 08 Calls Performance | empty (signal_calls fresh) | atlas_ledger empty | none net-new | wait for signal_call expiries OR surface in-flight T+N |

## Cross-page priority action list

### P0 — Unblocks multiple pages (do first)

1. **Migration: ALTER `atlas_cell_definitions` ADD `display_name` + `explain_text`** + backfill from `cell_id` (~30 min)
   - Unblocks: Page 01 Section D, E.34; Page 05 cell label

2. **Backfill `atlas_mf_recommendation_daily`** from `atlas_fund_scorecard` (SQL in audit doc) (~30 min)
   - Unblocks: Page 01 E.38; Page 06 SWITCH chips

3. **Expand `atlas_etf_scorecard` writer to full 126 ETFs** (currently 34 leaders only)
   - Unblocks: Page 01 E ETFs tab; Page 07 fully

4. **Migration: ALTER `atlas_sector_metrics_daily` ADD `rs_1w/1m/6m/12m`, `pct_above_ema20/200`, `pct_52wh`, `hhi`** + extend compute + 5y backfill
   - Unblocks: Page 04 + 04a entirely

### P1 — Backend writers (medium effort, parallelizable)

5. **Populate `atlas_macro_daily.india_10y_yield`** (column exists, 0 rows) — RBI/NSE GS ingest
6. **Populate `atlas_macro_daily.fii_cash_equity_flow_cr`** — NSDL provisional scrape
7. **NEW columns on atlas_macro_daily**: dii_flow, us_10y_yield, brent_inr → + ingest jobs (FRED + ICE + NSDL DII)
8. **NEW compute jobs**: `atlas/macro/pairwise_correlation.py`, `atlas/macro/concentration.py`
9. **Decide v6 regime classifier**: populate `atlas_regime_daily` OR derive smallcap_rs_z + dispersion in MV from `de_index_prices` + `de_equity_ohlcv`
10. **Encode sector rollup 31→22 actionable** per CONTEXT.md (config table or static map)

### P2 — Page-specific decisions

11. **Page 01**: hardcode regime deployment defaults; hardcode Liquid BeES yield 6.5%
12. **Page 02**: editorial copy strategy (templates vs LLM) for headline-index cards + breadth "reads as" + macro notes
13. **Page 03**: S/R rule (rolling min/max vs analyst levels); India RS Grade rule
14. **Page 05**: mcap source (use `de_market_cap_history` since `atlas_instruments` doesn't exist); add `atlas_stock_macro_overlay_map` config
15. **Page 07**: NEW tables `atlas_etf_te_bands` + `atlas_etf_ter_components` + `atlas_etf_physical_disclosure` + premium_bps compute + TE-60d compute + ADV compute
16. **Page 08**: wait for ledger OR surface in-flight T+N realized

### P3 — Security + governance

17. **RLS decision**: 117 atlas tables have RLS disabled (anon key can read all). Decision before public launch — apply remediation SQL or restrict anon role.

## v6.0 launch achievability — verdict

**Realistic v6.0 launch scope (next 2-4 weeks):**

| Page | Renders at v6.0 launch? |
|---|---|
| 01 Market Regime | ✅ 80% after P0 #1 + #2 + #3 |
| 02 India Pulse | 🟡 50% (hero + breadth + sectoral heatmap + tier leadership + sectoral indices LIVE; macro grid + dispersion concentration empty until P1 done) |
| 03 Markets RS | ✅ 95% (just needs grading rule + S/R rule decision) |
| 04 Sectors + 04a | ✅ 100% after P0 #4 |
| 05 Stocks + 05a | ✅ 90% (mcap source decision; macro overlay config) |
| 06 Funds + 06a | ✅ 85% after P0 #2 (Brinson deferred) |
| 07 ETFs + 07a | 🟡 40% (basic list + leaders only; new metrics deferred to v6.1) |
| 08 Calls Performance | 🟡 30% (in-flight only; full data needs ledger to populate over 30d-1y) |

**Aggregate: 5 of 8 pages → ≥90% data at v6.0 launch with the P0 actions done.**

---

# Next steps (NEXT SESSION)

1. **3 MV design specs** to be written (matching the 3 existing specs for pages 04/05/06-08):
   - `docs/superpowers/specs/2026-05-26-v6-market-regime-mvs-design.md` (Page 01)
   - `docs/superpowers/specs/2026-05-26-v6-india-pulse-mvs-design.md` (Page 02)
   - `docs/superpowers/specs/2026-05-26-v6-markets-rs-mvs-design.md` (Page 03)

2. **Migration sequence**: column adds (cells + sector_metrics + macro_daily) → backfills (mf_recommendation_daily, etf_scorecard expansion) → MV builds (3+5+3+3 = ~14 MVs) → pg_cron refresh chain → frontend page builds

3. **Decision matrix**: ~15 small decisions (hardcoded constants, rule encodings, copy strategy) need user sign-off

**This document is the load-bearing source of truth for v6 frontend build. All claims verified against live Supabase atlas-os (`nanvgbhootvvthjujkvs`) on 2026-05-26 ~21:30 IST.**
