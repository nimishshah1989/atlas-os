# F.0 Audit · /v6/stocks/STLTECH vs 05a-stock-reliance.html

**Audit date:** 2026-05-27
**Live URL:** https://atlas.jslwealth.in/v6/stocks/STLTECH (HTTP 200; RELIANCE used as reference pattern)
**Mockup file:** ~/.gstack/projects/atlas-os/designs/v6-redesign-20260526-mockups/05a-stock-reliance.html
**Verdict:** minor

## Section presence

| Section (from mockup) | One-line spec | Live status | Notes |
|---|---|---|---|
| Breadcrumb | Atlas › Stocks › SYMBOL | present | Page renders `← Stocks` back link via `Link` in `frontend/src/app/v6/stocks/[iid]/page.tsx` |
| Page header | Mono 44px ticker + action stamp (BUY/WATCH/AVOID) + company name (serif 22px) + meta chips (sector, tier, stage, market cap) | present | `StockHero.tsx` renders ticker, action verb, conviction tape, meta chips. Layout uses `font-mono text-[2.75rem]`; close to 44px. |
| Head conviction tape | 4-segment mini tape (1m/3m/6m/12m) inline with ticker | present | `StockHero.tsx` renders `ConvictionTape` with 4-segment visual |
| 6-tile verdict strip | 6 tiles: RS%ile / 6M return / Deployment / Max DD / Sector vs index / Cross-rule depth | present | `StockHero.tsx` renders 6-tile strip; tiles confirmed in component code |
| Overview tab | RankDecompositionCards + MultiBenchmarkRSWaterfall + MultiTenureReturnsTable + FundsHolding section | present | `StockDetailClient.tsx` Overview tab renders all these components |
| Multidim price chart | 380px 4-lane chart (price + S/R + RS diamonds + volume + 20D-MA) with timeframe chips | absent | No multidim price chart on the stock detail page; Technicals tab has technicals data (EMA, drawdown, etc.) but no visual chart |
| Cell-fire timeline | 130px timeline SVG showing when cells fired (POSITIVE/NEGATIVE) over 12M, per-tenure colored bars | absent | No cell-fire timeline in the live stock detail page |
| Cell methodology grid | 2-col layout: left = 3-row table of matching cells with cell_id, meta, state chip, IC; right = predicate panel (feature/comparator/value/check rows) | partial | `StockDetailClient` Overview tab shows `RankDecompositionCards` (IC breakdown by tenure) but NOT the actual matching cell IDs, their conditions, or the predicate DSL panel |
| Cross-cell visualization | 5×N grid of "pips" — one pip per cell, colored if fired; shows cross-rule depth visually | partial | `CrossRuleDepthData` is fetched and shown in `StockHero.tsx` as a dot-count badge (`depth / total`), but NOT as the 5-col pip grid from the mockup |
| Technicals tab | EMA 200 distance, ATH drawdown, current price, volatility, volume data | present | `StockDetailClient` has a Technicals tab; `StockTechnicals` data rendered |
| Audit tab | Audit trail table (entry date, cell, direction, confidence, outcome) | present | `AuditTrailTab` (lazy loaded) in `StockDetailClient.tsx` |
| Footnote | Methodology disclaimer + data-as-of | absent | No footnote on stock detail page |

## Token compliance

- [x] `StockHero.tsx` uses `bg-signal-pos`, `text-signal-neg`, `border-teal`, `bg-paper-soft` etc. Clean.
- [x] `StockDetailClient.tsx` tab nav uses `border-teal text-teal` for active state. Clean.
- [x] Fonts: `font-mono`, `font-sans`, `font-serif` throughout. Clean.
- [ ] `RegimeHero.tsx`-like hex issue does NOT appear in stock components. All clean for stock detail.

## Component reuse

