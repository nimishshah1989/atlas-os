# v6 — STATUS (source of truth: done / partial / left)

Generated **2026-06-01** by reconciling migrations 080→123 + the locked 8-page IA
(`CONTEXT.md` "v6 frontend redesign locks 2026-05-26") against **live prod state**,
verified read-only via Supabase MCP (project `nanvgbhootvvthjujkvs`).

This file resolves the §1 finding in
`docs/v6/2026-06-01-remaining-work-and-committed-plan.md`: "no one has a single
current source of truth for what's done vs left." It is that source of truth.

> **Method:** `pg_matviews.ispopulated`, `pg_stat_user_tables.n_live_tup`,
> exact `count(*)` + `max(date)` on metrics tables, `pg_attribute` for MV
> columns, `refreshed_at`/`as_of_date` for serving freshness.

---

## Headline

**The 8-page product backend is LIVE.** All 23 `atlas.*` materialized views are
populated, every one of the 8 pages has a populated serving MV, and the data is
**fresh through the last trading day** (base metrics `max(date) = 2026-05-29`,
a Friday; today is Mon 2026-06-01). The serving MVs refreshed last night
(2026-05-31 21:45 UTC) via pg_cron.

**There is no large remaining *backend* program for the 8 pages.** What the
handoff plan framed as "M4 backend" (standardizing `us_stocks.py` /
`global_pipeline.py` RS) is **off the 8-page roadmap** — see §5. The genuine
remaining backend is a thin tail (§4); the real remaining *effort* is frontend
wiring + QA and the optional discovery program (§6).

---

## 1. Per-page status (8-page IA)

All serving MVs `ispopulated = true`; grid + pulse refreshed 2026-05-31 21:45 UTC,
`as_of_date = 2026-05-29`.

