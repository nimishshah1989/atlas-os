# Atlas Cleanup Loop — Live State

**Mandate:** FM's 7-goal pristine-ification of Atlas, run as a goal-sync loop.
**Branch:** `release/v4-consolidation-live` · **Topology:** THIS box is prod (pm2 `atlas-frontend-v3` :3004 + live Supabase DB).
**Autonomy:** drive hard; pause only at 3 hard gates → (1) refresh-schedule sign-off, (2) destructive action (DROP schema/table/branch, force-push), (3) prod deploy.
**Started:** 2026-07-01 · **Last updated:** 2026-07-02 (G1 gate = 0 ✅)

> Loop mechanic, per goal: **inventory → write done-when as a runnable check → build → verify on REAL output → advance only when green (re-loop on red).** No goal is marked done without evidence (rule #0: gates assert on real produced output, never synthetic).

## Locked decisions (2026-07-01)
| # | Decision |
|---|---|
| D1 | Single core schema = **`atlas_foundation`** (rename `foundation_staging`→`atlas_foundation` as the FINAL step, after everything is consolidated in). |
| D2 | Repo-hygiene tools = **ponytail** (github.com/DietrichGebert/ponytail) + **headroom** (github.com/headroomlabs-ai/headroom). Fetch + learn run-protocol before use. |
| D3 | Autonomy = drive hard; pause only at the 3 hard gates above. |
| D4 | This box IS prod → every DB drop / force-push / deploy is a hard gate. |
| D5 | **Retire JIP entirely** → Atlas-owned ingestion (Kite=OHLCV; AMFI=NAV; Morningstar=holdings; BSE/NSE=filings; screener=fundamentals; FRED/NSE=macro), one orchestrator. |
| D6 | **Remove `mfwatch`** product (schema + pg_cron job 47 + Supabase edge fn). |
| D7 | **Drop `us_atlas` + `global_atlas`** schemas + their crons (etf_global/stooq/us_daily) + orphan US/global frontend. |
| D8 | **Kill retired IC/conviction/strategy/CTS/decisions cluster** — stop `run_atlas_intelligence_nightly.sh`; delete 56 orphan query files + 6 orphan + 3 non-core endpoints; drop atlas.* strategy/cts/conviction/decisions/signal tables. |
| D9 | Drop manifest APPROVED; execute only after migrate → green nightly → backup → show final list. |
| D10 | **Prices = Kite ONLY (single source)** — stocks + ETFs + indices. Purge `NSE_IND_CLOSE_ALL` (bhavcopy) + `KITE_HISTORICAL`-stale + seed rows; guard bhavcopy off `ohlcv_*`/`index_prices`. No multi-source. (Exception: 3 broad indices Kite lacks — Smallcap250/Microcap250/TotalMarket — stay bhavcopy, one-source-per-instrument preserved.) |
| D11 | **All calculations as-of last COMPLETE EOD; current day = live-only** (+ some live data points). Scored layer never ingests an in-session partial candle. Impl: `_db.eod_cutoff()` (today if ≥16:00 IST else yesterday) — compute_all + build_index_metrics anchor to it; daily orchestrator runs post-close so today naturally = EOD. Intraday job handles current-day live (indices/sector). |
| — | Logged: gstack-decision-log `ea5057b1` (mandate), `e98bc6d9` (D3-D6), `44608306` (D7-D9). |

## Goal tracker
| Goal | Definition of done (runnable gate) | Status | Evidence |
|---|---|---|---|
| **G1** single schema | Inventory of every prod table tagged raw/derived/materialized + producer + consumers; query proves 0 live-path deps outside `atlas_foundation`. atlas.*/public.de_*/us_atlas/global_atlas migrated or dropped. | 🔨 **GATE = 0 ✅** (`schema_gate.py` PASS, 2026-07-02); rename+DROP FM-gated | 165→0: FE orphan-closure deleted (475 files, build green); all backend + health reads repointed to fs. Commits bb91e305 / 8217ba2a / 76015018. |
| **G2** cron/refresh | Canonical orchestrator per cadence; **FM-approved** refresh matrix; 1 script/ingest; sources+auth documented; idempotent; freshness guard fails loud. | ⏳ not started | — |
| **G3** single-source FE | page→query→table map; 0 scoring/roll-up math in FE (TS or embedded SQL); no hardcoding; no orphan/exposed endpoints. | ⏳ not started | — |
| **G4** clean data model | No double-calc; no column derived twice; raw→1 derivation→1 serving layer; documented+versioned; surfaced in admin methodology tab. | ⏳ not started | — |
| **G5** zero hardcoding | grep proves 0 numeric scoring constants in code; every weight/threshold/toggle in thresholds table, editable from /thresholds page. | ⏳ not started | — |
| **G6** freshness+provenance | Last-refresh date on every page; every table documented w/ source+refresh; one freshness registry. | ⏳ not started | — |
| **G7** pristine repo | ponytail+headroom clean; full review (arch/bug/data/CI); branches/dead-code/stale-tables pruned; only core product remains. | ⏳ not started | Tools identified: ponytail = CC plugin (`/ponytail-audit`/`-debt`/`-review`, code minimalism); headroom = agent context-compression (`pip install headroom-ai`, `headroom wrap claude`). Both install into agent/runtime → FM hands-on step (gate) at G7. |

Status legend: ⏳ not started · 🔨 in progress · 🧪 built, verifying · ✅ done (green gate) · ⛔ blocked (gate)

## Progress log (execution)
- **2026-07-02 (session 2c) — RENAME → atlas_foundation + CRON cleaned + dead-code purge (FM directive).**
  - **Schema RENAMED** `foundation_staging`→`atlas_foundation` (commit 32a56b72): atomic `ALTER SCHEMA` (73 tables, no cross-schema deps) + full replace across 124 code+test files (0 refs left); rebuilt + redeployed (board live HTTP 200); gate still 0. **Gotcha:** DB rename MUST precede the FE build (static prerender queries the DB at build time — first build failed on /etfs until the DB matched). FM re-confirmed `atlas_foundation` (not `atlas_staging`).
  - **CRON cleaned + orchestrator completed** (commit 925aa7dd): found + fixed feed gaps — added `ingest_nav` (AMFI, daily; NAV was frozen 06-30, verified→07-01) + `ingest_bulk_deals` (was 06-19) to `atlas_daily.sh`. Installed a clean 6-job crontab (checked in at `scripts/ops/crontab.txt`): kite_autologin, atlas_daily, atlas_weekly, atlas_sunday_qa, auto-deploy (dormant off-main), :3004 watchdog (was pointed at dead :3002/non-existent app). **Retired the whole legacy tangle** — JIP $WRAPPER (eod/macro/filings/amfi/holdings), nightly_compute, run_atlas_nightly (M2-M7), run_atlas_intelligence_nightly (6 failing CTS/validator/strategy steps), amfi_etf_inav + atlas_health_check (write dead atlas.*), agent3. Old crontab backed up to `/home/ubuntu/logs/crontab_backup_*`.
  - **Dead-code purge DONE (~758 files removed this session).** Backend import-reachability (roots = live orchestrator entrypoints) + a per-file classifier → **235 SAFE_DELETE / 18 KEEP** of the 253 dead .py. Deleted the retired M1-M7 / intelligence / IC / conviction / CTS / strategy / macro-ingest / us-global / Stooq / TradingView / old-FastAPI / legacy-universe-validation-health surface + 3 dead .sh + 15 leftover artifacts (API systemd units, macro data, research/verify SQL) + `scripts/loops/` (17 docs) + 13 broken FE tests. **KEPT 18:** live-table maintenance producers not-yet-croned (build_universe, assign_sectors, build_sector_rrg, backfill_sector_rs, fetch_marketcap, populate_etf_isin, ingest_xbrl), admin/verify utils (recompute_composite_fast [/admin/thresholds], reconcile_portal, verify_fund_rank, calibrate_sectors, decile_core, fund/sector_view), dev-enforcement (3 hooks + CI ratchet). Disabled the dead `atlas-internal-recompute.service`. **Backend 308→79 live .py.** VERIFIED: every live orchestrator module imports; gate=0; `validate_lenses --check A` PASS on real 07-01 data. Commits 73fc760e / bde70533 / a763a314 / 813714d0. **NOTE (G4 follow-up):** the 7 not-yet-croned KEEP producers reveal refresh gaps — universe/sector membership, sector-RRG mv, sector-RS, marketcap, ETF-ISIN, XBRL fundamentals — wire into weekly. **NOTE (G6):** health/pipeline_runs/validator tables in fs have no live writer (their old writers were dead atlas.* scripts) → /admin data-status shows the cloned snapshot only.
- **2026-07-02 (session 2b) — orchestrator validated manually → bugs found + 07-01 board incident (Kite-only fix).** Ran `atlas_daily.sh` by hand to validate the G1 repoints end-to-end. The compute chain ran green (compute_all, build_index_metrics, lens_daily 498/0-skip, rollup, fund, breadth, **regime [fs-native rewrite] ok**, freshness PASS) — BUT it exposed real pre-existing bugs + an incomplete-EOD:
  - **07-01 stock OHLCV was only 10/2287 ingested** (never fully Kite-ingested during setup) → lens scored 07-01 off near-empty raw → composite≈0 for 496 → and (via the gate-bypass bug) it DEPLOYED that blank board.
  - **Fixed the board FROM KITE (not public — FM correction):** `ingest_kite.py --asset stock` (Kite historical) pulled 07-01 for 487/498 active (11 throttle-blocked); recomputed 07-01 (technical→lens→rollup→breadth→regime) → composite>0 for **487/498, avg 53.5** (matches 06-30's 52.9), regime 07-01=Risk-On; redeployed (fetch-cache flush + pm2 reload). The 11 + full raw universe complete tonight via the no-throttle `quote()` EOD ingest. **NO public.* used; the earlier public gap-fill idea was stopped.**
  - **Orchestrator/gate bugs fixed (commit 621aa0bf):** (1) `atlas_daily.sh` called `validate_lenses` bare but it requires `--check A|B` (rc=2 every run) AND ran it via `step()` which always returns 0 so `|| GATE_OK=0` never fired → a failed gate could deploy; now runs both checks directly, real exit drives GATE_OK. (2) `freshness_guard` only checked max(date) → an incomplete ingest passed; added a **completeness check** (EOD row-count ≥50% of prior session for per-instrument tables) — would have caught 10/2287. (3) `validate_lenses` check_B `s.composite` → fs.sector_lens_daily has no composite col (SEC-repoint exposed); check `s.technical` 0-100 instead.
  - **Flagged (not gamed):** check_B's ETF/index "lens coverage" assertions are architecturally stale (lens journal is stocks-only; ETFs live in `atlas_etf_scorecard` [34 scored / 126 universe], indices are benchmarks) → needs methodology reconcile before wiring `--check B` as a hard deploy gate.
- **2026-07-02 (session 2) — 🎯 G1 GATE = 0 (PASS ✅), 165→0.** Every live-path DB reference now inside `foundation_staging`. Verified on REAL output (scorer reconciliation test green; delivery + regime reconcile). Three commits:
  - **bb91e305 — FE orphan-closure delete (475 files).** An import-reachability graph rooted at all 41 Next App-Router entrypoints proved 344 src + 131 tests unreachable (retired v6 signal-board + pre-v6 component trees + stale root queries). Deleted; `npm run build` green, all 17 routes intact. NOTE: the runbook's orphan list was correct; the earlier Explore-agent "LIVE" verdicts were name-collisions (`v6/stocks.ts` ≠ live `stock_lens.ts`) — the reachability graph is the source of truth. 13 "mixed" tests (import both orphan+live) left for G7 triage.
  - **8217ba2a — backend repoints (48→0).** adapters (policy_registry + `instrument_master.sector/industry` [NEW col, seeded from atlas]), calibration, indices, ingest_{bhavcopy,kite,screener,fund_master}, build_index_metrics, validate_lenses; harness dropped the obsolete legacy "live" profile. `atlas_kite_session` migrated into fs (live token copied; retrieval verified). **Delivery decoupled:** new `fs.delivery_raw` (2.28M rows copied from public.de_equity_ohlcv), fetch/backfill read fs, fixed the orchestrator's no-arg `fetch_delivery` bug (incremental default window); delivery_daily rebuilt to 06-30 from the fs path. **regime.py rewritten to native fs loaders** (technical_daily + ohlcv_stock + instrument_master.is_active; strength-breadth states derived natively — weinstein=above-200EMA, rs_state from 50/200EMA+3m RS) — reconciled vs atlas M3: `regime_state`/`deployment_multiplier` match on every real-breadth day, `nifty500_close`/VIX exact (the 06-15 & 07-01 diffs are atlas NaN-gap / technical_daily 1-day-stale, both self-healing).
  - **76015018 — health.ts.** 3 observability tables cloned into fs (atlas_pipeline_runs 218 / atlas_health_daily 945 / atlas_validator_results 122) + repointed.
  - **DB migrations applied LIVE:** `instrument_master.industry`, `foundation_staging.{delivery_raw, atlas_kite_session, atlas_pipeline_runs, atlas_health_daily, atlas_validator_results}`.
  - **LEFT for G1-finish (FM-gated destructive):** rename `foundation_staging`→`atlas_foundation` + DROP atlas/public/us_atlas/global_atlas/mfwatch — only after green nightly + DB backup + final drop-list shown.
  - **⚠️ Landmine (G6):** `health.ts getJipFreshness` still reads `public.de_*` via DYNAMIC refs (uncaught by the gate) → repoint to the fs freshness registry BEFORE the public DROP. Flagged in-code.
- **2026-07-02 — G2 AUTOMATION BUILT + WIRED (crons).** `kite_autologin` (08:50 IST wd, TOTP headless — LOGIN SOLVED), `atlas_daily.sh` (16:00 IST wd: ensure-token→ingest_eod[batched quote, no throttle]→feeds→compute_all→index_metrics→lens→rollup_sectors→fund_rank→breadth→regime→validate_lenses+freshness_guard gates→conditional deploy→Telegram alert), `atlas_weekly.sh` (Sat), `atlas_sunday_qa.sh`+`qa_weekly.py` (Sun health audit: freshness+silent-zero+outlier→alert), `freshness_guard.py` (fail-loud). Commits 25dcba79/36d4b73e/a7d02148/7743fa59/6f45b7e3. **delivery_daily FIXED** (was 06-19; raw delivery_pct was fresh 06-30 in public.de_equity_ohlcv but the derived table's builder hadn't run → rebuilt to 06-30). LEFT for G2: (1) validate atlas_daily on tonight's real run; (2) retire OLD crons (JIP/M2-M5/intelligence/us-global/pg_cron) AFTER validation; (3) TELEGRAM_BOT_TOKEN/CHAT_ID not in .env → alerts silent until FM sets them; (4) delivery_daily still reads public.de_equity_ohlcv (JIP) → decouple in G1; (5) env codify talib/pyotp. 07-01 stock backfill loop still grinding (Kite historical cooldown).
- **2026-07-01 — P-Kite-stock/etf + bhavcopy guard DONE ✅.** ETFs re-pulled from Kite (311, single-source). Stocks: unified `KITE_HISTORICAL`→`KITE`, incremental Kite pull → `ohlcv_stock` 99.9% KITE (6.01M rows / 2093 stocks, EOD-fresh). `ingest_bhavcopy.py` GUARDED (D10): `write_stocks()` raises unless `allow=True`; `ingest_day` no longer writes stock OHLCV; `write_indices` restricted to `KITE_LESS_INDICES` (Smallcap250/Microcap250/TotalMarket — the only curated indices Kite lacks). **Residual (G4):** 282 stocks have no `kite_token` in instrument_master → 3583 bhavcopy rows remain (their only source); + 1089 seed rows. Add tokens / resolve later. Kite token failed transiently mid-first-pull (recovered on retry) — orchestrator needs retry/abort-loud on token errors.
- **2026-07-01 — EOD anchor DONE ✅ (commit c73e3f98).** `_db.eod_cutoff()`; compute_all + build_index_metrics anchor to last complete EOD; purged partial 07-01 from calc tables. D11.
- **2026-07-01 — P-Kite-index DONE ✅ Kite = single index source; 06-25 sector staleness FIXED.** Rewrote `ingest_kite.py` → unified multi-asset, `instrument_master`-driven (drops `public.de_instrument` dep + NSE-segment remap); routes stock→ohlcv_stock, etf→ohlcv_etf, index→index_prices; incremental per-instrument floor; source tag `KITE`. Re-pulled all 136 Kite indices (06-15→07-01), relabeled old `KITE_HISTORICAL`→`KITE`, purged duplicate non-KITE rows. Result: **every index single-source (0 multi-source); all 31 sector primaries fresh to 07-01** (was 14 fresh + 16 frozen 06-25). Rebuilt index metrics. **Kite lacks 3 broad indices** (Smallcap250/Microcap250/TotalMarket) → they stay bhavcopy (Kite doesn't carry them; documented exception, market_pulse needs them). LEFT: migrate stocks+ETFs to Kite + purge their bhavcopy; delete ~113 noise bhavcopy indices from raw index_prices (G4); wire ingest_kite+build_index_metrics into daily orchestrator (G2). NOTE: frontend cached → sector-RS fix shows after next deploy (batch with the regime/macro refresh so all of Market Pulse goes fresh together).
- **2026-07-01 — P1b DONE ✅ index_code truncation fixed + native builder self-heals.** Widened `foundation_staging.atlas_index_metrics_daily.index_code` varchar(32→64) (source `index_prices` has codes to 54 chars, 252 indices); `build_index_metrics.py` now idempotently ensures the width. RAN it → index metrics fresh **06-25→06-30**, 249 indices written, 54-char codes stored (sector-RS lag fixed). **Footgun found:** `build_index_metrics.py` imports `from scripts.foundation import _db` (needs `python -m scripts.foundation.build_index_metrics`, NOT direct) while `compute_all.py` uses bare `import _db`; `scripts/foundation/` has no `__init__.py`. Inconsistent invocation is why it silently never ran in the nightly → G2 orchestrator must standardize; G7 hygiene.
- **2026-07-01 — P1a DONE ✅ `compute_all.py` incremental by date.** Replaced status='done' skip with per-instrument date-staleness (`tech_max_dates()` vs `_source_max_dates()`); `compute_one` writes only the tail beyond the floor (EMAs still derived from full history). `--redo`/`--full` = full rebuild. Verified on REAL data: incremental targets on current data = 135 (all indices genuinely behind; stocks/ETFs current) vs full = 2540; lowering a floor 5d makes an instrument reappear. ruff clean. Fixes original problem #2 (a new day no longer no-ops). Also surfaced a real gap: 135 index technicals lag `index_prices` — the incremental daily run now closes this automatically.

## Findings log
- **2026-07-01 — ⭐ROOT CAUSE of the whole 06-25 staleness cliff: Kite ingestion died 06-25.** `index_prices` has 3 sources: `KITE_HISTORICAL` (136 idx, frozen **06-25** — Kite login broke, stale TOTP per FM brief), `NSE_IND_CLOSE_ALL` (160 idx, bhavcopy, fresh 06-30), `seed` (2). The 16 stale sector indices (Defence/Digital/EV/Capital Markets/Tourism/… — newer thematic ones) are Kite-only → froze when Kite died. The 14 fresh (Auto/Bank/IT/…) are also in bhavcopy so stayed fresh. Same 06-25 cliff = Market Pulse regime/macro. **FM directive D10: Kite is the SINGLE price source** (no bhavcopy remap, no multi-source). **Valid Kite token EXISTS now** (login 07-01 05:54 UTC, valid to 18:29 UTC) → can re-pull immediately.
  - **Kite-only build (top G2 task):** `ingest_kite.py` is stock-only (writes `ohlcv_stock`, NSE-equity segment, needs `--symbols`, reads `public.de_instrument`). Must: (1) extend to indices (INDICES segment tokens) + ETFs; (2) default to full universe from `instrument_master` (drop `public.de_instrument` dep); (3) re-pull stocks+ETFs+indices to latest; (4) PURGE `NSE_IND_CLOSE_ALL` + stale `KITE_HISTORICAL` + seed rows from `index_prices`/`ohlcv_*`; (5) guard `ingest_bhavcopy.py` off `ohlcv_*`/`index_prices`; (6) dedup index codes (Kite short-code is canonical; sector_master already uses them).
- **2026-07-01 — Market Pulse "26 June" staleness (root cause).** Headline "as of" = `regime.date` ([MarketPulseV4.tsx:117]) from `foundation_staging.atlas_market_regime_daily`, frozen at 2026-06-25. Raw+lens tables fresh to 06-30; but M3-derived surfaces (regime/macro/index_metrics/sector_lens) in `foundation_staging` froze at 06-25 because the **atlas.*→foundation_staging mirror + manual `rollup_sectors.py` stopped running**. Same tables in legacy `atlas` schema are fresh to 06-30. → Fix under G1+G2 as an early visible win.

## EXECUTION PLAN (all gates cleared 2026-07-01; drive-hard) — decisions D5-D9
Pause only at: prod deploy · force-push · the actual DROP (after migrate+green+backup, final list shown).

**P1 — Backend single-source build (G3/G4/G1-migrate):**
- P1a compute_all.py incremental-by-date · P1b build_index_metrics varchar(32→64) widen
- P1c materialize deciles+leadership+cap_cohort into atlas_lens_scores_daily · P1d sector composite into sector_lens_daily
- P1e build_etf_rank_history.py → etf_rank_daily (NEW) · P1f fund <12m gate + fund metrics into fund_rank_daily
- P1g **native v4 builders replace M2/M3** for FE-read derived (regime/macro/stock_metrics/scorecards) — D7 · reconcile before cutover
- P1h repoint 3 live-lens atlas.* reads (adapters/calibration/policy)→fs · P1i wire pipeline.py + native builders into nightly
**P2 — Frontend pure-reader (G3):** kill fundScore/sectorScore + CTE math → read precomputed cols · delete 56 orphan files + 9 endpoints + signal-call panels (D8) · repoint public.* + health.ts consumers→fs
**P3 — Orchestrators/sources (G2):** ingest_kite full-universe default + bhavcopy guard · atlas_daily/weekly/sunday_qa/intraday.sh · Telegram login (creds+/api/kite/login) · freshness guard · env codify (talib/pyotp) · remove JIP/intelligence/us/global crons
**P4 — Config plane (G5):** grep hardcoded constants → atlas_thresholds; /admin/thresholds covers all
**P5 — Freshness/provenance (G6):** freshness registry + "as of" every page + table docs in admin methodology tab
**P6 — Migrate+rename+drop (G1 finish):** copy MIGRATE history→fs · green nightly · backup · rename foundation_staging→atlas_foundation · **DROP** (final list shown; D9)
**P7 — Repo hygiene (G7):** delete stale copies (atlas-compute/prod-src/frontend-v2) · ponytail/headroom (FM hands-on) · full review workflow · prune branches · CI

## Census results + resolutions (2026-07-01) — see table-census.md
- **Counts:** KEEP 39 / MIGRATE 34 / DROP 71 / DECIDE 6. Full manifest = [table-census.md](table-census.md).
- **DECIDE resolved by me (no FM needed):** `technical_stock` → DROP (old PoC compute.py, superseded by technical_daily, no live reader); `atlas_cell_walkforward_runs` → DROP (no reader); `de_mf_lifecycle` → DROP (no reader); `sector_index_returns` → KEEP + wire `backfill_sector_rs.py`/fold into build_index_metrics (impl detail); `instrument_master` → KEEP + wire `build_universe.py`/`assign_sectors.py` into nightly.
- **DECIDE for FM:** `atlas_signal_calls`/`atlas_etf_signal_calls` — "signal calls" board is live-referenced (TodayClient, stock-detail SignalCallHistoryTable, recent_signal_calls.ts) but producer (M5) retired → keep feature (build native producer) or retire (drop tables+queries)?
- **Strategic fork for FM (G4):** M2/M3-derived tables the live FE reads (stock_metrics/regime/macro/scorecard/fund+etf scorecard) → REPOINT old M2/M3 producers to write fs, OR KILL M2/M3 and give each surface a native v4 producer (cleaner, more work). Recommend kill-and-native.
- **Live-dir CONFIRMED:** live code = `/home/ubuntu/atlas-os` (nightly REPO=atlas-os; pm2 atlas-frontend-v3 cwd=atlas-os/frontend). `atlas-compute`(non-git stale, log dir only), `atlas-prod-src`(deploy-main checkout), `atlas-frontend-v2` = G7 cleanup targets (multiple stale copies on box).
- **Live nightly is STILL old M2–M5 + JIP** (run_atlas_nightly.sh 23:30); v4 lens pipeline NOT wired in → 06-30 needed manual recompute (= MIGRATE #1).
- **Kite Telegram login ALREADY BUILT** (kite_daily_notify.py + atlas/intraday/notify+auth); needs TELEGRAM creds + /api/kite/login endpoint wired (G2).

## G1 inventory — schema stock (2026-07-01)
| Schema | Objects | Size | Role |
|---|---|---|---|
| `atlas` | 165 | 10.8 GB | LEGACY — retired methodology (strategy/cts/conviction/decisions/agents/portfolio) + still-written M2/M3 mirror sources + `mv_*` views (pg_cron refreshes these). Mostly droppable. |
| `public` | 106 | — | LEGACY raw `de_*` + more. Migrate live bits → drop. |
| `foundation_staging` | 68 | 11.05 GB | LIVE target (→ `atlas_foundation`). Carries mirror-cruft (retired `atlas_*_scorecard/_states/_metrics/conviction/signal`) alongside the real live tables. |
| `us_atlas` | 16 | — | Separate US-market system. FM decision: keep-separate vs remove. |
| `global_atlas` | 11 | — | Separate global-ETF system. FM decision: keep-separate vs remove. |
| `mfwatch` | 18 | — | SEPARATE PRODUCT (own config/portfolio/alerts/news + edge-function cron 16:00). FM decision: leave vs remove. |

## Cron reality (2026-07-01) — THREE systems, must consolidate (G2)
- **pg_cron (in-DB):** refreshes `atlas.mv_*` matviews (regime/rotation/rs_leaders/breakouts/deterioration/conviction) + big `mv_refresh_v6_all` (21:45, refreshes `atlas.mv_*_v6` landing/sector/stock/fund/etf views) + intraday MV every 15min (mkt hrs) + `mfwatch_daily` edge fn. NOTE frontend reads `foundation_staging.mv_*` but pg_cron refreshes `atlas.mv_*` → mismatch/staleness.
- **JIP OS crontab** (`/home/ubuntu/jip-data-engine/scripts/cron/jip_trigger.sh`): **`eod` (OHLCV!) 13:03**, macro_daily, filings_daily, bse_filings, morningstar_weekly, fundamentals_weekly, holdings_monthly, bse_ownership_weekly, etf_global, amfi_late, agent3. **⇒ OHLCV source today is JIP, NOT Kite.**
- **atlas-os OS crons:** `nightly_compute` 18:00, `run_atlas_nightly.sh` 19:00, `run_atlas_intelligence_nightly.sh` 21:00 (**still runs RETIRED conviction/IC methodology → atlas.atlas_signal_***), amfi_nav_backfill, ingest_mf_holdings (weekly Sun 12:00), amfi_etf_inav, atlas_health_check 22:00, auto-deploy + frontend healthcheck (*/5).
- **Kite `ingest_kite.py` is NOT scheduled anywhere.**

## FM gate — RESOLVED 2026-07-01 (see D5-D8 above)
1. ✅ OHLCV+all sources → **Atlas-owned, JIP retired** (Kite prices + Atlas scripts).
2. ✅ mfwatch → **remove entirely**.
3. ✅ us_atlas/global_atlas → **drop both** + crons + code.
4. ✅ retired IC cron/methodology → **kill it all**.
5. ⏭ mv_* one-schema/one-refresh-path → handled during migration into `atlas_foundation`.

**Next: exhaustive per-table census workflow** → precise KEEP/MIGRATE/DROP manifest (drops are gated).

## G1 — frontend reachability (2026-07-01)
- **Live routes (14):** 5 product (/, stocks, etfs, funds, sectors) + details + methodology + **/admin/thresholds** (G5 control plane, already exists) + **/admin/data-status** (G6 freshness RAG, already exists) + health + login.
- **Query files: 29 live / 56 ORPHAN** (of 114). Orphans = dead code for removed routes → deletion candidates (G3/G7).
- **Live cross-schema deps = essentially none:** all product queries read `foundation_staging.*` only. Sole exception = `health.ts` (observability) reads `atlas.atlas_pipeline_runs/validator_results/health_daily` + `public.*` (JIP freshness) — repoint when atlas/public drop.
- **API routes: 8 live / 6 orphan.** 3 live but non-core reference atlas.*: `/api/cts/sectors` (atlas_cts_sector_pivot_daily), `/api/policy` (atlas_portfolio_policy), `/api/portfolio/create` (strategy_fm_custom_portfolios) → delete (no v4 UI) or migrate.
- **Freshness stamp mechanism exists** (fmtDate(row.date) → "as of" on Market Pulse); G6 = extend to every page + centralize.

## Freshness snapshot (2026-07-01, read-only sweep)
| Table | `foundation_staging` | `atlas` (legacy) |
|---|---|---|
| ohlcv_stock / index_prices / technical_daily / lens scores | 06-30 ✅ | — |
| ohlcv_etf | 06-19 ⚠️ | — |
| delivery_daily | 06-19 ⚠️ | — |
| atlas_market_regime_daily | 06-25 ❌ | 06-30 |
| atlas_macro_daily | 06-25 ❌ | 06-25 |
| atlas_index_metrics_daily | 06-25 ❌ | 06-30 |
| sector_lens_daily | 06-25 ❌ | — |
| fund_rank_daily | 06-30 ✅ | — |
| de_mf_holdings | 06-26 | 05-04 (public) |

## Next actions
1. G1 kickoff: full table inventory across all schemas (producers/consumers), map cross-schema deps.
2. Draft the G2 refresh matrix → **FM sign-off gate**.
