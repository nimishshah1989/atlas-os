# Atlas v6 — Backend Buildout Master Plan

**Date:** 2026-05-26
**Owner:** Nimish + Claude
**Status:** APPROVED — execute in order, no frontend code until Phase G
**Companion doc:** [`docs/v6/2026-05-26-page-data-inventory.md`](./2026-05-26-page-data-inventory.md) — every claim verified against live Supabase atlas-os (`nanvgbhootvvthjujkvs`) via MCP
**Discipline:** 100% backend before any frontend line. All daily/weekly/monthly jobs must be wired, tested, stable for 7 days before Phase G starts.

---

## The principle

> **Backend must be a feature-complete, qualitatively checked, accurate platform — then frontend is pure plug-in.**

No partial pages. No "we'll patch the data layer later." No yFinance-as-primary. No undocumented decisions. No 60% data on the day of launch.

---

## Synopsis (verified) — Page × data readiness

| Page | Data points needed | Have working data | New cols needed | New tables needed | New writers/ingest |
|---|---|---|---|---|---|
| **01 Market Regime** | 50 | **31 (62%)** | 2 (`display_name`, `explain_text`) | 0 | 0 |
| **02 India Pulse** | ~50 | **32 (64%)** | ~8 on `atlas_macro_daily` | 0 | 5-6 (NSDL FII/DII, FRED US10Y/DXY, ICE Brent, CPI, pairwise corr, concentration, VIX9) |
| **03 Markets RS** | 28 | **23 (82%)** ← cleanest | 0 | 0 | 0 |
| **04 Sectors** | ~40 | gated | ~8 on `atlas_sector_metrics_daily` | 0 | extend `atlas/compute/sectors.py` |
| **05 Stocks** | ~45 | mostly LIVE | 0 | 1 (`atlas_stock_macro_overlay_map`) | + fundamentals ingest (see §Fundamentals) |
| **06 Funds** | ~40 | mostly LIVE | 0 | 0 | 1 backfill (`atlas_mf_recommendation_daily`) |
| **07 ETFs** | ~35 | partial | 3 on `atlas_etf_scorecard` | 3 (TE bands, TER components, physical disclosure) | 4 compute jobs |
| **08 Calls Performance** | ~12 | mostly empty | 0 | 0 | 0 (auto-fills as calls expire) |

**Totals:** ~21 column adds across 3 tables · 4 new tables · 9 net new ingest/compute jobs · 2 backfills · 14 MVs.

---

## Historical depth requirement (user direction)

**Every derived metric must back-compute at least 5 years; ideally 10 years where raw data permits.**

| Raw data table | Available depth | Derived metric historical mandate |
|---|---|---|
| `de_equity_ohlcv` | 2007 (19 yrs) | 10 years — full history |
| `de_index_prices` | 2014 (12 yrs) | 10 years |
| `de_etf_ohlcv` | 2016 (10 yrs) | 10 years |
| `de_mf_nav_daily` | 2006 (20 yrs) | 10 years |
| `de_global_prices` (^GSPC, URTH, VWO, GLD) | 2012-2016 (10-14 yrs) | 10 years |
| `atlas_market_regime_daily` | 2016 (10 yrs) | 10 years |
| `atlas_macro_daily` | 2016 (10 yrs) | 10 years |
| `atlas_stock_metrics_daily` | 2016 (10 yrs) | 10 years |
| `atlas_sector_metrics_daily` | 2016 (10 yrs) | 10 years |

**Backfill discipline:** every new column-add migration in Phase B is followed by a backfill job in Phase C that populates the column from 2016-04-07 onward (matching the JIP data start date). Where derivation requires shorter window (60d rolling correlation, 24m quartile streak), the metric is computed for every trading day in the 10-year window.

**5-year hard floor:** any metric where 10-year computation is infeasible (corp-action gaps, missing constituents) gets 5-year minimum from 2021-05-26 onward.

---

## Stock fundamentals data (user direction)

**Current state:** `atlas_universe_stocks` carries `symbol, company_name, sector, industry, tier, in_nifty_500` — NO fundamentals (P/E, EPS, ROE, book value, margins, revenue growth).

