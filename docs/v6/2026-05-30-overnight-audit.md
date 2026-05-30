# Atlas OS — Overnight Audit Report

**Date:** 2026-05-30
**Scope:** 6 dimensions (data-pipeline, backend-arch, frontend-coherence, api-quality, secrets-security, code-health)
**Findings:** 47 verified (CRITICAL/HIGH adversarially verified), 3 refuted and excluded.
**Author:** Lead engineer (overnight audit pass)

Severity counts (verified): **CRITICAL 1 · HIGH 9 · MEDIUM 19 · LOW 18**.
(One HIGH — `stale-mv-cascade` — was upgraded to CRITICAL on verification; counted here under its corrected severity. See note in the table.)

---

## 1. Executive Summary — bad news first

**The platform is serving multi-day-stale data on its highest-traffic pages, and the root cause is a single incomplete cron job.** Everything else in this report is secondary.

### 1.1 Root cause: the MV refresh job never touches 7 of the most important frontend views

Migration `098_v6_seven_mvs.py` created 7 materialized views that back the landing page, stocks list, markets-RS, stock deep-dive, fund list, fund deep-dive, and calls-performance pages. Its own docstring (line 28) promises: *"Refresh strategy (Phase D): pg_cron nightly at 20:00 IST after writer chain."*

That refresh job was **never delivered for those 7 MVs.** When migration `111_consolidate_pg_cron.py` consolidated the per-MV cron jobs into one job `mv_refresh_v6_all` (jobid 23, `'45 21 * * *'`), it listed only **9** MVs (lines 53–61):

```
mv_india_pulse, mv_markets_rs_detail_charts, mv_sector_cards, mv_sector_breadth,
mv_sector_rrg, mv_sector_deepdive, mv_stock_landscape, mv_etf_list_v6, mv_etf_deepdive
```

It **omits** `mv_market_regime_landing` and `mv_stock_list_v6` (and, per the cascade verification, the other 5 from migration 098: `mv_markets_rs_grid`, `mv_stock_deepdive`, `mv_fund_list_v6`, `mv_fund_deepdive`, `mv_calls_performance`). No migration 112–120 fixes this. Migration 120 is only a tombstone deduplicating the revision graph — it is a NO-OP and adds no refresh.

**User-visible consequence:** as of the audit, the verified DB state shows the landing page and `/stocks` frozen at `as_of_date=2026-05-22` (7–8 days stale), `/markets-rs` at `2026-05-26` (3–4 days), and `mv_stock_landscape` at `2026-05-27`. Meanwhile the regime source tables (`atlas_market_regime_daily`, `atlas_stock_conviction_daily`) are fresh at `2026-05-29`. The result is **incoherent advice**: a fresh "Risk-On" verdict on the landing page sitting next to a stocks list whose Stage-2 classifications are a week old and may have already rotated to Stage 3 or deteriorated.

### 1.2 Three base source tables are also stale (separate from the MV problem)

Even after the MV job is fixed, three writers are not producing 05-29 data:
- **`atlas_fund_scorecard`** — `MAX(snapshot_date)=2026-05-22` (7d). Root cause (per verification): fund scorecard generation is **not in the nightly automation at all** — there is no `scripts/fund_scorecard*.py` invoked by `run_atlas_nightly.sh`. `atlas_fund_metrics_daily` (Lens 1 NAV) also stops at 05-20.
- **`atlas_signal_calls`** — `MAX(date)=2026-05-27` (2d). The `daily_inference` orchestrator last ran 05-27 16:13 UTC per `atlas_provenance_log`; `compute_daily_signal_calls()` needs `atlas_scorecard_daily` + `atlas_regime_daily`, both of which also MAX to 05-27. This is the "d3 for every stock" symptom.
- **`atlas_etf_scorecard`** — `MAX(snapshot_date)=2026-05-27` (2d).

### 1.3 `atlas_sector_metrics_daily` 05-29 rows have NULL metric values

The 8 v6 columns (`rs_1w/1m/6m/12m`, `pct_above_ema20/200`, `pct_52wh`, `hhi`) added in migration 097 were **never integrated into `_run_pipeline()`** (commit `c4d986ae` added the compute functions but not the wiring). The backfill populated history; the daily run writes only the original 18 columns, leaving the v6 columns NULL for 05-29. This is incomplete Phase C, not a regression — but it means sector tables show partial metrics for the current day.

### 1.4 The good news

- **Backend architecture is clean.** Eight god-files >1000 LOC are all justified; modulith boundaries hold; no dead code, no swallowed exceptions, no banned `iterrows` misuse.
- **Auth is solid.** JWT middleware + service-token gating on internal routes; all write endpoints gated; parameterized SQL in runtime paths; no hardcoded credentials in git or history.
- **Shipped TypeScript is type-safe.** All `tsc` errors are confined to test fixtures, not `app/`/`components/`/`lib/`.

**What matters most, in order:** (1) restore data to 05-29 tonight via the operational sequence in §2 — zero code changes; (2) ship migration 121 to permanently fix the cron job; (3) wire fund-scorecard generation and the missing sector columns into the nightly pipeline; (4) everything else (API hygiene, clickability, tooltips, test coverage) is real but non-urgent.

---

## 2. Fix Tonight — safe, operational, no code changes

Goal: bring every frontend surface to the **2026-05-29 Friday close** state. This is the highest-value, lowest-risk action. It re-runs writers, then refreshes all MVs. No migrations, no deploys.

> **Caveat (honesty):** the `mv_refresh_remediation_sequence` finding was marked **UNCERTAIN** in verification — the auditor could not confirm from the read-only repo that the nightly pipeline actually completed on 05-29 or that source tables are fresh. **Run the diagnostics in step 0 first and confirm output before running mutating steps.** Adjust `--date` if the latest trading close is not 05-29.