- [x] `StockHero`, `MultiBenchmarkRSWaterfall`, `RankDecompositionCards`, `MultiTenureReturnsTable`, `GradeChip`, `AuditTrailTab` — all `components/v6/`. Correct.
- [ ] Missing: multidim chart — no `StockPriceChart` or `MultidimChart` component.
- [ ] Missing: cell-fire timeline SVG — no `CellFireTimeline` component.
- [ ] Missing: cell-condition predicate panel — no `CellPredicatePanel` component; `CellRulePlainEnglish.tsx` exists in `components/v6/` but is not used in stock detail.
- [ ] Missing: cross-cell pip grid — `CrossRuleDepthData` drives only a dot count, not the full pip grid.

## Data correctness

- [x] Ticker, action verb (derived via `deriveActionVerb()`), conviction tape directions all real.
- [x] 6-tile strip: RS%ile, return values, deployment multiplier, max drawdown, sector delta — all populated from `getInstrumentDetail()`.
- [x] RankDecompositionCards: IC scores by tenure from `atlas_conviction_daily`. Real but note: components use `ic * 100` which may show small or zero values when conviction tape has no POSITIVE/NEGATIVE records for this stock.
- [x] MultiBenchmarkRSWaterfall: built from `ret_6m` with stub cohort/benchmark values (noted in code comment). Partial — real ret_6m but synthetic benchmark legs.
- [x] MultiTenureReturnsTable: real multi-tenure returns from `getMultiTenureReturns()`.
- [ ] Cell-fire timeline: absent — no data.
- [ ] Predicate DSL panel: absent — `CellRulePlainEnglish.tsx` exists but not wired to stock detail.
- [ ] RS Waterfall benchmark legs: comment in `buildWaterfallData()` at line ~42 says `nifty50_return: '0', nifty500_return: '0'` — synthetic zeros, not real Nifty50/500 returns.

## Per-gap closure plan

1. **Multidim price chart absent** — file: create `frontend/src/components/v6/StockPriceChart.tsx`; render OHLCV from `atlas_price_history` (or equivalent) with S/R levels, RS-signal diamond overlays (from `atlas_signal_calls`), 20D-MA, volume bars. Timeframe chips: 3M/6M/1Y/3Y. Wire into `StockDetailClient.tsx` Overview tab above `RankDecompositionCards`. This is a foundational chart gap present in mockup 05a.

2. **Cell-fire timeline absent** — file: create `frontend/src/components/v6/CellFireTimeline.tsx`; 12-month SVG timeline showing diamond markers where cells fired (from `atlas_signal_calls` for this `instrument_id`), per-tenure colored horizontal bars. Data query: `getSignalCallsByIid()` already exists in `lib/queries/v6/recent_signal_calls.ts` — extend to return full 12M history. Wire into Overview tab after the price chart.

3. **Cell predicate panel absent** — file: `frontend/src/components/v6/StockDetailClient.tsx` Overview tab; add a section that lists the matching cells (from `atlas_conviction_daily` for this iid today) and for each cell show `CellRulePlainEnglish` (component already exists at `components/v6/CellRulePlainEnglish.tsx`). This closes the "cell methodology" gap.

4. **Cross-cell pip grid: only dot-count shown** — file: `frontend/src/components/v6/StockHero.tsx`; change: replace the dot-count badge with the 5-col pip grid (one pip per cell, filled when fired); the `CrossRuleDepthData.depth` field provides the count but not individual cell IDs; extend `fetchCrossRuleDepth()` in `frontend/src/app/v6/stocks/[iid]/page.tsx` to return the actual cell_ids that fired, then render as labeled pips.

5. **RS Waterfall benchmark legs are synthetic zeros** — file: `frontend/src/app/v6/stocks/[iid]/page.tsx` `buildWaterfallData()` at line ~42; change: add a `getNiftyReturns(snapshotDate)` query to `lib/queries/v6/` to fetch Nifty50 and Nifty500 actual returns from `atlas_index_ohlcv`; pass as `nifty50_return` and `nifty500_return` instead of `'0'`.