**Mockup 05a Reliance stock deep-dive needs:**
- P/E ratio, P/B, EV/EBITDA
- Last 4 quarters revenue, EBITDA, net profit, margins
- ROE, ROCE
- Debt/equity, interest coverage
- Promoter holding, FII holding, DII holding
- Sales growth YoY, profit growth YoY, 5-yr CAGR
- Sector relative P/E

**Source priority (NSE-first per user direction; no yFinance unless last resort):**

| Source | Coverage | Cost | Reliability |
|---|---|---|---|
| **NSE corporate filings** (XBRL via NSE BSE) | Quarterly + annual | Free, official | High |
| **NSE/BSE listings + corporate actions** | Static + events | Free | High |
| **Screener.in** | Aggregated ratios + financials | Free with rate limit; HTML scrape | Medium (HTML changes) |
| **AMFI (for fund-related)** | Fund holdings + AUM | Free | High |
| **MoneyControl** | Same as Screener | Free with rate limit | Medium |
| **TIJORI Finance** | Indian-market focused | Paid | High if subscribed |
| **yFinance** | Aggregated global | Free Python | **LAST RESORT — breaks frequently** |

**Phase C add:** new ingest job `atlas/data_ingest/fundamentals.py` writing to a new table `atlas_stock_fundamentals_quarterly` (one row per stock per quarter end, columns covering all the above metrics). Initial source: NSE XBRL filings + Screener.in supplemental scrape. 10-year backfill (2016-Q1 onward = 40 quarters).

---

## Indian macros + F&O sourcing (user direction)

**Indian macros — NSE/RBI/MOSPI first:**