### Step 0 — Diagnose before you mutate (read-only)
```bash
ssh atlas && cd ~/atlas-os && source .venv/bin/activate

# Confirm cron job state and last run
psql -U atlas -d atlas -c "SELECT jobid, jobname, schedule, active FROM cron.job WHERE jobname='mv_refresh_v6_all';"
psql -U atlas -d atlas -c "SELECT jobid, status, start_time, end_time FROM cron.job_run_details WHERE jobid=(SELECT jobid FROM cron.job WHERE jobname='mv_refresh_v6_all') ORDER BY start_time DESC LIMIT 5;"

# Confirm source-table freshness (what we can actually refresh TO)
psql -U atlas -d atlas -c "SELECT 'regime' t, MAX(date)::text d FROM atlas.atlas_market_regime_daily
  UNION ALL SELECT 'conviction', MAX(snapshot_date)::text FROM atlas.atlas_stock_conviction_daily
  UNION ALL SELECT 'sector_metrics', MAX(date)::text FROM atlas.atlas_sector_metrics_daily
  UNION ALL SELECT 'signal_calls', MAX(date)::text FROM atlas.atlas_signal_calls
  UNION ALL SELECT 'fund_scorecard', MAX(snapshot_date)::text FROM atlas.atlas_fund_scorecard
  UNION ALL SELECT 'etf_scorecard', MAX(snapshot_date)::text FROM atlas.atlas_etf_scorecard;"
```
If `mv_refresh_v6_all` shows a recent `status='succeeded'` (or in-flight `running`), the job is firing — the problem is purely the *missing MVs in its body*, not a crashed scheduler. (The refuted finding `mv_refresh_cron_no_second_run` showed the job did fire on schedule; do not assume the scheduler is dead.)

### Step 1 — Re-run stale writers (idempotent, --force)
```bash
# Signals (fixes the "d3 for every stock" 2-day lag)
python3 scripts/m5_daily.py --date 2026-05-29 --force

# Fund metrics / scorecard
python3 scripts/m4_daily.py --date 2026-05-29 --force
```
> Note: `atlas_fund_scorecard` has no nightly generator at all (§1.2). `m4_daily` may not populate it. If it stays at 05-22 after this step, that is the **known wiring gap** — defer to Chunk C, not a tonight fix. Funds will remain at 05-22 until the generator is wired.

### Step 2 — Refresh ALL v6 MVs by hand (covers the 7 the cron omits + the 9 it includes)
```bash
psql -U atlas -d atlas <<'SQL'
REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_market_regime_landing;
REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_stock_list_v6;
REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_stock_deepdive;
REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_markets_rs_grid;
REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_fund_list_v6;
REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_fund_deepdive;
REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_calls_performance;
REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_stock_landscape;
REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_markets_rs_detail_charts;
REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_india_pulse;
REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_sector_cards;
REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_sector_breadth;
REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_sector_rrg;
REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_sector_deepdive;
REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_etf_list_v6;
REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_etf_deepdive;
SQL
```
> All 098 MVs have unique indexes (per the migration docstring), so `CONCURRENTLY` is safe and non-blocking. If any `CONCURRENTLY` errors with "cannot refresh ... concurrently" (missing unique index), drop `CONCURRENTLY` for that one MV only.

### Step 3 — Verify (read-only)
```bash
psql -U atlas -d atlas -c "
SELECT 'regime_landing' v, MAX(as_of_date)::text d FROM atlas.mv_market_regime_landing
UNION ALL SELECT 'stock_list', MAX(as_of_date)::text FROM atlas.mv_stock_list_v6
UNION ALL SELECT 'markets_rs', MAX(as_of_date)::text FROM atlas.mv_markets_rs_grid;"
```
Expected: all show `2026-05-29` (or the latest trading close). Then spot-check `/`, `/stocks`, `/markets-rs` in the browser — regime verdict and stock states should now agree on the same date.

**This buys time. The permanent fix (migration 121) is Chunk A below.** Until 121 ships, tonight's manual refresh will go stale again tomorrow.

---

## 3. Ranked Findings

Priority score = blast_radius × user_visibility × inverse_complexity (S=3, M=2, L=1). Higher = do first. Ties broken by severity.

