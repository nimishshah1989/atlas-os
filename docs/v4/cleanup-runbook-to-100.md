# Atlas cleanup — RUNBOOK to 100% (resumable)

Objective: G1–G7 fully complied. **Objective truth = `python scripts/ops/schema_gate.py`
must return 0** (single schema) + the other per-goal gates below. Baseline 2026-07-02: gate=165.
Read `docs/v4/cleanup-loop-state.md` + memory `atlas-cleanup-loop-mandate.md` first.
Locked decisions D1–D11 (single schema = rename `foundation_staging`→`atlas_foundation`;
prices = Kite only; calculations = last EOD, current day live-only; retire JIP/M2-M5/
intelligence/us/global/mfwatch; drops gated on backup+green nightly).

## DONE (verified, committed on release/v4-consolidation-live)
- Kite login solved (TOTP auto-login + daily cron); batched-quote EOD ingest; retry-backoff.
- Single-source Kite prices (stocks/ETFs/indices); bhavcopy guarded; index widen+curate; EOD anchor.
- Lens journal fixed (498 real composites); regime+sector native into fs; delivery_daily rebuilt to 06-30.
- Orchestrators wired: atlas_daily (16:00 wd), atlas_weekly (Sat), atlas_sunday_qa (Sun), freshness_guard, kite_autologin (08:50 wd). **First real atlas_daily run: 2026-07-02 16:00 IST — WATCH IT.**
- Product board reads foundation_staging only (verified). single-schema GATE built.

## REMAINING — do in order; re-run `schema_gate.py` after each to watch the number fall

### G2 finish (validate + retire) — after tonight's atlas_daily is green
1. Confirm `atlas_daily` ran green (logs/atlas_daily_*.log; freshness_guard PASS; board at 07-02).
2. Retire OLD crons (crontab -e): remove JIP `$WRAPPER`/`$AGENT3` lines, `run_atlas_nightly.sh`,
   `run_atlas_intelligence_nightly.sh`, `nightly_compute`, us/global (stooq/us_daily/global_daily),
   `mfwatch_daily` (pg_cron job 47), the pg_cron `atlas.mv_*` refresh jobs (1-13,44,45).
3. FM to add `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` to .env (alerts are silent without them).
4. Codify env: add `TA-Lib` + `pyotp` to pyproject.toml.
5. 07-01 stock backfill loop (scripts/ops/kite_backfill_0701_stocks.sh) — confirm it finished or delete (07-02 supersedes).

### G1 = gate to 0 (migrate the finite backend list; delete orphans)
Backend (repoint reads to foundation_staging; copy data if the fs table is empty):
6. **regime.py (biggest)** — build/point a NATIVE regime that reads fs: replace reads of
   `atlas.atlas_stock_metrics_daily/atlas_stock_states_daily/atlas_universe_stocks/atlas_index_metrics_daily`
   + `public.de_equity_ohlcv/de_index_prices` with fs equivalents (technical_daily, instrument_master,
   atlas_index_metrics_daily(fs), index_prices, breadth_nifty500_daily). Reconcile output vs current.
7. `atlas/lenses/data/adapters.py` — `atlas.atlas_universe_stocks`→instrument_master; `atlas.policy_registry`→fs.policy_registry (migrate the table).
8. `atlas/lenses/calibration.py:94` — `atlas.atlas_lens_scores_daily`→foundation_staging.
9. `atlas/intraday/auth.py` — move `atlas.atlas_kite_session` into foundation_staging (create + repoint).
10. `atlas/compute/indices.py`, `regime.py` — `public.de_index_prices`→fs.index_prices.
11. `fetch_delivery.py`/`backfill_delivery.py` — decouple from `public.de_equity_ohlcv`+`public._deliv_fill`; source delivery from NSE directly into an fs table.
12. `validate_lenses.py` — `public.de_etf_holdings`/`de_index_constituents`→fs. `harness.py:142` — `public.de_instrument`→instrument_master.
Frontend:
13. Delete orphan v6 queries (book_diff, matrix_diff, switch_proposals, fund-list, audit_trail, cells,
    landing, markets_rs, india_pulse, industry_snapshot, portfolio_*, snapshot, screen-filter, sector_breadth,
    sector_book_exposure, multi_tenure_returns, stock-detail-extra, stock_technicals, stocks, regime[v6], calls, book_diff) + the 33 root orphans + orphan API routes (`/api/policy`, `/api/portfolio/create`, `/api/cts/sectors`, +6 orphan) — none imported by a live page (verify with an import trace before rm).
14. `health.ts` — repoint `atlas.atlas_health_daily/atlas_pipeline_runs/atlas_validator_results` to fs (migrate those 3 into fs first).
15. **Gate must now = 0.** Then: DB backup → run atlas_daily green → **rename** foundation_staging→atlas_foundation (update every `foundation_staging.` string in code + `_db`/harness/config constants; re-run gate) → **DROP** atlas, public, us_atlas, global_atlas, mfwatch (FM-gated; show final drop-list from table-census.md first).

### G3 — pure-reader (mostly done; finish)
16. Confirm no scoring/roll-up math remains in live queries (deciles/leadership/composite already materialized? if the frontend still computes composite via sectorScore/fundScore, materialize into fs columns + read them). Delete fundScore.ts/sectorScore.ts math if still used. No exposed/ad-hoc endpoints (done in step 13).

### G4 — clean data model
17. Fund <12m gate in build_fund_rank_history (has_12m). ETF rollup → etf_rank_daily (build_etf_rank_history, mirror fund). Add kite_token for the 282 stocks missing it (build_universe/assign_sectors). Curate raw index_prices to the ~40 used (delete noise). No table computes what another holds (drop fs mirror-cruft per table-census §4g). Document every KEEP table (source/formula/version) in the admin methodology tab.

### G5 — zero hardcoding
18. `grep -rnE "[^a-z_](0\.[0-9]+|[0-9]{2,})" atlas/lenses/compute` for numeric scoring constants; move any to atlas_thresholds; confirm /admin/thresholds edits them + recompute works. Prove: no scoring constant in code.

### G6 — freshness/provenance
19. "data as of <EOD>" stamp on every page (Market Pulse has it; extend to Stocks/ETFs/Funds/Sectors). One freshness registry (reuse freshness_guard's table list) surfaced in /admin/data-status. Every table documented with source+refresh.

### G7 — pristine repo
20. Delete stale box copies: /home/ubuntu/{atlas-compute, atlas-prod-src, atlas-frontend-v2} (verify nothing live points at them — nightly/pm2 both = atlas-os). Prune merged/dead git branches. Run ponytail (github.com/DietrichGebert/ponytail — CC plugin: /ponytail-audit,-debt,-review) + headroom (github.com/headroomlabs-ai/headroom) — FM installs. Full review (/review or a workflow) across arch/bugs/data-health/CI. Commit/land to main.

## Verification per goal
G1: `schema_gate.py`=0 + only 5 schemas→1 (atlas_foundation). G2: atlas_daily green 3 days + Sunday QA email. G3: gate=0 frontend + no math. G4: no double-calc query + admin docs render. G5: constant-grep clean. G6: every page shows as-of. G7: ponytail/headroom clean + stale dirs gone.