| Macro series | Primary source | Backup | Free? |
|---|---|---|---|
| USD/INR daily | **RBI reference rate** (https://rbi.org.in) | NSE FX rates | ✅ Free, daily 1:30pm IST |
| India 10Y G-Sec yield | **NSE GS market** (NSE WDM) | RBI bulletin | ✅ Free |
| 91-day T-bill yield | **NSE T-bill segment** | RBI auction results | ✅ Free |
| CPI YoY | **MOSPI** monthly release | RBI bulletin | ✅ Free, ~12th of next month |
| WPI YoY | MOSPI | — | ✅ Free |
| IIP | MOSPI | — | ✅ Free |
| FII cash equity | **NSDL CMOTS** (HTML daily) | NSE provisional | ✅ Free, T+1 |
| DII cash equity | NSDL CMOTS | NSE provisional | ✅ Free, T+1 |
| FII/DII derivatives flow | NSE F&O participant-wise data | — | ✅ Free |
| India VIX | **NSE direct** (already in atlas_market_regime_daily.india_vix) | — | ✅ |
| Nifty VIX9 (short-dated) | **NSE direct** (NSE archives) | — | ✅ |
| Crude Brent (USD) | **MCX crude (₹)** | ICE / EIA free CSV | ✅ |
| Gold INR/g | **MCX gold spot** | RBI bulletin | ✅ |

**US macros — FRED (free official API):**
- US 10Y (DGS10), DXY (DTWEXBGS), Fed funds, US CPI — all free from FRED API key (1 line of code each)

**F&O (Futures & Options) — entirely new addition per user direction:**

Mockup needs (verifying which pages):
- Page 01 / 02: PCR (Put-Call Ratio) as sentiment indicator? (decide if shown)
- Page 05 (stocks): per-stock open interest, F&O ban list, near-month futures premium/discount, IV
- Sector page: sectoral OI changes

**Source:** NSE F&O bhavcopy daily (CSV, free, T+0), option chain endpoint (NSE direct), participant-wise OI (NSE).

**New tables for F&O (Phase C scope):**
- `de_fno_bhavcopy_daily` (every (symbol, expiry, strike, opt_type) per day) — partitioned by year similar to de_equity_ohlcv
- `de_fno_oi_daily` (rolled-up OI per stock per day)
- `de_fno_participant_oi_daily` (FII/DII/Pro/Retail OI breakdown)
- `atlas_stock_fno_metrics_daily` (PCR, IV, futures-spot basis, OI build-up — derived, per stock per day)

**5-year F&O backfill** from NSE archives (NSE keeps F&O bhavcopy 5+ years online).

---

## The 7-phase buildout — gstack skill sequence per phase

### Phase A — Inventory & dead-code burn (½–1 day)

**Goal:** Clean foundation. No mystery tables.

**Steps:**
1. Drop 8 tables tagged `ATLAS-REVIEW-UNUSED` in DB comments after explicit sign-off:
   - `atlas_governance_daily`, `atlas_governance_master`
   - `atlas_index_membership`
   - `atlas_v6_strategy_runs`, `atlas_v6_exclusions_log`, `atlas_v6_recommendations_daily`
   - `atlas_portfolio_policy`, `atlas_portfolio_proposed_change`
2. Drop 4 empty `atlas_*_quarantine` tables (verify nothing writes to them first)
3. Write `docs/v6/canonical-backend.md` — the locked v6 table inventory (~30 tables)
4. RLS decision pass — review 117 RLS-disabled tables; apply remediation OR scope anon role
5. Apply Supabase advisor's RLS remediation SQL (gated on user OK; not auto-applied)

**gstack skills:**
- `cso` (Chief Security Officer mode) — RLS + security audit, daily mode
- `to-issues` — turn audit findings into trackable issues
- Direct Supabase MCP `list_tables` + `execute_sql` for verification

**Quality gate:** `list_tables atlas` matches `canonical-backend.md` exactly. Zero "REVIEW-UNUSED" comments remaining. RLS decision documented in ADR.

---

### Phase B — Schema migrations (1 day, single PR)

**Goal:** Every column the mockups need, available in the schema.

**Steps:**
1. Single Alembic migration `097_v6_frontend_column_adds.py` containing:
   - ALTER `atlas_cell_definitions` ADD `display_name VARCHAR(64)`, `explain_text TEXT`
   - ALTER `atlas_sector_metrics_daily` ADD 8 cols (`rs_1w/1m/6m/12m`, `pct_above_ema20/200`, `pct_52wh`, `hhi`)
   - ALTER `atlas_macro_daily` ADD 6 cols (`dii_flow`, `us_10y_yield`, `dxy_actual` if usdinr-dxy ambiguity, `brent_inr`, `cpi_yoy`, `vix_9d`)
   - ALTER `atlas_etf_scorecard` ADD 3 cols (`premium_bps`, `te_60d`, `adv_20d_inr`)
   - CREATE TABLE `atlas_stock_macro_overlay_map` (sector + business_mix_tag → 3 macro series ids)
   - CREATE TABLE `atlas_etf_te_bands` (per-category TE config)
   - CREATE TABLE `atlas_etf_ter_components` (per-ETF per-quarter TER breakdown)
   - CREATE TABLE `atlas_etf_physical_disclosure` (per-ETF per-month physical holdings)
   - CREATE TABLE `atlas_stock_fundamentals_quarterly` (per-stock per-quarter fundamentals)
   - CREATE TABLE `de_fno_bhavcopy_daily` (partitioned)
   - CREATE TABLE `de_fno_oi_daily`
   - CREATE TABLE `de_fno_participant_oi_daily`
   - CREATE TABLE `atlas_stock_fno_metrics_daily`

2. Backfill `atlas_cell_definitions.display_name` from `cell_id` in same migration (21 rows)

**gstack skills:**
- `grill-with-docs` — lock terminology vs CONTEXT.md before migration (mostly already done)
- `superpowers:writing-plans` — write the migration upfront
- `plan-eng-review` — eng review pre-PR
- `superpowers:test-driven-development` — column-exists + column-type integration tests first
- `review` + `codex:codex review` pre-merge
- `ship` to land

**Quality gate:** All ALTER + CREATE statements execute against a clean copy. Alembic head consistent across `main` + dev. ADR for v6 schema completeness.

---

### Phase C — Writers, ingest, backfills (5-7 days, multiple PRs, parallelizable)

**Goal:** Every column populated. Every new metric computed. 10-year history where data permits.

**Workstream C1 — Existing-data backfills (fast, no new sources):**
- C1a: Backfill `atlas_mf_recommendation_daily` from `atlas_fund_scorecard` (~587 rows)
- C1b: Expand `atlas_etf_scorecard` writer from 34 leaders to all 126 ETFs
- C1c: Backfill `atlas_sector_metrics_daily` 8 new cols (5-year minimum, ideally 10-year) — extend `atlas/compute/sectors.py`

**Workstream C2 — Indian macro ingest (NSE / RBI / MOSPI / NSDL first):**
- C2a: RBI USD/INR daily ingest → `atlas_macro_daily.usdinr` (already populated, verify writer wired for ongoing)
- C2b: NSE G-Sec 10Y yield → `atlas_macro_daily.india_10y_yield` (column exists, 0 rows; needs writer)
- C2c: NSDL FII/DII daily → `atlas_macro_daily.fii_cash_equity_flow_cr` + new `dii_flow` col
- C2d: MOSPI CPI YoY monthly → `atlas_macro_daily.cpi_yoy` (new col)
- C2e: MCX Brent ₹ daily → `atlas_macro_daily.brent_inr` (new col)
- C2f: NSE India VIX9 daily → `atlas_macro_daily.vix_9d` (new col)

**Workstream C3 — Foreign macro ingest (FRED API — free official):**
- C3a: FRED DGS10 (US 10Y) → `atlas_macro_daily.us_10y_yield`
- C3b: FRED DTWEXBGS (DXY broad) → verify vs existing `atlas_macro_daily.dxy` (column populated; reconcile or replace)

**Workstream C4 — New compute jobs:**
- C4a: `atlas/macro/pairwise_correlation.py` (Nifty 500 rolling 60d corr) — daily run, 10-year backfill
- C4b: `atlas/macro/concentration.py` (top-N point contributions per index) — daily, 10-year backfill
- C4c: `atlas/compute/etfs.py` extensions for premium/TE-60d/ADV — daily, 10-year backfill
- C4d: `atlas/compute/regime.py` extensions for `pct_above_ema_100` + `% at 4-week high`

**Workstream C5 — Fundamentals ingest (NEW):**
- C5a: NSE XBRL quarterly filings parser → `atlas_stock_fundamentals_quarterly` (10-year backfill = 40 quarters × ~750 stocks)
- C5b: Screener.in supplemental scrape for ratios not in XBRL — rate-limited, cached locally

**Workstream C6 — F&O ingest (NEW):**
- C6a: NSE F&O bhavcopy daily CSV parser → `de_fno_bhavcopy_daily` (5-year backfill, NSE keeps 5y archive)
- C6b: NSE option chain endpoint → daily OI snapshots → `de_fno_oi_daily`
- C6c: NSE participant-wise OI → `de_fno_participant_oi_daily`
- C6d: `atlas/compute/fno_metrics.py` — PCR, IV, futures basis, OI build-up → `atlas_stock_fno_metrics_daily`

**gstack skills per workstream:**
- `grill-with-docs` per writer (lock semantics)
- `superpowers:writing-plans` per workstream
- `superpowers:test-driven-development` per writer — column-completeness ≥95% non-null on new daily writes
- `investigate` if any ingest source breaks (NSDL HTML structure change, NSE rate limit)
- `review` + `codex:codex review` per PR
- `simplify` to keep writer code under LOC budgets
- `verify` for end-to-end run on small date range before backfill

**Quality gate per workstream:**
- Column-completeness test: `COUNT(*) FILTER (WHERE col IS NOT NULL) ≥ 0.95 × COUNT(*) AS denom` on the backfill window
- Forward verification: 30 consecutive days of fresh writes (no gaps)
- Sample-row inspection: compare against source (NSE bhavcopy CSV, RBI bulletin PDF) for 5 random dates per year per writer

---

### Phase D — Cron orchestration (1 day + 7-day stability watch)

**Goal:** Every job scheduled, sequenced, monitored. No silent failures.

**Steps:**
1. Document the full nightly chain in `docs/v6/nightly-orchestration.md`:
   - **18:00 IST** — EOD trigger
   - **18:05** — JIP ingest (de_equity_ohlcv refresh, de_index_prices refresh, NSE bhavcopy F&O)
   - **18:30** — Atlas compute stage 1 (scorecard_writer, stock_states, sector_states, market_regime classifier)
   - **19:00** — Macro ingest (NSDL FII/DII, FRED, MCX)
   - **19:15** — Compute stage 2 (pairwise corr, concentration, F&O metrics, ETF computes)
   - **19:30** — Conviction + signal_calls + ledger update
   - **19:45** — MV refresh chain (pg_cron)
   - **20:00** — Daily brief generation + drift detector tick
   - **20:30** — Daily QA audit (row count + freshness check on all key tables)
2. EC2 crontab entries reviewed + reconciled with repo scripts (resolve the systemd vs crontab divergence)
3. pg_cron refresh chain defined: writers → MVs → audit log table
4. Weekly cron (Sundays):
   - Walk-forward IC recompute on rolling window
   - Drift detector tick
   - Pairwise correlation full recompute (cache invalidation)
5. Monthly cron (1st of month):
   - Quartile rank refresh on funds
   - Concentration baseline refresh
   - Fundamentals XBRL pull for last quarter (if quarter ended)
6. PagerDuty (or alternative) integration on cron failure
7. **7-day stability watch** — green-run for 7 consecutive days before greenlight to Phase E

**gstack skills:**
- `setup-deploy` — systemd/cron setup on EC2
- `verify` — end-to-end manual trigger of nightly chain
- `canary` — post-deploy monitoring
- `health` — daily quality dashboard
- `monitor` — watch background jobs

**Quality gate:** All jobs run automatically for 7 days without any manual intervention. Audit log shows all rows fresh. No PagerDuty alerts.

---

### Phase E — MV build (5-7 days, PR-per-page or PR-per-MV)

**Goal:** 14 materialized views, each backing a v6 page.

**Order (build from simplest to most complex):**
- Page 08 (1 MV) — simplest, mostly read of existing tables
- Page 03 (2 MVs) — cleanest data
- Page 01 (1 MV) — wide single row, JSONB nested sections
- Page 02 (1 MV) — depends on Phase C macro ingest
- Page 04 (5 MVs) — per existing design doc
- Page 05 (3 MVs) — per existing design doc
- Page 06 (2 MVs) — per existing design doc
- Page 07 (2 MVs) — per existing design doc (most complex)

**Per MV:**
1. Write spec (`docs/superpowers/specs/2026-05-26-v6-<page>-mvs-design.md`) — 3 still pending for Pages 01/02/03
2. Implement migration with `CREATE MATERIALIZED VIEW` + indexes
3. Test row count + sample row + refresh latency
4. Wire into pg_cron refresh chain
5. PR with TDD test, codex review, /review pre-merge

**gstack skills per MV:**
- `grill-with-docs` per MV spec (lock semantics)
- `superpowers:writing-plans` per spec
- `plan-eng-review` per MV
- `superpowers:test-driven-development` per MV
- `review` + `codex:codex review` per PR
- `simplify` if SQL grows over budget
- `verify` for end-to-end MV refresh + query

**Quality gate per MV:**
- Row count matches expected grain
- Sample query returns mockup-expected shape
- Refresh latency < 30s
- Integration test: MV row joins back to source data without contradiction
- All 14 MVs refresh successfully in nightly chain

---

### Phase F — Backend QA gauntlet (2-3 days)

**Goal:** "Cannot ship the frontend" sign-off gate.

**Checks:**
1. Per-MV row count + freshness audit ≥ 99% trading days populated last 90 days
2. Per-page sample query returns NO NULLs in load-bearing fields
3. Per-page latency budget: full data fetch < 200ms cold, < 50ms warm
4. Cross-MV consistency:
   - Composite score for stock X same in `mv_stock_list_v6` + `mv_stock_deepdive`
   - Regime state same in `mv_market_regime_landing` + `mv_india_pulse`
   - Sector verdict same in `mv_sector_cards` + `mv_sector_deepdive`
5. Closed-loop engine still runs (atlas_signal_ic, atlas_cts_*, atlas_signal_weights_live_perf populating nightly)
6. Historical depth verification: every derived metric in MVs has ≥5y backfill
7. Fundamentals + F&O data flowing for at least the latest quarter / last 30 days
8. Security: RLS decision applied; no auth bypass; service-role-only writes
9. **7-day stability watch** — second one, with full chain active

**gstack skills:**
- `health` — full code quality dashboard
- `qa` — systematic backend QA, full mode
- `cso` — final security pass before launch (comprehensive mode)
- `verify` — hands-on functional verification per page
- `benchmark` — performance baseline against the live MV queries

**Quality gate:** `docs/v6/backend-readiness-check.md` checklist all green. CEO + Engineering sign-off documented in ADR. **No frontend code starts before this gate.**

---

### Phase G — Frontend sprint (after Phase F sign-off)

**Goal:** Pure UI plug-in. No backend surprises.

**Per page:**
1. New route directory in `frontend/src/app/v6/<page>`
2. Query module in `frontend/src/lib/queries/v6/<page>.ts` (one SELECT per MV)
3. Compose mockup using existing `/components/v6/*` atoms
4. Wire data to Recharts / SVG
5. Per-page `/design-review` pass
6. Per-page `/qa`

**gstack skills:**
- `frontend-design:frontend-design` per page
- `design-review` per page
- `qa` per page (Quick or Standard mode)
- `verify` per page (real browser)

**Quality gate per page:** Design-review pass + QA pass + every mockup field renders real data (no `—` placeholders on load-bearing fields). Page ships individually as it passes.

---

## Master sequence — per-session execution order

| Session | Phase | Deliverable | Skill cadence |
|---|---|---|---|
| 1 | A | dead-code burn + RLS decision + canonical-backend.md | `cso` + `to-issues` |
| 2 | B | single migration PR with all column adds + new tables | `grill-with-docs` + `plan-eng-review` + `tdd` + `review` + `codex` + `ship` |
| 3-5 | C1+C2 | existing-data backfills + Indian macro ingest | per-writer `grill` + `tdd` + `review` per PR; parallelizable across sessions |
| 6-7 | C3+C4 | FRED + new compute jobs | same |
| 8-9 | C5+C6 | fundamentals + F&O ingest | same |
| 10 | D | cron orchestration + 7-day watch start | `setup-deploy` + `canary` + `health` + `monitor` |
| 11-15 | E | 14 MV builds | `grill` + `tdd` + `review` per MV |
| 16-17 | F | backend QA gauntlet + 7-day stability watch | `health` + `qa` + `cso` + `verify` + `benchmark` |
| 18+ | G | per-page frontend sprint | `frontend-design` + `design-review` + `qa` per page |

**Total estimate: 18-25 working sessions** (some sessions span 2-4 hours; parallelizable workstreams in Phase C compress this).

---

## Hard rules (no negotiation)

1. **Every derived metric gets a 5-year minimum backfill, 10-year ideal.** No "we'll backfill later." Backfill is part of the same PR as the writer.
2. **NSE/RBI/MOSPI/NSDL/FRED are primary sources.** yFinance is last resort only when no free official source exists.
3. **Every column added in Phase B has a populated writer in Phase C before the migration is considered done.** No empty columns shipped to main.
4. **Every cron job has a PagerDuty alert on failure.** Silent failures are not acceptable.
5. **No frontend line until Phase F sign-off.** Quality gate is binding.
6. **7-day stability watch is non-negotiable** — once at end of Phase D, once at end of Phase F.
7. **No new ingest source goes live without a 30-day forward verification window.**

---

## Open decisions (will be resolved during execution; no blockers)

- Composite score scaling for Page 05 (decided: lift from `atlas_stock_conviction_daily.conviction_score`)
- Stock-specific macro overlay deterministic mapping (3 series per stock; encoded in `atlas_stock_macro_overlay_map`)
- ETF TE band thresholds per category (per CONTEXT.md ETF vocabulary)
- LLM-generated copy vs templated copy for editorial bits (decide per-page in Phase E)
- Brinson attribution for Page 06: include or defer to v6.1

---

## Recovery / blast-radius safeguards

- All Phase A drops via `DROP TABLE IF EXISTS atlas.<name> CASCADE` only after sign-off
- All Phase B ALTER + CREATE in single migration with `op.downgrade()` defined
- All Phase C writers backed by tests with deterministic fixtures
- All ingest sources cached locally (raw response saved before parsing) so a source change doesn't lose the input
- All MVs are `REFRESH MATERIALIZED VIEW CONCURRENTLY` to avoid downtime on refresh

---

## Files this plan replaces / makes redundant

- The "TODO" entries in `docs/TODOS.md` for v6 backend
- Scattered notes in `docs/superpowers/specs/` about backend buildout
- Implicit assumptions in CEO/eng plans about what's done vs not

This document supersedes any prior backend-buildout sketches. Update it inline as decisions get made during execution.

---

**Last reviewed:** 2026-05-26
**Next action:** Phase A — Session 1