| # | Sev | ID | Title | Location | Fix (short) | Cx | Dimension |
|---|-----|----|-------|----------|-------------|----|-----------|
| 1 | CRIT | `mv_refresh_cron_incomplete` | Cron job missing 2+ critical frontend MVs | `migrations/.../111_consolidate_pg_cron.py:48-64` | Migration 121: re-register job with all 11 MVs | S | data-pipeline |
| 2 | CRIT* | `stale-mv-cascade` | 7 MVs from migration 098 absent from any refresh | `frontend/src/lib/queries/v6/` | Same root fix as #1 (add all 7) | L | frontend-coherence |
| 3 | HIGH | `mv-stale-stock-list` | `/stocks` reads `mv_stock_list_v6` 7–8d stale | `stock-list.ts:4` | Fixed by #1 + tonight refresh | L | frontend-coherence |
| 4 | HIGH | `mv-stale-markets-rs` | `/markets-rs` reads `mv_markets_rs_grid` 3–4d stale | `markets_rs.ts:4` | Fixed by #1 + tonight refresh | L | frontend-coherence |
| 5 | HIGH | `eventheader-sector-not-linked` | Sector plain text, breaks [[everything-clickable]] | `EventHeader.tsx:62-66` | Wrap in `<LinkedSector>` | S | frontend-coherence |
| 6 | HIGH | `signal_calls_2d_stale` | `atlas_signal_calls` 2d stale ("d3 everywhere") | `atlas.atlas_signal_calls` | Re-run M5 05-29 (§2 step 1) | M | data-pipeline |
| 7 | HIGH | `etf_scorecard_2d_stale`† | `atlas_etf_scorecard` 2d stale | `atlas.atlas_etf_scorecard` | Re-run ETF compute | M | data-pipeline |
| 8 | HIGH | `fund_scorecard_7d_stale` | `atlas_fund_scorecard` 7d stale; no nightly generator | `atlas.atlas_fund_scorecard` | Wire generator into nightly | M | data-pipeline |
| 9 | HIGH | `sector_metrics_null_values_05_29` | 8 v6 sector cols never wired into pipeline → NULL | `atlas/compute/sectors.py:46-66,1160-1200` | Integrate compute fns into `_run_pipeline` | M | data-pipeline |
| 10 | MED | `dupe-markets-rs` | Duplicate `markets-rs.ts` (kebab) unused | `lib/queries/v6/markets-rs.ts` | Delete kebab file + its test | S | code-health |
| 11 | MED | `empty-conviction-pane-no-context` | Empty pane gives no staleness context | `TodayConvictionTabs.tsx:389` | Show `as_of_date` + Health link | S | frontend-coherence |
| 12 | MED | `tv-internal-no-response-envelope` | Bare `{status:ok}` not enveloped | `atlas/tv/routes.py:109-119` | Wrap in `{data,meta}` | S | api-quality |
| 13 | MED | `missing-response-models-tv-routes` | TV routes return untyped dicts | `tv/routes.py:140`, `tv_signals.py:166` | Add Pydantic response models | S | api-quality |
| 14 | LOW | `admin-endpoints-inconsistent-envelope` | Admin proposals return raw dicts | `admin/proposals.py:81-159` | Envelope + models | S | api-quality |
| 15 | LOW | orphaned-query × 6 | 6 query modules zero imports | `lib/queries/v6/*` | Delete (see §4.6) | S | code-health |
| 16 | LOW | `orphaned-component-etf-trader-view` | `ETFTraderViewHeader` zero imports | `components/v6/etfs/ETFTraderViewHeader.tsx` | Delete or TODO | S | code-health |
| 17 | LOW | `intraday-docs-outdated` | Docstring claims auth-exempt; uses service token | `atlas/api/intraday.py:18` | Fix docstring | S | api-quality |
| 18 | LOW | `sql-injection-discovery-persist-cells` | f-string SQL (enum-bounded, file-gen only) | `discovery/persist_cells.py:299,342-344` | Parameterize / validate enums | S | secrets-security |
| 19 | MED | `path-traversal-risk-screenshot` | File-path param; validation correct but thin | `tv_signals.py:136-163` | Defense-in-depth (whitelist, no-symlink) | S | secrets-security |
| 20 | MED | `regime-driver-not-explained` | Verdict doesn't say which driver triggered Cautious | `RegimeVerdict.tsx:12-24` | Append driver sub-clause | M | frontend-coherence |
| 21 | MED | `jargon-rs-state-no-inline-tooltip` | RS state chips lack inline definitions | `StocksTableV6.tsx` | `InfoTooltip` on `StateBadge` | M | frontend-coherence |
| 22 | MED | `breadth-tile-vix-context-missing` | Breadth tile ignores VIX constraint | `SignalScorecard.tsx:116-154` | Add VIX sub-metric / commentary | M | frontend-coherence |
| 23 | HIGH | `api-url-versioning-inconsistent` | Mixed `/api/*` vs `/v1/*` vs `/api/v1/*` | `agents.py:38`, `trading.py:22`, +6 | Standardize prefix | M | api-quality |
| 24 | HIGH | `tv-signals-offset-pagination` | Offset pagination, not cursor | `tv_signals.py:81-120` | Convert to cursor | M | api-quality |
| 25 | MED | `trading-endpoints-untyped-responses` | All `/api/trading/*` return bare dict | `trading.py:34-265` | Pydantic models | M | api-quality |
| 26 | MED | `password-plaintext-cookie` | Plaintext password in auth cookie | `login/page.tsx:21`, `middleware.ts:15` | Session token + server store | M | secrets-security |
| 27 | MED | `missing-idempotency-key-write-protection` | No `Idempotency-Key` on writes | 6 POST endpoints | Idempotency middleware | M | api-quality |
| 28 | MED | `missing-rate-limit-headers` | No `X-RateLimit-*` headers | `atlas/api/__init__.py` | Rate-limit middleware | M | api-quality |
| 29 | MED | `candidates-factory-monolithic` | 2027-LOC archetype factory | `discovery/deep_search_candidates.py` | Split per-archetype | M | backend-arch |
| 30 | MED | `scorecard-writer-ui-mixed` | 1231-LOC mixes orchestration + ELI5 | `features/scorecard_writer.py` | Extract ELI5 + loaders | M | backend-arch |
| 31 | MED | `etf-scorecard-ui-mixed` | 1074-LOC mixes scorers + ELI5 | `inference/etf_scorecard.py` | Extract scorers + ELI5 | M | backend-arch |
| 32 | MED | backend-test-gaps × 5 | features/decisions/regime/tv/verdict: 0 tests | `tests/atlas/{...}/` | Add unit tests | M | code-health |
| 33 | LOW | `unused-export-gold-availability` | `isGoldAvailable()` only used by tests | `gold_availability.ts` | Wire in or delete | M | code-health |
| 34 | LOW | `ts-errors-test-fixtures` | TS errors confined to test fixtures | `src/**/__tests__/*` | Fix fixture types | M | code-health |
| 35 | LOW | `env-var-not-in-git` | `.env.local` has prod-like DB pwd (gitignored) | `frontend/.env.local` | Secrets manager / injected env | S | secrets-security |
| 36 | LOW | `iterrows-stateful-classifier` | iterrows is correct (stateful) | `states/classifier.py:273` | Comment only — no change | S | backend-arch |
| 37 | LOW | `exceptions-defensive-correct` | Handlers are correct defensive guards | `compute/_session.py`, etc. | No change | S | backend-arch |
| 38 | UNC | `mv_refresh_remediation_sequence` | The §2 sequence (run diagnostics first) | EC2 + Supabase | Operational; see §2 | L | data-pipeline |

