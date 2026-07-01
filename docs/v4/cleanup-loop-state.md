# Atlas Cleanup Loop — Live State

**Mandate:** FM's 7-goal pristine-ification of Atlas, run as a goal-sync loop.
**Branch:** `release/v4-consolidation-live` · **Topology:** THIS box is prod (pm2 `atlas-frontend-v3` :3004 + live Supabase DB).
**Autonomy:** drive hard; pause only at 3 hard gates → (1) refresh-schedule sign-off, (2) destructive action (DROP schema/table/branch, force-push), (3) prod deploy.
**Started:** 2026-07-01 · **Last updated:** 2026-07-01

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
| D10 | **Prices = Kite ONLY (single source)** — stocks + ETFs + indices. Purge `NSE_IND_CLOSE_ALL` (bhavcopy) + `KITE_HISTORICAL`-stale + seed rows; guard bhavcopy off `ohlcv_*`/`index_prices`. No multi-source. |
| — | Logged: gstack-decision-log `ea5057b1` (mandate), `e98bc6d9` (D3-D6), `44608306` (D7-D9). |

## Goal tracker
| Goal | Definition of done (runnable gate) | Status | Evidence |
|---|---|---|---|
| **G1** single schema | Inventory of every prod table tagged raw/derived/materialized + producer + consumers; query proves 0 live-path deps outside `atlas_foundation`. atlas.*/public.de_*/us_atlas/global_atlas migrated or dropped. | 🧪 census done ([table-census.md](table-census.md)), awaiting FM drop-gate | KEEP 39 / MIGRATE 34 / DROP 71 / DECIDE 6. Manifest + double-calc findings written. |
| **G2** cron/refresh | Canonical orchestrator per cadence; **FM-approved** refresh matrix; 1 script/ingest; sources+auth documented; idempotent; freshness guard fails loud. | ⏳ not started | — |
| **G3** single-source FE | page→query→table map; 0 scoring/roll-up math in FE (TS or embedded SQL); no hardcoding; no orphan/exposed endpoints. | ⏳ not started | — |
| **G4** clean data model | No double-calc; no column derived twice; raw→1 derivation→1 serving layer; documented+versioned; surfaced in admin methodology tab. | ⏳ not started | — |
| **G5** zero hardcoding | grep proves 0 numeric scoring constants in code; every weight/threshold/toggle in thresholds table, editable from /thresholds page. | ⏳ not started | — |
| **G6** freshness+provenance | Last-refresh date on every page; every table documented w/ source+refresh; one freshness registry. | ⏳ not started | — |
| **G7** pristine repo | ponytail+headroom clean; full review (arch/bug/data/CI); branches/dead-code/stale-tables pruned; only core product remains. | ⏳ not started | Tools identified: ponytail = CC plugin (`/ponytail-audit`/`-debt`/`-review`, code minimalism); headroom = agent context-compression (`pip install headroom-ai`, `headroom wrap claude`). Both install into agent/runtime → FM hands-on step (gate) at G7. |

Status legend: ⏳ not started · 🔨 in progress · 🧪 built, verifying · ✅ done (green gate) · ⛔ blocked (gate)

## Progress log (execution)
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
