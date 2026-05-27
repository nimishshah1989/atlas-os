# F.0 Audit · /v6/etfs/GOLDBEES vs 07a-etf-goldbees.html

**Audit date:** 2026-05-27
**Live URL:** https://atlas.jslwealth.in/v6/etfs/GOLDBEES (HTTP 200)
**Mockup file:** ~/.gstack/projects/atlas-os/designs/v6-redesign-20260526-mockups/07a-etf-goldbees.html
**Verdict:** minor

## Section presence

| Section (from mockup) | One-line spec | Live status | Notes |
|---|---|---|---|
| Breadcrumb | Atlas › ETFs › GOLDBEES | present | `ETFDetailClient.tsx` or page renders breadcrumb via `DataSourceBanner` and back-link |
| Page header | Mono 44px ticker + BUY stamp + serif 22px full name + meta chips (category, AMC, underlying, AUM, ADV, TER, age, inception) | present | `ETFHero.tsx` renders ticker, action stamp, full name, and meta chips; layout confirmed in component |
| Topbar live price | "NAV ₹62.84 · Mkt ₹62.86 · Premium +3bps · date" in topbar-right | absent | Live topbar shows only "as-of date"; no live NAV/market-price/premium in the topbar |
| 6-tile verdict strip | 6 tiles: 12M return / Tracking error 60d / Premium to NAV / ADV 30d avg / AUM / TER 5Y avg | present | `ETFHero.tsx` renders verdict strip; tiles from `ETFHeroData` |
| Multidim price chart | 360px 4-lane chart (price + S/R + RS-signal diamonds + volume + 20D-MA) | absent | No price chart on ETF detail page |
| NAV vs price chart | 240px line chart: NAV and market price overlaid, with premium/discount band shaded | absent | No NAV-vs-price chart on ETF detail page |
| Tracking error chart | 200px chart showing 60-day rolling tracking error vs category median over time | absent | No tracking error time-series chart |
| Peer comparison table | Table of ETFs in same category: ticker, 12M return, tracking error, premium, AUM, expense ratio, action chip; current ETF highlighted | absent | No peer comparison table |
| Macro overlay row (3 cards) | 3 cards: underlying macro driver (e.g. Gold price) + correlation with underlying + macro narrative | absent | No macro overlay section for ETFs |
| Composition cards (2-col) | Left: top-10 index constituents with name + weight; Right: sector allocation breakdown | partial | Holdings tab shows top holdings from `atlas_etf_scorecard.top_holdings` JSONB; sector allocation absent |
| Overview tab | RankDecompositionCards + MultiBenchmarkRSWaterfall | present | `ETFDetailClient.tsx` Overview tab confirmed |
| Holdings tab | Top holdings list | present | Holdings tab confirmed |
| Audit tab | Audit trail (lazy loaded) | present | `AuditTrailTab` lazy loaded in `ETFDetailClient.tsx` |
| Footnote | Data disclaimer + methodology | absent | No footnote |

## Token compliance

- [x] `ETFHero.tsx` and `ETFDetailClient.tsx` use semantic tokens throughout. Clean.
- [x] Tab nav: `border-teal text-teal` for active tab. Clean.
- [x] Fonts: `font-serif`, `font-sans`, `font-mono` only. Clean.
- [ ] Note: `buildRankData()` in `frontend/src/app/v6/etfs/[iid]/page.tsx` line ~50 uses `pctile = rawNum` which approximates percentile as the raw score — this is a computation shortcut, not a token violation.

## Component reuse

- [x] `ETFHero`, `RankDecompositionCards`, `MultiBenchmarkRSWaterfall`, `DataSourceBanner`, `AuditTrailTab` — all from `components/v6/`. Correct.
- [ ] Missing: `ETFPriceChart` — no multidim price chart component.
- [ ] Missing: `ETFNAVvsPriceChart` — no NAV-vs-market-price line chart.
- [ ] Missing: `TrackingErrorChart` — no tracking error time-series chart.
- [ ] Missing: `ETFPeerTable` — no peer comparison table.
- [ ] Missing: `MacroOverlayRow` — no macro driver cards for ETFs.
- [ ] Missing: sector allocation in Holdings tab.

## Data correctness

- [x] Ticker, full name, category, AMC, AUM, TER, inception render from `getEtfDetail()`. Real data.
- [x] 6-tile verdict strip: 12M return, tracking error, AUM, expense ratio all real values.
- [x] RankDecompositionCards: rank components from ETF scorecard (matrix conviction, sector strength, tracking quality, AUM bracket, liquidity, expense ratio). Real.
- [ ] Premium to NAV tile: present in hero strip but uses `raw_metrics` JSONB; may show `—` if `nav_premium_bps` not stored.
- [ ] ADV (average daily volume) tile: from `raw_metrics` JSONB; may show `—`.
- [ ] RS Waterfall: `buildWaterfallData()` in page.tsx line ~76-80 uses `etfRet * 0.9` as cohort proxy — synthetic, not real category median.
- [ ] Multidim chart: absent — no price data fetched.
- [ ] NAV-vs-price chart: absent.
- [ ] Tracking error chart: absent — only single `tracking_error` value shown, not history.
- [ ] Peer table: absent.
- [ ] Macro overlay: absent.

## Per-gap closure plan

1. **Multidim price chart absent** — file: create `frontend/src/components/v6/ETFPriceChart.tsx`; reuse same pattern as `StockPriceChart` (when built); render OHLCV from `atlas_etf_price_history` or `atlas_price_history` with RS-signal diamonds from `atlas_etf_signal_calls`, 20D-MA, volume pane. Wire into `ETFDetailClient.tsx` Overview tab above rank decomposition.

2. **NAV-vs-price chart absent** — file: create `frontend/src/components/v6/ETFNAVvsPriceChart.tsx`; Recharts LineChart with two series (NAV + market price) + shaded premium/discount band; data from `atlas_etf_metrics_daily` (nav_price + market_price over 90-180 days). Wire into Overview tab below the price chart.

3. **Tracking error chart absent** — file: create `frontend/src/components/v6/TrackingErrorChart.tsx`; rolling 60D tracking error vs category median; data from `atlas_etf_metrics_daily.tracking_error_60d` history. Wire into Overview tab.

4. **Peer comparison table absent** — file: create `frontend/src/components/v6/ETFPeerTable.tsx`; query: `getETFPeers(category, snapshotDate)` in `lib/queries/v6/etfs.ts`; render table with current ETF highlighted. Wire into a new "Peers" tab or below the composition section.

5. **Macro overlay row absent** — file: create `frontend/src/components/v6/MacroOverlayRow.tsx`; 3 cards: underlying index/commodity (Gold, Nifty50, Nifty Bank etc.) with mini price chart + correlation coefficient + narrative. Data requires mapping `etf_category` → macro driver and fetching macro time-series. Wire into ETF detail page for commodity and thematic ETFs.

6. **RS Waterfall cohort is synthetic** — file: `frontend/src/app/v6/etfs/[iid]/page.tsx` `buildWaterfallData()` line ~76; change: add a query `getETFCategoryReturns(category, snapshotDate)` to fetch the actual category-median return from `atlas_etf_metrics_daily`; use real value instead of `etfRet * 0.9`.

7. **Topbar live price absent** — this is a low priority since the topbar is a global layout component; a quick win would be adding NAV and premium to the `ETFHero` verdict strip footnote text rather than the topbar.
