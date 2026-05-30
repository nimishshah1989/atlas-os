# Atlas v6 — Production-Readiness Inventory (master tracker)

**Created:** 2026-05-30 · **Purpose:** the single source of truth for "what is
actually not done." Built by cross-checking the **live DB** against **what each
page actually renders** — not from git or scripts.

## Definition of DONE (the rule that fixes the disconnect)

A line item is DONE only when **the live page at atlas.jslwealth.in renders the
correct value**. Not "the script ran." Not "the table has rows." Not "tests
pass." Rendered, and right. Every item below carries a `DONE-WHEN` that names the
page + the value that must show.

> Why we kept thinking things were done: Atlas data flows through 5 layers
> (`writer → base table → MV → frontend query → page`). Past "done" was scored at
> layer 1–2. A backfill can succeed and still leave the column the page reads
> NULL, write to an MV nothing queries, or populate a table whose join is broken.
> Evidence below is `DB truth` + `page render`.

Severity: **P0** = blocks trading decisions tomorrow · **P1** = visible wrong/blank
on a core page · **P2** = quality/polish · **P3** = cleanup/future.

---

## A. P0 — Decision-surface blockers (data missing where the verdict needs it)

| # | Item | Evidence (DB + page) | Layer | Fix | DONE-WHEN |
|---|------|----------------------|-------|-----|-----------|
| A1 | **`predicted_excess` 100% NULL** — the "Expected" excess is blank everywhere | `signal_calls @05-29: 0/49 have predicted_excess`; landing conviction table + stock header render `—`; `mv_stock_landscape_trader.cell_predicted_excess` derives from it so also null | writer (`compute_daily_signal_calls`) | Compute + persist `predicted_excess` per call (it's the cell's predicted excess return) | Landing "Top conviction" + stock header show a real % in Expected for every active call |
| A2 | **Sector investability gate "unavailable"** — the verdict skips the sector gate | Stock detail gates: `Sector N/A — Sector state unavailable`; yet sector MVs (`mv_sector_cards/deepdive`) are fresh @05-29 | wiring (stock-detail → sector state join) | Repoint the gate's sector-state lookup to the populated sector MV; key by the stock's sector | Stock detail shows PASS/FAIL (not N/A) on the Sector gate; "all 5 gates" actually means 5 |
| A3 | **Stock-detail returns table mostly blank** — only 3M shows | `stock_metrics @05-29: ret_1w/1m/3m = 747/747, ret_6m 737, ret_12m 692`; page renders `1W — 1M — 3M +54% 6M — 12M —` | wiring (`getStockMetricHistory` → Returns-by-Horizon component) | Pass 1W/1M/6M/12M through to the component (data already exists) | Stock detail Returns-by-Horizon shows all 5 horizons populated |

## B. P1 — Wiring bugs (data exists in DB, page shows em-dash)

| # | Item | Evidence | Layer | Fix | DONE-WHEN |
|---|------|----------|-------|-----|-----------|
| B1 | Stock-detail **header Price = `—`** | `mv_stock_landscape.close_price 747/747` populated; page header renders `Price —` | wiring (trader-header query) | Read `close_price` into the header | Stock detail header shows a price |
| B2 | Stock-detail **header Conviction = `—`** | `mv_stock_landscape.conviction_score 703/747`; page renders `Conviction —` (but body shows 0.752) | wiring | Read conviction into the header strip | Header Conviction matches the decomposition score |
| B3 | **RS-ratio panel: "Backend endpoint may not be deployed yet"** | Endpoint `/v1/stocks/{sym}/rs-ratios` + `compute_rs_ratios()` exist in `atlas/tv/`; message fires on null return | API deploy + wiring | Verify the tv router is deployed on the running EC2 API; fix the misleading copy | RS-ratio panel renders a chart (or an honest "insufficient history" note) |
| B4 | **Fundamentals coverage 400/747** | `tv_metrics @05-29: 400 rows, all have pe/roe`; ~347 stocks (small/microcaps incl SHAILY) show `—` | data coverage + API | Expand TV-metrics universe to all 747; confirm `/v1/tv/metrics/{sym}` is served | P/E etc. populate for the full universe, or show "N/A for microcaps" honestly |
| B5 | **`/funds` recommendation counts don't match the DB** | Page shows `Reduce 586 / Hold 0 / Exit 0`; live `fund_decisions @latest: Reduce 276 / Hold 225 / Exit 29` | wiring + freshness | Find what `/funds` actually reads; repoint to live decisions @ latest date | `/funds` rec counts equal the live table |

## C. P1 — Missing features (no backend source at all)

