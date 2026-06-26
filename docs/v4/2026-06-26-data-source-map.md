# Atlas v4 — exact data-source map + canonical-table proposal (2026-06-26)

Written at FM request: stop development, agree on the exact backend tables first.
Everything below is traced from the live DB + the actual `FROM`/`JOIN` in each query
(not from memory).

## 1. The sprawl (why every fix is a fight)

| schema | tables | matviews | views | what it is |
|---|---|---|---|---|
| `atlas` | 133 | 23 | 9 = **165** | the legacy compute layer — the real chaos |
| `public` | 104 | — | — | external "data-engine" raw (`de_*`) |
| `foundation_staging` | 56 | — | — | the intended single READ schema |

So there are **~325 objects** across three schemas. The board is *supposed* to read only
`foundation_staging`, but several pages still reach into `atlas.*` and `public.*`.

## 2. Per-page data-source map (LENS_V4 paths only)

✅ = reads only `foundation_staging` · ⚠️ = still reads `atlas.*` / `public.*`

| Page | Status | Tables it reads |
|---|---|---|
| **Stocks list** `/stocks` | ✅ clean | `atlas_lens_scores_daily`, `instrument_master`, `technical_daily` |
| **Stock detail** `/stocks/[s]` | ✅ clean | `atlas_lens_scores_daily`, `instrument_master`, `technical_daily`, `ohlcv_stock`, `financials_quarterly`, `lens_filings`, `lens_shareholding`, `delivery_daily`, `mv_sector_cards`, `atlas_fund_scorecard`, `atlas_universe_funds`, `de_etf_holdings`, `de_etf_master`, `atlas_etf_scorecard`, `policy_registry` |
| **ETF list** `/etfs` | ✅ clean | `de_mf_master`, `de_etf_holdings`, `atlas_lens_scores_daily`, `instrument_master`, `technical_daily` |
| **ETF detail** `/etfs/[t]` | ✅ clean | same as ETF list + `ohlcv_etf`, `index_prices` |
| **Funds list** `/funds` | ✅ clean | `de_mf_holdings`, `de_mf_master`, `de_mf_nav_daily`, `instrument_master` |
| **Sectors list** `/sectors` | ⚠️ | `mv_sector_cards`, `mv_sector_breadth`, `mv_sector_rrg` (fs) · `atlas_index_metrics_daily`, `atlas_sector_master` (fs) · **`public.de_index_prices`** |
| **Sector detail** `/sectors/[x]` | ⚠️ | `mv_sector_deepdive`, `sector_lens_daily`, `financials_quarterly` (fs) · **`public.de_index_prices`** · deepdive MV is built upstream from `atlas.*` |
| **Market Pulse** `/` | ⚠️ heavy | fs scorecards + **`atlas.atlas_market_regime_daily`, `atlas_sector_metrics_daily`, `atlas_sector_signal_unified`, `atlas_signal_calls`, `atlas_stock_state_daily`, `atlas_universe_stocks`, `mv_breakout_candidates`, `mv_deterioration_watch`** + **`public.de_equity_ohlcv`** |
| **Fund detail** `/funds/[id]` | ⚠️ heavy | fs (`atlas_fund_scorecard`, `atlas_fund_metrics_daily`, …) + **`atlas.atlas_fund_decisions_daily`, `atlas_fund_lens_monthly`, `atlas_fund_signal_unified`, `atlas_stock_metrics_daily`, `atlas_stock_signal_unified`, `atlas_universe_stocks`** + **`public.de_mf_holdings`, `de_mf_nav_daily`** |

**5 pages are clean. 4 still read outside the schema** — Market Pulse and Fund detail
are the worst, which is also why Fund detail looks shallow (the `atlas.*` joins it depends
on are stale/empty).

## 3. Where the 113.2% came from (it should not exist — you're right)

- The list heatmap reads `foundation_staging.mv_sector_cards.ret_12m`.
- That mirrors `atlas.mv_sector_cards`, whose `ret_12m` was computed (migration 102) as
  **`rs_12m + nifty500_ret_12m`** — a *reconstructed* return, not a real one — sourced from
  `atlas.atlas_sector_metrics_daily.rs_12m` + `atlas.atlas_index_metrics_daily`.
- On the stale **2026-05-29** row that the frontend was anchoring to, that reconstruction =
  **113.2%**. It is an artifact of a wrong formula on an old row. It is not a real return.
- The REAL number = `bottomup_ret_12m` (holdings-weighted, corp-action-adjusted) ≈ **0.9%**,
  lineage: `ohlcv_stock` → `technical_daily` (per-stock adj returns) → sector bottom-up
  aggregate → `mv_sector_cards.ret_12m`. **The `rs+nifty` reconstruction column should be deleted.**

## 4. Proposed canonical schema — ONE schema, ≤ ~20 core tables

Everything (raw + derived) in a single schema (e.g. `atlas`). State/ingest housekeeping
(`*_state`, `compute_state`, `backfill_state`, `ingest_run` — 8 tables) moves to a separate
`ops` schema and does not count.

**Raw inputs (10):**
1. `instrument` — every stock/ETF/index/fund + sector map (498 stocks → 21 sectors) [merges instrument_master + universe_etfs + universe_funds]
2. `ohlcv` — daily adjusted prices: stocks + ETFs + indices [merges ohlcv_stock + ohlcv_etf + index_prices]
3. `financials` — quarterly + annual + screener ratios [merges financials_quarterly + financials_annual + screener_ratios]
4. `corp_action` [merges corp_action + corp_action_event]
5. `filings` — NSE announcements [lens_filings]
6. `ownership` — insider + shareholding + bulk-deals + MF holdings [merges lens_insider + lens_shareholding + lens_bulk_deals + de_mf_holdings]
7. `fund` — MF master + NAV [merges de_mf_master + de_mf_nav_daily]
8. `etf` — ETF master + holdings [merges de_etf_master + de_etf_holdings]
9. `policy_registry`
10. `thresholds`

**Computed (≈8):**
11. `technical_daily` — per-stock technicals + adjusted returns
12. `lens_scores_daily` — the six-lens journal (the core output)
13. `sector_daily` — ONE table: sector returns + breadth + RS + verdict [replaces mv_sector_cards + mv_sector_breadth + mv_sector_rrg + mv_sector_deepdive]
14. `etf_scorecard`
15. `fund_scorecard`
16. `index_metrics_daily`
17. `market_regime_daily`
18. `sector_master` — sector → NSE index (21 rows, the canonical taxonomy)

≈ **18 core tables, one schema.** Then `atlas.*` (165) and `public.*` (104) get dropped.

## 5. The honest tension

This is the right end-state and it kills the whole class of bugs you've been hitting. But it
is a real migration: re-point every query + re-target the compute to write the new tables.
It cannot be both "done properly" AND "done before tomorrow's board." So the decision is
yours: (a) do this consolidation now and slip the board, (b) a scoped version — collapse the
4 sector MVs into `sector_daily` + kill the `rs+nifty` reconstruction + get the 4 dirty pages
onto `foundation_staging` (the highest-impact subset) before the board, or (c) board on the
current data with the orphans/Defence fixed, consolidate right after.