\* `stale-mv-cascade` was filed HIGH; verification upgraded to CRITICAL (it is the superset root cause of #3/#4). 
† `etf_scorecard_2d_stale` is filed MEDIUM in the source JSON; grouped near the other staleness HIGHs for operational adjacency. Counted as MEDIUM in totals.

---

## 4. Per-Dimension Detail

### 4.1 data-pipeline

**`mv_refresh_cron_incomplete` (CRITICAL).** `migrations/versions/111_consolidate_pg_cron.py:48-64` registers `mv_refresh_v6_all` (`'45 21 * * *'`) with exactly 9 REFRESH statements (lines 53–61). It omits `mv_market_regime_landing` and `mv_stock_list_v6`, both created in migration 098 and read by `frontend/src/lib/queries/v6/market-regime.ts:145` and `stock-list.ts:114` (both files comment "MV refreshed nightly via pg_cron (Phase D)" — that promise is false for these views). **Verified in repo:** I read 111 (9 MVs, confirmed) and 098 (creates 7 MVs none of which appear in 111). **Fix:** migration 121 (revises 120) unschedules job 23 and re-registers with all 11+ MVs. See §5 Chunk A.

**`stale-mv-cascade` (HIGH → CRITICAL).** All 7 MVs from migration 098 (`mv_market_regime_landing`, `mv_markets_rs_grid`, `mv_stock_list_v6`, `mv_stock_deepdive`, `mv_fund_list_v6`, `mv_fund_deepdive`, `mv_calls_performance`) are absent from every cron schedule. They grow stale indefinitely. Migration 098's own docstring (line 28) promised "Phase D pg_cron"; it was never delivered. **Fix:** same as above — 121 must enumerate all 098 MVs plus the 9 already present.

**`signal_calls_2d_stale` (HIGH).** `MAX(date)=2026-05-27`. `daily_inference` last ran 05-27 16:13 UTC (`atlas_provenance_log`). `compute_daily_signal_calls()` requires `atlas_scorecard_daily` + `atlas_regime_daily`, both also at 05-27. `atlas_stock_decisions_daily` *does* have 05-29 (676 rows) — likely a partial/manual `run_stock_decisions()`, not the full M5. This is the "d3 for every stock" symptom. **Fix:** §2 step 1 (`m5_daily --date 2026-05-29 --force`); check M5 log for the gap.

**`fund_scorecard_7d_stale` (HIGH).** `MAX(snapshot_date)=2026-05-22`, 587 rows, single snapshot. **Root cause differs from filed evidence:** there is no `scripts/fund_scorecard*.py` in `run_atlas_nightly.sh` — fund scorecard generation was never integrated into automation (table exists from migration 093). `atlas_fund_metrics_daily` also stops at 05-20 even though M4 ran 05-29 (states table is current). **Fix:** wire a fund-scorecard generator into the nightly chain (Chunk C). Tonight's `m4_daily` will likely *not* fix this.

**`etf_scorecard_2d_stale` (MEDIUM).** `MAX(snapshot_date)=2026-05-27`. Same family as fund scorecard. **Fix:** verify ETF compute step + NAV availability; run manually if a step exists.

**`sector_metrics_null_values_05_29` (HIGH).** The 8 v6 columns added in migration 097 (`rs_1w/1m/6m/12m`, `pct_above_ema20/200`, `pct_52wh`, `hhi`) are absent from `METRICS_COLUMNS` (`atlas/compute/sectors.py:46-66`) and from `_run_pipeline()` (lines 1160-1200). Commit `c4d986ae` added the 4 compute functions (lines 883-1107) but did not wire them into the daily flow. Backfill populated history (74,752 rows per `2026-05-27-B2-final.md`); daily run writes only the original 18 columns → v6 columns NULL for 05-29. **This is incomplete Phase C, not a bug.** **Fix:** integrate the 4 compute functions into `_run_pipeline` and add the 8 columns to the upsert payload, then re-run M3 for 05-29 (Chunk C).

**`mv_refresh_remediation_sequence` (UNCERTAIN).** The §2 sequence is structurally sound (writers → cron fix → MV refresh, dependency-ordered). Verification could not confirm from the read-only repo that the 05-29 pipeline completed or that source tables are fresh — hence the §2 step-0 diagnostics requirement before mutating.

### 4.2 frontend-coherence

**`eventheader-sector-not-linked` (HIGH).** `frontend/src/components/v6/stock-detail/EventHeader.tsx:62-66` (read directly) renders `{sector}` inside a plain `<span>` with no Link. `LinkedSector` exists and is used in `StocksTableV6`, `SectorsListV6`, `SectorLadder`. Violates [[everything-clickable]]. High-traffic entry point. **Fix:** replace the `<span>` at lines 62-66 with `<LinkedSector sector={sector} className="..." />`.

**`mv-stale-stock-list` / `mv-stale-markets-rs` (HIGH).** Symptoms of the cron gap (§4.1). `/stocks` shows states 7–8d old; `/markets-rs` shows RS rankings 3–4d old while source tables are current at 05-29. **Fix:** §2 tonight + Chunk A permanent fix.

**`regime-driver-not-explained` (MEDIUM, user-visible).** `RegimeVerdict.tsx:12-24` renders e.g. "Cautious — deploy 40%" with no driver. `regime.py:443-445` can trigger Cautious via `near_200`, `breadth_deteriorating`, or `vix_band`. **Fix:** expose the triggering flag(s) in `MarketRegimeRow`; append a sub-clause ("(VIX elevated)" / "(breadth deteriorating)" / "(price near 200 EMA)").

**`jargon-rs-state-no-inline-tooltip` (MEDIUM, user-visible).** `StateBadge` chips (Leader/Strong/Consolidating/Emerging) have no inline definition; definitions live only in `MethodologyTabs`. Violates [[atlas-explainer-flywheel]]. **Fix:** `InfoTooltip` on `StateBadge` reusing the existing definitions.

**`breadth-tile-vix-context-missing` (MEDIUM).** `buildBreadthTile()` (`SignalScorecard.tsx:116-154`) evaluates only `pct_above_ema_50`; can show green while regime is Cautious because VIX ∈ [22,28]. **Fix:** add VIX sub-metric/commentary when elevated (>22). (Note: the related "threshold mismatch" finding was **refuted** — see §6.)

**`empty-conviction-pane-no-context` (MEDIUM, user-visible).** `TodayConvictionTabs.tsx:389` renders `<EmptyPane/>` with no staleness context. When signal_calls is stale (§4.1) users see empty tabs and can't tell "stale" from "genuinely none". **Fix:** show "No active calls (as of {as_of_date}). Computed nightly… Check Health if this persists."

### 4.3 api-quality

**`api-url-versioning-inconsistent` (HIGH).** CLAUDE.md line 77 mandates Bloomberg-style `/v1/...`. Actual: `/api/agents`, `/api/strategies/...`, `/api/trading/*`, `/api/portfolios/*`, `/api/kite/*` (no `/v1`), plus a *third* hybrid pattern `/api/v1/intraday`, `/api/v1/tv`. Three schemes in one API. **Fix:** standardize to `/api/v1/` across routers; update `auth.py` `_EXEMPT_PREFIXES` / `_SERVICE_TOKEN_PREFIXES`. *Breaking change — coordinate with frontend; see Chunk F.*

**`tv-signals-offset-pagination` (HIGH).** `tv_signals.py:81-120` uses `offset` (line 84) + `LIMIT :limit OFFSET :offset` (line 110). CLAUDE.md line 81: "Cursor pagination. Never offset." `screen.py:217-271` is the correct reference (base64 `(instrument_id, snapshot_date)`). **Fix:** convert to cursor; return `next_cursor` in `meta`.

**`trading-endpoints-untyped-responses` (MEDIUM).** Every `/api/trading/*` endpoint returns bare `dict` with `# type: ignore[type-arg]`; uses `_envelope()` manually. No `response_model`. **Fix:** Pydantic models inheriting the `{data, meta}` envelope.

**`missing-response-models-tv-routes` (MEDIUM).** `tv/routes.py:140` and `tv_signals.py:166` return untyped `dict`. **Fix:** `PeerMatrixResponse`, `GenerateReportResponse`.

**`tv-internal-no-response-envelope` (MEDIUM).** `tv/routes.py:117` returns `{'status':'ok'}` un-enveloped. **Fix:** wrap in `{data, meta}`.

**`missing-idempotency-key-write-protection` (MEDIUM).** Zero `Idempotency` references in `atlas/api`. 6 POST endpoints affected. **Fix:** idempotency middleware (key + response hash store).

**`missing-rate-limit-headers` (MEDIUM).** Zero `X-RateLimit` references. **Fix:** middleware emitting `X-RateLimit-Limit/Remaining/Reset`.

**`admin-endpoints-inconsistent-envelope` (LOW).** `admin/proposals.py:96` returns `{'proposals':..,'count':..}` un-enveloped. **Fix:** `ProposalListResponse`/`ProposalApprovedResponse` + envelope.

**`intraday-docs-outdated` (LOW).** `intraday.py:18` docstring claims routes are auth-exempt; `auth.py:55` lists `/api/v1/intraday` in `_SERVICE_TOKEN_PREFIXES` (requires `ATLAS_INTERNAL_SECRET`). **Fix:** correct the docstring.

### 4.4 secrets-security

**`password-plaintext-cookie` (MEDIUM, user-visible).** `login/page.tsx:21` sets `atlas_auth` cookie = plaintext password; `middleware.ts:15` compares cookie value directly to `process.env.ATLAS_PASSWORD`. HTTPOnly mitigates JS theft but the password rides every request and an env rotation locks out all users. **Fix:** OWASP session pattern — random token, server-side store with TTL+HMAC, token ID in HTTPOnly cookie.

**`path-traversal-risk-screenshot` (MEDIUM).** `tv_signals.py:136-163` accepts `path` query param, validates via `Path.resolve()` + `startswith(allowed_base)` (correct) and is gated by `X-Internal-Secret`. Residual risk: symlink/`resolve()` edge cases. **Fix:** defense-in-depth — DB whitelist of allowed PNGs, reject symlinks (`is_symlink()`), strict extension check, audit-log resolved paths.

**`sql-injection-discovery-persist-cells` (LOW).** `persist_cells.py:299,342-344` builds SQL via f-strings, but inputs (`cap_tier`/`action`/`tenure`) are enum-bounded and the SQL is written to files for manual review, not executed at runtime. **Not a runtime vector.** **Fix:** parameterize or add a runtime enum-validation guard for defense-in-depth.

**`env-var-not-in-git` (LOW).** `frontend/.env.local` is correctly gitignored (`.gitignore:36`) and not in history. It contains a prod-like Supabase DB password in plaintext on the dev machine. **Fix:** inject env at deploy time; use a secrets manager locally; document in CONTRIBUTING.md.

### 4.5 backend-arch

Architecture is healthy. The only items are maintainability optimizations (not correctness):

- **`candidates-factory-monolithic` (MEDIUM):** `deep_search_candidates.py` (2027 LOC), 16 generators for 4 tenures × 3 tiers × 2 directions. Split into `atlas/discovery/candidates/{positive,negative}/*.py` with a thin aggregator.
- **`scorecard-writer-ui-mixed` (MEDIUM):** `features/scorecard_writer.py` (1231 LOC) mixes orchestration, feature loaders (~300 LOC), ELI5 rendering (~200 LOC). Extract ELI5 → `atlas/inference/eli5_scorecard.py`; loaders → `atlas/features/loaders/`.
- **`etf-scorecard-ui-mixed` (MEDIUM):** `inference/etf_scorecard.py` (1074 LOC) mixes 6 scorers + ELI5 + SQL. Extract scorers → `atlas/inference/etf/`; ELI5 → `eli5_etf.py`.
- **`iterrows-stateful-classifier` (LOW):** `states/classifier.py:273` — iterrows is *correct* (path-dependent State 1→2→3→4 transitions). Add a comment only.
- **`exceptions-defensive-correct` (LOW):** `compute/_session.py`, `nse_bhavcopy_ingest.py` handlers are correct defensive guards. No change.

### 4.6 code-health

**`dupe-markets-rs` (MEDIUM).** Confirmed in repo: `lib/queries/v6/markets-rs.ts` (kebab) is self-referenced only; `markets_rs.ts` (underscore) is imported by `app/markets-rs/page.tsx:9` and `MarketsRsClient.tsx:22`. **Fix:** delete `markets-rs.ts` + `__tests__/markets-rs.test.ts`.

**Orphaned query modules (LOW) — all confirmed zero non-test imports:** `stock-list.ts` (`getStockListPage`), `fund-list.ts` (`getFundListPage`), `stock-deepdive.ts` (`getStockDeepdive`), `market-regime.ts` (`getMarketRegimePage`), `calls-performance.ts` (`getCallsPerformancePage` — the live `/calls` page imports `queries/v6/calls`, confirmed at `app/calls/page.tsx:22`), `fund-deepdive.ts` (`getFundDeepdive`). **Caution:** these read the same MVs as the *live* query files — confirm the live pages do **not** transitively re-export from them before deleting. **Fix:** delete the 6 orphans (or TODO-mark if a future feature is planned).

> ⚠️ **Coordination note:** the kebab `markets-rs.ts` and these orphans were committed canonical-page placeholders. They reference the *same* stale MVs we are fixing in Chunk A. Deleting them is purely cleanup and does NOT change runtime behavior — but do Chunk A first so nobody confuses "deleted the wrong file" with "broke the page."

**`orphaned-component-etf-trader-view` (LOW).** `ETFTraderViewHeader.tsx` (113 LOC) only referenced in comments in `BenchmarkToggle.tsx`. **Fix:** delete or TODO. (Cross-check against migrations 115/116 "trader_view" work before deleting — a redesign may revive it.)

**`unused-export-gold-availability` (LOW).** `isGoldAvailable()` only imported by its test; `BenchmarkToggle.tsx` documents the contract but never calls it. **Fix:** wire into the RSC page rendering `BenchmarkToggle`, or delete query+test.

**`backend-test-gaps` (MEDIUM ×5).** Zero unit tests in `atlas/features` (6 modules), `atlas/decisions` (3), `atlas/regime` (2), `atlas/tv` (6 — confirmed), `atlas/verdict` (1: `derive.py` — confirmed). 18 modules total. **Fix:** add `tests/atlas/{context}/test_*.py`; prioritize `regime/compute_regime.py` and `decisions/evaluator.py` (highest blast radius — they drive page rendering and daily signal generation).

**`ts-errors-test-fixtures` (LOW).** `tsc --noEmit` errors are all in `__tests__` fixtures (e.g. `cross-link-tokens.test.tsx:32` ETFRow mismatch). Shipped code is clean. **Fix:** update fixture types (`FundMasterRow` needs `data_source`, `aum_cr`, `aum_as_of`).

---

## 5. Chunked Fix Plan

Each chunk = one session with review. Ordered by dependency + impact.

### Chunk 0 — TONIGHT: operational data restore *(automate-with-supervision)*
- **Findings:** `signal_calls_2d_stale`, the MV-staleness symptoms, `mv_refresh_remediation_sequence`.
- **Action:** §2 (diagnostics → writers → manual MV refresh).
- **Files touched:** none (production ops only).
- **Verification:** §2 step 3 — all MVs at 05-29; browser spot-check `/`, `/stocks`, `/markets-rs` agree on date.
- **Complexity:** L (ops). **Review:** human-supervised; run step 0 diagnostics first, then proceed.

### Chunk A — Migration 121: permanent cron fix *(needs human review)*
- **Findings:** `mv_refresh_cron_incomplete` (CRIT), `stale-mv-cascade` (CRIT), `mv-stale-stock-list`, `mv-stale-markets-rs`.
- **Action:** new `migrations/versions/121_*.py` (revises 120): `cron.unschedule('mv_refresh_v6_all')` then re-`schedule` with **all 16 v6 MVs** (the 9 from 111 + the 7 from 098), ordered so dependents follow sources.
- **Files touched:** `migrations/versions/121_v6_cron_complete_mv_refresh.py`. Apply via the project's working write path (MCP execute_sql per migration-098/120 precedent; Mac psycopg2 hangs on Supabase).
- **Verification:** `SELECT command FROM cron.job WHERE jobname='mv_refresh_v6_all'` shows all 16 REFRESH lines; let it fire once at 21:45 UTC; confirm all MVs advance next morning.
- **Complexity:** S. **Review:** human — production cron change. *Gated path: invoke `/tdd` or `/plan-eng-review` before editing migrations.*

### Chunk B — Quick frontend coherence wins *(automate)*
- **Findings:** `eventheader-sector-not-linked`, `empty-conviction-pane-no-context`.
- **Files touched:** `EventHeader.tsx`, `TodayConvictionTabs.tsx` (+ `EmptyPane`).
- **Verification:** sector chip on stock detail navigates to `/sectors/[sector]`; empty pane shows `as_of_date` + Health link. Design-review pass.
- **Complexity:** S. **Review:** light (frontend-design skill + design-review). *Gated path: `frontend/src/**`.*

### Chunk C — Pipeline completeness: fund scorecard + sector v6 columns *(needs human review)*
- **Findings:** `fund_scorecard_7d_stale`, `sector_metrics_null_values_05_29`, `etf_scorecard_2d_stale`.
- **Action:** wire fund-scorecard generation into `run_atlas_nightly.sh`; integrate the 4 sector compute fns into `sectors.py::_run_pipeline` + add 8 cols to upsert; verify ETF compute step. Re-run M3/M4 05-29.
- **Files touched:** `atlas/compute/sectors.py`, `run_atlas_nightly.sh`, fund/etf scorecard writer(s), backfill scripts.
- **Verification:** `atlas_fund_scorecard`, `atlas_etf_scorecard`, sector v6 columns all current; no NULLs for current day. Row-count before/after logged (per data-engineering rules).
- **Complexity:** M–L. **Review:** human — touches finance-critical compute + nightly automation. *Gated: invoke `/tdd`; `atlas/compute/**` edits gated.*

### Chunk D — Dead-code cleanup *(automate, after Chunk A)*
- **Findings:** `dupe-markets-rs`, 6 orphaned queries, `orphaned-component-etf-trader-view`, `unused-export-gold-availability` (decide), `ts-errors-test-fixtures`.
- **Files touched:** delete kebab `markets-rs.ts` + test; delete 6 orphan query modules; delete/TODO `ETFTraderViewHeader.tsx`; fix test fixtures.
- **Verification:** `tsc --noEmit` clean (incl. fixtures); `npm run build` green; full test suite passes; grep confirms no dangling imports.
- **Complexity:** S–M. **Review:** light, BUT confirm no transitive re-exports and cross-check 115/116 trader-view work before deleting `ETFTraderViewHeader`.

### Chunk E — API hygiene non-breaking *(automate)*
- **Findings:** `tv-internal-no-response-envelope`, `missing-response-models-tv-routes`, `trading-endpoints-untyped-responses`, `admin-endpoints-inconsistent-envelope`, `intraday-docs-outdated`, `sql-injection-discovery-persist-cells`, `path-traversal-risk-screenshot`.
- **Files touched:** `tv/routes.py`, `tv_signals.py`, `trading.py`, `admin/proposals.py`, `intraday.py`, `discovery/persist_cells.py`.
- **Verification:** OpenAPI schema generates for all touched routes; envelope shape consistent; existing API tests pass; path-traversal unit test (symlink rejection).
- **Complexity:** M. **Review:** light–medium (Pydantic additions are additive/non-breaking).

### Chunk F — API breaking changes *(needs human review + frontend coordination)*
- **Findings:** `api-url-versioning-inconsistent`, `tv-signals-offset-pagination`, `password-plaintext-cookie`.
- **Files touched:** all routers' prefixes, `auth.py`, frontend API clients; `tv_signals.py` pagination; `login/page.tsx`, `middleware.ts`.
- **Verification:** full e2e — every frontend call resolves to new URLs; cursor pagination round-trips; login/logout/session-expiry works; no user lockout on env rotation.
- **Complexity:** M–L. **Review:** human — breaking. Ship behind a transition window; keep old prefixes as 308-redirects briefly.

### Chunk G — Backend test coverage *(automate incrementally)*
- **Findings:** `backend-test-gaps` ×5.
- **Files touched:** new `tests/atlas/{features,decisions,regime,tv,verdict}/`.
- **Verification:** ≥80% coverage on new code; CI green. Prioritize `regime` + `decisions` first.
- **Complexity:** M (per context). **Review:** light. *Invoke `/tdd`.*

### Chunk H — Backend refactors *(automate, low urgency)*
- **Findings:** `candidates-factory-monolithic`, `scorecard-writer-ui-mixed`, `etf-scorecard-ui-mixed`, `iterrows-stateful-classifier` (comment), `exceptions-defensive-correct` (none).
- **Files touched:** `discovery/deep_search_candidates.py` → `candidates/`, `features/scorecard_writer.py`, `inference/etf_scorecard.py`.
- **Verification:** behavior unchanged (golden-output diff on scorecard/candidate generation); module size limits respected; all tests pass.
- **Complexity:** M each. **Review:** medium — pure refactor, must prove output-identical. *Invoke `simplify`.*

---

## 6. Do NOT touch — intentional, looks-broken-but-isn't

1. **Breadth tile vs regime threshold "mismatch"** (REFUTED `scorecard-regime-threshold-mismatch`). The tile threshold (`>= 0.6` for green) and regime threshold (`> 0.6` for Risk-On) are **intentionally separate**: tiles measure single signal families; the regime applies compound gating (price > 200 EMA, VIX bands). A 55% breadth tile renders yellow/orange "neutral" (not green), and a Cautious regime at VIX 25 is *coherent*, not contradictory. Only true edge case is breadth exactly 0.60 (`>=` vs `>`), which is cosmetic. Do NOT "align" the thresholds — that would break the multi-factor design. (The separate `breadth-tile-vix-context-missing` MED finding — adding VIX context — is still valid and lives in Chunk-adjacent backlog.)

2. **`MultiTenureReturnsTable` ticker as plain text** (REFUTED `multitenuretable-ticker-not-linked`). The component is only used in `StockDetailClient.tsx` to show the *current stock's own* returns — a self-referential link would be redundant. Peer/holdings tables use other components with proper Links. Do NOT add a link here.

3. **`mv_refresh_v6_all` scheduler is NOT dead** (REFUTED `mv_refresh_cron_no_second_run`). The "ran only once" evidence was captured at 21:31 UTC, 14 min *before* the 21:45 scheduled fire; the job fired on schedule (in-flight at 21:45). The problem is the **MV list inside the job body**, not a crashed scheduler. Do NOT restart/recreate pg_cron assuming it died.

4. **`states/classifier.py:273` iterrows** — correct for stateful path-dependent classification. Do not vectorize.

5. **`compute/_session.py` / `nse_bhavcopy_ingest.py` exception handlers** — intentional defensive guards (psycopg2 `InFailedSqlTransaction` recovery; date-parse fallback with downstream null-check). Do not "clean up."

6. **Eight backend god-files >1000 LOC** — all justified; do not split reflexively. Chunk H addresses only the three with genuine mixed-concern boundaries.

---

## 7. Open Questions for the User

1. **Migration 121 write path:** migrations 098/120 are NO-OP markers because Mac psycopg2 hangs on Supabase and the real DDL was applied via MCP `execute_sql`. Should 121 follow the same pattern (apply cron change via MCP, commit a marker migration), or do you want it run from the EC2 box where psycopg2 works? This affects whether tonight's manual refresh (§2) is on EC2 or Supabase.

2. **Fund scorecard generator:** `atlas_fund_scorecard` has no nightly generator (the table exists from migration 093 but nothing populates it). Is there an existing script that was meant to write it, or does this need to be built fresh in Chunk C? Knowing this changes Chunk C from "wire up" to "build + wire up."

3. **05-29 vs latest trading close:** today is 2026-05-30 (Saturday). 05-29 was Friday close — confirm that is the intended target and that NSE bhavcopy/AMFI NAV for 05-29 actually published before we `--force` the writers.

4. **API versioning (Chunk F) is breaking.** Standardizing to `/api/v1/` touches every frontend call. Do you want a hard cutover or a transition window with 308 redirects from the old prefixes? And is `/api/v1/` the target, or pure `/v1/` per the literal CLAUDE.md example (`/v1/screen.stocks`)?

5. **Orphaned query modules:** these were committed as "canonical 12-mockup page routes" placeholders. Are the deep-dive/list pages they back actually planned (keep + TODO), or superseded (delete in Chunk D)?

6. **ETF scorecard expansion:** migration 098 referenced a deferred "34→126 ETF scorecard expansion" as a Phase C dependency. Is that still on the roadmap, and does it block the ETF list/deepdive MVs from being fully correct even after the cron fix?

---

## 8. Tonight — Execution Log (what was actually done)

Appended by the live session after the audit. Distinguishes done-safely vs diagnosed-for-supervised-fix.

### DONE tonight (safe, verified)
- **tv-integration fully deployed + live** (separate from audit): merged to main, 16 migrations applied (alembic head=120), TV screener ported to Query API + JSON-safe payload (400/750 rows), stock + ETF detail pages render HTTP 200. Commits 24f35fe4 → 8b33e262.
- **Refreshed 11 fresh-source MVs.** `mv_market_regime_landing` and `mv_markets_rs_grid` advanced to **2026-05-29** ✅ — landing page + /markets-rs now show Friday close. Plus all sector MVs (mv_sector_cards/breadth/rrg/deepdive), mv_india_pulse, mv_markets_rs_detail_charts, mv_stock_deepdive refreshed.

### RECLASSIFIED (severity down) after live verification
- **`mv_stock_list_v6` is a DATE-LABEL bug, not data staleness.** Proven: RELIANCE row composite `-4.81` = `(0.2595−0.5)×20` where 0.2595 is the **05-29** conviction score. The row DATA is fresh (Friday close); only `as_of_date` is wrong because the MV's date CTE reads the dead legacy table `atlas_conviction_daily` (frozen 05-22, 2988 rows) instead of the live `atlas_stock_conviction_daily` (05-29, 7035 rows). **User impact: /stocks shows correct decisions with a wrong date stamp.** Fix = repoint the `as_of_date` CTE; gated MV-redefine migration (Chunk A-adjacent). NOT auto-applied — redefining a prod MV unsupervised at 01:30 is out of scope.

### DIAGNOSED, deferred to supervised morning fix
- **`mv_stock_landscape` stuck uniformly at 05-27** (all 747 rows) despite source `atlas_stock_metrics_daily` being fresh at 05-29. Definition-level anchor bug — needs the full CREATE reviewed to find why the anchor returns 05-27. Gated MV-redefine.
- **3 stale base writers NOT re-run tonight** (fund_scorecard 05-22, signal_calls 05-27, etf_scorecard 05-27). Reason: `signal_calls` depends on `atlas_scorecard_daily`+`atlas_regime_daily` (also 05-27), so a lone `m5 --force` won't fix it without orchestrating the scorecard→regime→signals chain; `fund_scorecard` has NO generator (Open Q2); and Open Q3 (did 05-29 NSE bhavcopy/AMFI NAV fully publish for a clean `--force`?) is unresolved. Running finance writers `--force` blind risks bad data — explicitly against the "nothing gets destroyed" constraint. Needs supervised run with the dependency chain confirmed.
- **Migration 121 (permanent cron fix)** — not written tonight; it's the gated `migrations/**` path needing /tdd or /plan-eng-review first. This is the #1 morning task (without it, tonight's manual refresh re-goes-stale tomorrow).

### Net state for the user this morning
- **Landing page (/), /markets-rs, all sector pages: LIVE with Friday 05-29 close.** ✅
- **/stocks: data is current (Friday), date label reads 05-22** — cosmetic-ish, fix is Chunk A-adjacent.
- **/funds, /etfs conviction, calls-performance: still stale** (their writers didn't run) — supervised fix.
- Everything else (frontend coherence Chunk B, API hygiene Chunk E, dead code Chunk D) is queued and ranked above.
