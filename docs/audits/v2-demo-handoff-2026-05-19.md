# Atlas v2 — fund-manager demo handoff (2026-05-19 morning)

**Status:** Built overnight. v2 frontend running on EC2 port 3002. **One step left for you:** open the EC2 security-group port. Everything else is done.

## TL;DR

- **What's deployed:** All consolidation phases (1-3 + 5-8) shipped on branch `feat/atlas-consolidation` and built into `/home/ubuntu/atlas-frontend-v2/` on EC2 .214, served by PM2 process `atlas-frontend-v2` on port 3002.
- **What you need to do:** Run one AWS CLI command (see "Open the demo URL" below) to open inbound tcp/3002 on the security group `sg-0215e4a4161ca4a12`, then visit `http://13.206.34.214:3002/` to compare with production at `https://atlas.jslwealth.in/`.
- **Goal-post:** `met:true` end-to-end. V5-RP-TREND rank 1 unchanged (alpha_oos 0.2018, hit_rate 0.631). `atlas/trading/lab.py` untouched throughout.

## Open the demo URL (your one action)

You authorized `0.0.0.0/0` via AskUserQuestion last night but the auto-classifier blocked me from executing the AWS CLI inline. Please run this command yourself on your laptop (any machine with `aws` configured for `ap-south-1`):

> Command body:  `aws ec2 authorize-security-group-ingress` with `--group-id sg-0215e4a4161ca4a12`, `--protocol tcp`, `--port 3002`, `--cidr 0.0.0.0/0`, `--region ap-south-1`.

Then visit: `http://13.206.34.214:3002/`

If you'd rather not open the port: `ssh -L 3002:localhost:3002 atlas` from your laptop, then the demo is at `http://localhost:3002/`.

## What changed, page by page

| Page | What's gone (v2 vs v1) | What's there instead |
|---|---|---|
| `/stocks` list | 7-gate dot row, Momentum chip column, Volume chip column, SignalCell (mini 4-line summary) | Tighter rows. `rs_state` + `risk_state` routed through `ValidatedBadge` reading `atlas_component_validation` for per-tier IC. Conviction column → `WithinStateRankCell` reading `within_state_rank`. |
| `/stocks/NESTLEIND` | Exit Risk Flags 6-boolean panel, Weinstein/Momentum interpretation cards, 4-lane StateJourneyCompact heatmap, all 6 CTS components, StockHistoryTab | Master state card (sticky), OBV continuous chart + ATR contraction gauge, within-state peers table, 252-day DwellTimeline, ComponentScorecard footer. Single consistent state — no more "Investable + Stage 4 Decline" contradiction. |
| `/sectors` | Top-down `sector_state` | Bottom-up: derived from constituent stock states via `atlas_sector_signal_unified`. Aggregate state badge + tiny stacked breadth bar (% stage 2 / stage 3 / stage 4). |
| `/funds` | 4-gate dot row (P/S/H/M), legacy composition badges | Recommendation (Recommended/Hold/Avoid) derived from composition + holdings + nav. Composition + holdings + nav rendered as compact secondary badges. nav_state retained as genuinely fund-internal. |
| `/etfs` | Top-down ETF state, legacy chip columns | Bottom-up ETF state from `atlas_etf_signal_unified`. ETFBubbleChart re-axed: x=ATR contraction, y=within_state_rank, color=engine_state. (See "Open follow-ups" below.) |
| `/global`, `/portfolios`, `/strategies`, `/us` | Stray gate / conviction references | Inherited the cleanup from shared cells. |

## Side-by-side spot check (NESTLEIND)

Internal `curl http://localhost:3002/stocks/NESTLEIND` from the EC2 host returns HTTP 200 / 234KB. Verified:

- Master state card renders `STAGE 4 DECLINE` (single source of truth from `atlas_stock_state_daily`)
- No visual gate-dot row (was present in v1)
- No exit-risk-flags panel (was present in v1)
- No StateJourneyCompact 4-lane heatmap (was present in v1)
- `Investable` count card → gone from screener cards
- `Avoid` recommendation present on fund-level views

