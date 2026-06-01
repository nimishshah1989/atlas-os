# v6 Track-B — frontend execution plan (CORRECTED, 2026-06-01)

Supersedes the build framing in `2026-05-30-production-readiness-inventory.md`.
Built from a verified investigation (23-agent workflow: per-area code+DB+git
checks, adversarial verify, + static audits of the 5 un-browsed pages). The
inventory is **largely stale** — most P0/P1 items were fixed and merged after it
was written. Full raw findings: workflow `wf_72916604-c78` output.

## TL;DR

1. **The inventory's A/B/C/D/F items are mostly DONE in code** (merged to
   `feat/v6-m4-markets-rs`). The blocker is **deploy**, not code.
2. **The real remaining frontend work is the 5 pages nobody had browsed**
   (`/calls`, `/markets-rs`, `/etfs`, `/india-pulse`, `/portfolios`) — the audits
   found real, uncatalogued bugs there.
3. Order: **DEPLOY first** (unblocks ~8 merged fixes), then the verified
   code fixes below, each its own CI-green PR, no auto-merge.

## Already merged (verified ancestors of HEAD) — need DEPLOY, not code

| Item | Commit | Residual |
|---|---|---|
| A1 predicted_excess writer | `164221e` | false "per-stock" tooltip; deploy+MV refresh verify |
| A2 sector gate, A3 returns | `9f8aac3` | missing regression test; deploy |
| B1 price, B2 conviction header | `89ad094` | deploy (≈44 stocks honestly em-dash: no conviction_score) |
| C1 alpha-vs-Nifty (5 horizons) | `188f437` | deploy (alpha_12m null ~55 stocks: ret gaps) |
| D3 /stocks as-of date label | `444c337` | deploy |
| F1/F2 dead code | `0dca809` | none — already deleted; inventory rows stale |
| B3 rs-ratios, B4 tv/metrics | (in repo) | **API not deployed** on EC2 |

## DEPLOY — the actual unlock (human-gated; I can't SSH)

EC2 = `ubuntu@13.206.34.214`, key `~/.ssh/jsl-wealth-key.pem`, app `atlas-frontend-v2`.

1. **Frontend (Next):** `EC2_HOST=ubuntu@13.206.34.214 bash scripts/deploy_frontend_v6.sh`
   (rsyncs `frontend/src/` → builds on EC2 → `pm2 reload`, with auto-rollback on 5xx).
   Renders A2/A3/B1/B2/C1/D3.
2. **API (FastAPI):** reconcile EC2 backend checkout to `origin/main` (currently
   `1783b3d`) + restart the API process so the TV router mounts. Verify:
   - `curl -s localhost:8002/v1/stocks/RELIANCE/rs-ratios?days=252` → 200, `data.vs_nifty50` non-empty (closes B3)
   - `curl -s localhost:8002/v1/tv/metrics/SHAILY` → 200, `data.pe_ttm ≈ 81.17` (closes B4)
3. Refresh the verdict MVs if the A1 writer hasn't been picked up:
   `mv_stock_landscape`, `mv_top_conviction_daily` (mig 121 cron).

> Heed `2026-05-30-deploy-hygiene-guide.md`: backup .next, bounded build wait,
> verify HTTP before declaring done.

## Real remaining code work (verified, by PR)

P0/MAJOR first. Each = `/tdd` → tests → pyright/ruff/eslint → `/review` + `/codex review` → CI-green PR, **no auto-merge**. Migrations applied to prod via MCP **after** review (alembic stamp drifted — same as M3).

| # | PR | Severity | Migration? | Notes / gate |
|---|----|----------|-----------|--------------|
| 1 | **/calls** realized_excess **100× unit bug** + drop hardcoded 587/636 counts + hide dead "Closed" tile (100% in_flight) | **P0** | yes (mv_calls_performance rescale realized→decimal) | also closes **H2** (track-record); methodology: confirm realized=decimal fraction |
| 2 | **/india-pulse** BreadthTable `*_dma`→`*_ema` key align + `real_yield` unit fix (cpi_yoy scale) + G3 regression test | **MAJOR** | yes (mv_india_pulse_v2.sql real_yield) | G3 render already works; this is the data/label bug |
| 3 | **/etfs** `te_60d` units (realized-vol ≠ tracking-error → every verdict stuck WAIT) + `fund_house` backfill (all 1 AMC) + category-band remap | **P0-ish** | maybe (fund_house source) | methodology: define TE units |
| 4 | **/markets-rs** wire detail charts to `mv_markets_rs_detail_charts` (fully populated, unused) + `rank_12m` NULL integrity | **MAJOR** | yes (grid rank NULL guard) | **design review** (largest unwired surface) |
| 5 | **sectors** H4 leading-count (drop the `slice(0,4)` cap) + H3 theme/sector split | MAJOR/POLISH | yes (mig 124 `sector_kind`) | H4 clean; H3 needs taxonomy sign-off |
| 6 | **/stocks** D2 action/composite coherence (NEGATIVE-cell AVOID with composite≥0) | P2 | yes (mig 106 mv_stock_landscape `action` CASE) | methodology sign-off |
| 7 | **/portfolios** exclude test-fixture rows (9/9 are fixtures) + wire equity/drawdown charts (`data={[]}` stubs) | P1 | no | + custom-backtest writer persists NULL not 'NaN' |
| 8 | **H1** portfolio builder (regime deploy% × leading sectors × conviction picks, gated) | NEW | no | **design review**; resolve "gates not in base table" flaw |
| 9 | **funds** B5 rec counts / C2 v2 scorecard / H5 Weinstein transitions | P1 | tbd | re-investigate (workflow funds agent failed) |
| 10 | regression tests for merged A2/A3/B1/B2/C1 (no prod risk) | P2 | no | lock the fixes against regressions |

## Things the inventory got WRONG (don't rebuild)

- A1/A2/A3/B1/B2/C1/D3/F1/F2 — already merged. D2 "AVOID not negative" is stale
  (composite now spans −8.3..+8.9); the real bug is action/composite *disagreement*.
- G3 "macro cards unavailable" — already renders; residual is the real_yield unit bug.
- /portfolios "stub" — it's a full manual FM manager; H1 is a *separate* proposer.