| # | Page | Serving MV(s) | Rows | Status |
|---|------|---------------|------|--------|
| 01 | Market Regime | `mv_market_regime_landing`, `mv_current_market_regime` | 1, 1 | **LIVE** (regime state via v5+v6 hybrid; see §3 regime) |
| 02 | India Pulse | `mv_india_pulse` | 2614 | **LIVE** — `macro_cards` populated on all rows (from v5 `atlas_macro_daily`) |
| 03 | Markets RS | `mv_markets_rs_grid`, `mv_markets_rs_detail_charts` | 9, 13932 | **LIVE but partial** — grid is **5 windows** (`ret_1w/1m/3m/6m/12m`), lock wants **9×7** (add `1d`,`24m`). detail_charts already built (plan's "not built" was stale) |
| 04 | Sectors | `mv_sector_cards`, `_breadth`, `_rrg`, `_deepdive`, `_rotation_state` | 47901, 47901, 30, 30, 30 | **LIVE** |
| 05 | Stocks | `mv_stock_list_v6`, `mv_stock_deepdive`, `mv_stock_landscape`, `_trader` | 750, 750, 747 | **LIVE** (verdict columns via mig 113-116) |
| 06 | Funds | `mv_fund_list_v6`, `mv_fund_deepdive` | 587, 587 | **LIVE** |
| 07 | ETFs | `mv_etf_list_v6`, `mv_etf_deepdive` | 34, 34 | **LIVE** (`atlas_etf_scorecard` = 170 rows; the 34→126 expansion landed) |
| 08 | Calls Performance | `mv_calls_performance` | 636 | **LIVE** (in-flight `atlas_signal_calls` = 636) |

---

## 2. Capability-layer status (base tables)

| Layer | Tables (live rows) | Status |
|---|---|---|
| Metrics daily | stock 1.40M · fund 1.05M · etf 280k · index 265k · sector 75k | **LIVE**, fresh to 2026-05-29 |
| States daily | stock 1.39M · fund 981k · etf 280k · sector 75k | **LIVE** |
| Decisions | fund 633k · stock 6.7k · etf 235 | **LIVE** (stock/etf decisions are latest-window) |
| Scorecard / conviction | `atlas_scorecard_daily` 2988 · `atlas_conviction_daily` 2988 · `atlas_stock_conviction_daily` 7035 · `mv_top_conviction_daily` 703 | **LIVE** |
| Signals / IC | `atlas_signal_calls` 636 · `atlas_signal_ic_rolling` 490 · `atlas_signal_weights` 82 | **LIVE** |
| Benchmarks | `atlas_benchmark_returns_cache` 24319 | **LIVE** |

---

## 3. Gaps confirmed on prod

| Gap | Evidence | Impact | Roadmap? |
|---|---|---|---|
| **Markets RS grid 5→7 windows** | `mv_markets_rs_grid` cols = `ret_1w/1m/3m/6m/12m` only | Page 03 grid missing `1d` + `24m` vs the 9×7 lock | **Yes** — on-roadmap, small |
| **v6 regime state log thin** | `atlas_regime_daily` (v6) = **4 rows**; v5 `atlas_market_regime_daily` = 2614 | Landing regime *state* history is v6-thin; rich inputs + 12-wk journey likely served from v5. Verify the landing's 12-week journey source | Verify |
| **v6 macro-features empty** | `atlas_macro_features_daily` = **0 rows**; only `atlas/ingest/macro/fred_ingest.py` exists | Named full-parity fields (FII/DII, DXY, US10Y, `concentration_top*`, `avg_pairwise_corr`) are unbuilt. India Pulse cards currently use v5 macro, so impact is the *new* parity fields only — spot-check the mockups | Partial |
| **`atlas_benchmark_master` empty** | 0 rows | Plan's "MSCIWORLD/SP500 confirmed active in benchmark_master" is **stale**. Non-blocking: the RS grid reads baselines from raw price tables (`de_index_prices`, `de_global_prices`, `us_atlas.stock_ohlcv`) via MV CTE | Cosmetic |

**Unbuilt macro ingest** (CONTEXT.md "MV scope contract — full mockup parity",
Phase A): `atlas/macro/pairwise_correlation.py`, `atlas/macro/concentration.py`,
NSDL FII/DII scrape. (`fred_ingest.py` for US10Y/DXY exists.)

---

## 4. The genuine remaining backend tail (8-page product)

Small and bounded — not an M4–M7-sized program:

1. **Markets RS grid 5→7 windows** — extend `mv_markets_rs_grid` (+ detail) to add
   `1d`/`24m`. Migration + MV rebuild + verify. On-roadmap.
2. **v6 regime state** — confirm whether Page 01's 12-week journey reads v5 or v6;
   backfill `atlas_regime_daily` if v6 is load-bearing.
3. **Macro full-parity fields** (optional, mockup-driven) — build
   `pairwise_correlation.py` + `concentration.py` + NSDL FII/DII, populate
   `atlas_macro_features_daily`. Only needed if the mockups require fields v5 macro
   doesn't already supply.

---

## 5. Off-roadmap (the "M4" that isn't)

`atlas/compute/us_stocks.py` + `atlas/compute/global_pipeline.py` are a
**US / international stock+ETF screening** surface (`/v6/us`, `/v6/global`,
`frontend/src/lib/queries/us-stocks.ts`, `us-etfs.ts`) — **not in the locked
8-page India IA**. The Markets RS page gets its US/global context (S&P 500,
MSCI World, EEM) from **raw price tables via MV CTEs** (CONTEXT.md baseline
registry), not from these pipelines' `rs_*_acwi`/`rs_*_vt` columns.

ADR-0002 deferred their excess→relative standardization to "M4" mechanically.
It touches no shipped 8-page surface. **Recommendation: de-prioritize.** Do it
later as a ~30-min consistency pass if/when the US screening surface ships.

---

## 6. M4–M7 reframe (CEO scope decision)

M4–M7 were never crisply defined (handoff plan §1). The audit makes the fork
concrete:

- **(b) Finish the 8-page product on built data** — *nearly done*. Backend +
  serving layer is LIVE. Remaining = §4 thin tail + **frontend wiring/QA of the
  8 pages against live MVs** ("see what you build"). This is likely 1 backend
  chunk + the bulk-of-effort frontend pass, **not four milestones**.
- **(a) Formal Phase 0.5–9 discovery program** — *genuinely not-started*:
  `atlas_cell_walkforward_runs` 0, `atlas_drift_event_log` 0, `atlas_ledger` /
  `atlas_paper_portfolio` / `atlas_user_lots` / `atlas_brief_cache` all 0. This
  IS a multi-milestone program if the CEO wants it.

**These are different products.** Decide (a) vs (b) before labeling anything M4–M7.

---

## 7. Known operational notes (carried from handoff plan §4)

- **Prod alembic stamp drift**: `public.alembic_version` = 112 while schema ≈ 123;
  mig **064** has an IMMUTABLE-index bug that breaks a fresh `alembic upgrade head`.
  Prod DDL applied directly via MCP until re-baselined. Owner decision needed.
- **EC2** parked on `feat/v6-m3-rs-baselines`, local edits stashed; nightly crons
  run the current checkout (no auto-pull). Return to `main` when convenient.
- Local Mac commits need `--no-verify` (pre-commit ruff 0.7.4 ≠ CI 0.15.x). CI is
  the real gate.