Note: strings like `history_gate_pass`, `exit_stop_loss` still appear in the RSC JSON payload because Phase 7 used `TRUE AS history_gate_pass` etc. as compatibility stubs in the SQL — the columns are stubs, not rendered. Phase 9 of the original plan drops the underlying tables and these stubs disappear naturally.

## Architecture summary

**One DB write per nightly cycle** for stocks: `atlas-lab states classify --persist` writes `atlas_stock_state_daily`. The legacy `atlas/compute/stocks.py` nightly write is in scope to disable in Phase 8.1 (deferred — see follow-ups).

**Four SQL views** re-derive every legacy column name from the new state engine:
- `atlas_stock_signal_unified` (migration 080)
- `atlas_sector_signal_unified` (migration 084)
- `atlas_fund_signal_unified` (migration 085) — LEFT JOIN to `atlas_fund_states_daily` for nav_state retention
- `atlas_etf_signal_unified` (migration 086)

**Three aggregate v2 tables** (migrations 081-083) populated by bottom-up aggregators in `atlas/intelligence/aggregations/`:
- `atlas_sector_state_v2`
- `atlas_fund_state_v2`
- `atlas_etf_state_v2`

**Frontend queries** in `frontend/src/lib/queries/{stocks,sectors,sector-deep-dive,sector-funds,funds,etfs,conviction,instruments}.ts` all read from the unified views (Phase 7).

**Frontend components deleted (Phase 5):** StateTuple4, StateJourneyCompact, FundStateJourneyCompact, SignalCell, CTSDeepDiveCard, CTSGradeSummaryCards, CTSIndexTimingPanel, CTSSectorPanel, CTSSignalBadge, CTSTimingCell, StockHistoryTab. Plus four API routes (`/api/states-compact`, `/api/fund-states-compact`, `/api/cts/index-timing`, `/api/cts/sectors`). ~800 LOC removed.

**Frontend components rewired (Phase 6):** ConvictionCell renamed to WithinStateRankCell + reads `within_state_rank` from the unified view. RS-state and risk-state cells in StockScreener and ETFScreener route through `ValidatedBadge` looking up `atlas_component_validation` for per-tier IC.

## Commit log on `feat/atlas-consolidation` (chronological)

Phase 0 (setup): `5e1bd87`, `1f78c9b`, `265796a`, `84974cf`, `36414be`, `5c957e0`
Phase 1 (bridge): `4ac5c0e`
Phase 2 (aggregators): `c73fb6f`, `10b910c`, `a6aaf8a`
Phase 3 (tables/views/persistence): `c4c31a9`, `a51f72f`
Phase 5 (cut chips): `b551a9e`, `8d3cde4`
Phase 6 (ValidatedBadge): `1735a42`, `3f98174`
Phase 7 (query rewires): `f28204d`, `dea95dd`, `eefc4cc`, `783afe9`
Phase 8 (page rewires): `6003ec4`, `a560e56`, `177f13e`, `5cdf5ec`, `51b9aa6`, `1b3c893`

23 commits total. ~3600 LOC net change. Pre-commit hooks (ruff, mypy, secrets, pragma-coverage, chain integrity, file size, bounded-context, threshold-in-DB) passed on every commit. 14 aggregator tests + 16 migration tests + 2 WithinStateRankCell tests + 488 pre-existing Vitest tests all pass. (9 pre-existing Vitest failures in FundDecisionHistory + FundDeepDiveHeader were present before this work — not caused by the consolidation.)

## Open follow-ups (not blocking the demo)

1. **EC2 security-group rule for tcp/3002** — the one AWS CLI command described above. Until then, you can SSH-tunnel: `ssh -L 3002:localhost:3002 atlas` and visit `http://localhost:3002/`.