| # | Item | Evidence | Fix | DONE-WHEN |
|---|------|----------|-----|-----------|
| C1 | **Stock alpha-vs-Nifty** never computed | No `alpha`/`excess` column on any stock metrics table; "Alpha vs Nifty" column all `—` | Add alpha = stock return − Nifty return per horizon to `stock_metrics` (cheap; rs_*_nifty500 already proves the pattern) | Returns table Alpha column populated |
| C2 | **Fund v2 scorecard not surfaced** | `atlas_fund_scorecard` has my `composite_score` (avg 50.6 @05-29) but `/funds` renders nav_state/recommendation; `fund-list.ts`/`fund-deepdive.ts` = 0 imports (dead) | Wire `/funds` to the v2 composite + momentum/consistency, or decide /funds stays nav-state and surface v2 elsewhere | The data-driven fund ranking is visible to a user |

## D. P2 — Data quality / ranking integrity

| # | Item | Evidence | Fix |
|---|------|----------|-----|
| D1 | **Confidence is a flat per-cell prior** | 49 calls → only 9 distinct `confidence_unconditional` values (one per fired cell); every stock in a cell shows identical 71%/64% | Differentiate within-cell (per-stock confidence) or relabel the column so users know it's a cell prior |
| D2 | **AVOID signal not negative** | `/stocks` "worst AVOIDs" composites ≈ −0.0…−0.2, tagged NEUTRAL not AVOID | Investigate downside compression in the composite; AVOIDs should be meaningfully negative |
| D3 | **Date label inconsistency** | `/stocks` shows "Data as of 30 May" (a non-trading Saturday); landing/sectors/detail show "29 May" | Fix the `/stocks` as-of label to the data date |

## E. P1 — Deploy / middleware (code merged ≠ running)

| # | Item | Evidence | Fix |
|---|------|----------|-----|
| E1 | **Chunk E API code not deployed** | Envelope/docstring/guard merged to main; running EC2 API still on old code | Deploy + restart the API server |
| E2 | **EC2 git behind main** | Backend/nightly/ops files `scp`'d, EC2 checkout at 1783b3d | Reconcile EC2 to `origin/main` cleanly (deploy runbook) |
| E3 | **TV routes deploy unconfirmed** | rs-ratios + tv/metrics endpoints exist in repo; B3/B4 suggest they may not be live | Confirm the router is mounted on the served API |

## F. P3 — Dead code to delete (confirmed 0 non-test imports)

| # | Item | Files |
|---|------|-------|
| F1 | 11 dead v6 query modules | `lib/queries/v6/`: calls-performance, drift_status_rollup, fund-deepdive, fund-list, gold_availability, instrument, market-regime, **markets-rs (kebab dup)**, screen, stock-deepdive, stock-list |
| F2 | ~7 dead v6 components | `components/v6/`: StockDetailClient, ETFDetailClient, FundDetailClient, SectorsListV6, FundsList, ETFsList, CellDetailClient (+ ETFTraderViewHeader) |
| F3 | Backend Chunk H refactors | split deep_search_candidates.py (2027 LOC), scorecard_writer.py, etf_scorecard.py (maintainability only) |

## G. P3 — Marked placeholders (honest "future" — not bugs)

| # | Item |
|---|------|
| G1 | Sector detail: multidim chart, cross-market comparison, macro overlays ("Coming in v6.1" ×3) |
| G2 | ETF detail: `top_holdings` JSONB placeholder |
| G3 | India Pulse: macro cards "unavailable" (macro query layer not wired) |

## H. P2/P3 — New build + design (from the pre-trading review)

| # | Item | Note |
|---|------|------|
| H1 | **Portfolio builder** | `/portfolios` is a stub; build the real builder (regime deploy-% × leading sectors × conviction picks, gated by investability gates) |
| H2 | **Since-recommendation track record** | per-stock `since-call return` exists (1 day old); build an aggregate realized-vs-predicted view (blocked by A1) |
| H3 | **RRG sector reclassification** | taxonomy mixes true sectors (Energy, Banking, IT, Metal, Pharma) with themes (Defence, Rural, MNC, Tourism, EV, Housing) → overlap distorts RRG geometry; plot a mutually-exclusive sector set, themes on a separate board |
| H4 | **RRG count reconcile** | cards say "4 leading sectors", RRG quadrant says "Leading 15" |
| H5 | **Weinstein for fund managers** | surface stage *transitions* (2→3 topping) prominently, not just a stage label |

---

## Suggested knock-out order (top-down)
1. **A1** predicted_excess writer — unblocks the whole "Expected excess" story + H2.
2. **A2 + A3** stock-detail verdict gate + returns wiring — the detail page is the trade surface.
3. **E1/E3** deploy the API so B3/B4 can even be tested.
4. **B1/B2** header price + conviction wiring.
5. **C1** stock alpha (cheap, high visibility).
6. **B5 + C2 + D2** funds correctness + AVOID compression.
7. **D3** date label; **F1/F2** dead code; **H1–H5** build/design.

Verified surfaces: landing, /stocks (+detail), /sectors, /funds, /methodology.
**Not yet browsed:** /markets-rs, /etfs, /calls, /india-pulse, /portfolios, admin
pages — treat those rows as DB-evidence-only until browsed.