2. **Phase 4 (IC harness for legacy candidates)** — skipped per scope. CTS continuous values, `transition_trigger`, `breakout_trigger`, `nav_state` — none gate the demo. Run later via `atlas-lab states validate-legacy --start 2023-01-01 --end 2024-12-31` (per the plan's Phase 4 spec) to decide which survive into the engine as Tier 3 transition triggers and which get deleted in Phase 9.

3. **Phase 8.1 + 8.2 (nightly DAG cutover)** — deferred. The new state engine writes nightly already; legacy `atlas/compute/stocks.py` still writes too. Both coexist until the burn-in window completes. The legacy nightly write is harmless because the bridge view ignores the legacy table.

4. **Phase 9 (drop legacy tables)** — deferred. After 2-week burn-in proves v2 stable, the migration `088_drop_legacy_phase1.py` + `089_drop_legacy_phase2.py` (specified in the plan) can land.

5. **ETF bubble chart x-axis** — currently defaults to `1.0` for all ETFs. Reason: ATR contraction is per-stock and there's no weighted-average ATR aggregation in `atlas_etf_signal_unified` yet. Add a column to `atlas_etf_state_v2` for weighted-mean ATR-contraction across holdings, then patch the view + the chart query. ~30 min of work.

6. **`getFundDecisionHistory` still reads `atlas_fund_decisions_daily`** — that's a historical decision audit log (52 weeks back), not a current-signal table. Left untouched intentionally.

7. **Pyright noise** — IDE complains about pandas `columns=[...]` type stubs and "Import could not be resolved" for worktree files when viewed from the main tree. Pre-commit mypy passed cleanly throughout; these are IDE-side false positives.

8. **9 pre-existing Vitest failures** in `FundDecisionHistory.test.tsx` and `FundDeepDiveHeader.test.tsx` — present before this work, not caused by it. Fix them in a separate cleanup pass.

9. **Untracked side artifact:** during Phase 0, a separate spec file `docs/superpowers/specs/2026-05-18-v6-rs-trading-model-design.md` from another session got captured into commit `84974cf` (signal consolidation plan commit) due to pre-commit hook stash dynamics. Content is unrelated to this work — a v6 RS trading model brainstorm. Move to its own commit later if you want clean attribution.

## What the fund manager should evaluate

When you show them `http://13.206.34.214:3002/` vs `https://atlas.jslwealth.in/`:

1. **Is the v2 page faster to interpret?** The gate row, momentum/volume chips, and exit-flags panel are gone. Each remaining chip has an IC stamp behind it.
2. **Do they miss anything from v1?** If yes, was it actually used as a decision input, or just visual reassurance? Anything actually used we can derive from the state engine.
3. **Does "Recommended / Hold / Avoid" on funds match their intuition?** Derived from composition_state + holdings_state + nav_state per the conservative-first rule in `aggregations/fund.py`.
4. **Does `within_state_rank` replace SP04 conviction acceptably?** Same 0-100 feel, sourced from the IC-validated state engine.

If approved → merge `feat/atlas-consolidation` → `main`, deploy to production atlas-frontend on 3001, then start the 2-week burn-in clock to Phase 9 drops.

If iteration needed → run `./scripts/deploy_v2.sh` from the worktree after edits. Production `atlas.jslwealth.in` stays untouched.

## Locations

- **Worktree:** `/Users/nimishshah/Documents/GitHub/atlas-os-consolidation`
- **Branch:** `feat/atlas-consolidation`
- **Plan:** `docs/superpowers/plans/2026-05-18-atlas-signal-consolidation.md`
- **Spec:** `docs/superpowers/specs/2026-05-18-atlas-signal-consolidation-design.md`
- **Deploy script:** `./scripts/deploy_v2.sh` (one-command rebuild + restart of `atlas-frontend-v2`)
- **EC2 deploy dir:** `/home/ubuntu/atlas-frontend-v2/`
- **PM2 process:** `atlas-frontend-v2`
- **Port:** 3002 (pending security-group rule)
- **Production reference:** `https://atlas.jslwealth.in/` (atlas-frontend on 3001, untouched)
