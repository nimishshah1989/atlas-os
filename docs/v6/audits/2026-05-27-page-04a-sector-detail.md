# F.0 Audit · /v6/sectors/Energy vs 04a-sector-energy.html

**Audit date:** 2026-05-27
**Live URL:** https://atlas.jslwealth.in/v6/sectors/Energy (HTTP 200)
**Mockup file:** ~/.gstack/projects/atlas-os/designs/v6-redesign-20260526-mockups/04a-sector-energy.html
**Verdict:** major

## Section presence

| Section (from mockup) | One-line spec | Live status | Notes |
|---|---|---|---|
| Breadcrumb | Atlas › Sectors › Energy | present | `SectorDetailClient.tsx` renders breadcrumb via page.tsx |
| Page header | Serif 44px sector name + OVERWEIGHT stamp + 15px sub-line | partial | Live shows sector name + `StateBadge`; no large serif title at 44px — uses `font-serif text-2xl lg:text-3xl` (~30-36px vs mockup's 44px); no `page-stamp` color badge inline with the title |
| Verdict strip (6 tiles) | 6-tile strip: sector rank / RS% / breadth % / 1M return / vol / sector state with feet text | present | `SectorDetailClient` renders a 6-tile verdict strip from `sector` data |
| Multidim price chart | 360px multi-pane chart (price + S/R levels + RS-signal diamonds + volume + 20D-MA) with timeframe chips | absent | No multidim chart on the sector detail page; `SectorDetailClient` has `BubbleRiskReturnChart` + `SectorBreadthPanel` but no multidim price chart for the sector index |
| Timeframe chip controls | 3M/6M/1Y/3Y period toggle + Daily/Weekly toggle | absent | No chart controls on the sector detail page |
| RS multi-baseline grid | Table: sector RS vs 5+ baselines (Nifty 50, Nifty 500, Midcap150, Smallcap250, Gold, etc.) across multiple timeframes; colored heat cells | absent | No RS multi-baseline grid; live shows `SectorBreadthPanel` (breadth + stage breakdown) instead |
| Sub-industry decomposition | 2-col layout: sub-industry table (name, stock count, breadth %, RS delta) + allocation donut/bar chart | absent | No sub-industry breakdown on the live page |
| Constituent stocks table | Dense table: symbol, company name, CTS stage, conviction tape, 1M/3M/6M/12M returns, RS %ile, portfolio badge | present | `SectorDetailClient.tsx` renders constituent table with `ColumnChooser`, `ConvictionTape`, `PortfolioBadge`; returns columns present |
| SectorBookStrip | Portfolio vs benchmark exposure bar for this sector | present | `SectorBookStrip` imported and rendered |
| SectorBreadthPanel | Stage breakdown bars (Stage 1/2a/2b/3/4), breadth % current | present | `SectorBreadthPanel` imported and rendered |
| BubbleRiskReturnChart | Risk/return scatter for constituents | present | `BubbleRiskReturnChart` rendered with constituent stocks as bubbles |
| Footnote | Data-as-of + methodology link | absent | No footnote block |

## Token compliance

- [x] `SectorDetailClient.tsx` uses semantic tokens throughout: `bg-signal-pos/15`, `text-signal-pos`, `bg-signal-neg/15`, `bg-paper-deep`, `border-paper-rule`, etc. Clean.
- [x] `CHIP_CLS` record uses opacity-based `bg-signal-pos/15` etc. — correct pattern.
- [x] Fonts: `font-serif`, `font-sans`, `font-mono` only. Clean.

## Component reuse

- [x] Page uses `SectorBookStrip`, `SectorBreadthPanel`, `BubbleRiskReturnChart`, `PortfolioBadge`, `ConvictionTape`, `StateBadge`, `ColumnChooser` — all from `components/v6/` or `components/ui/`. Proper.
- [ ] Missing: multidim price chart — no `SectorPriceChart` or reuse of the multidim chart pattern.
- [ ] Missing: RS multi-baseline grid — no `MultiBenchmarkRSGrid` component for sectors.
- [ ] Missing: sub-industry decomposition — no `SubIndustryTable` component.

## Data correctness

- [x] Constituent stocks table: symbol, name, stage, conviction tape, 1M/3M return, RS %ile, portfolio badge all render real data.
- [x] SectorBookStrip: exposure delta renders real data from `getSectorBookExposure()`.
- [x] SectorBreadthPanel: stage counts and breadth % render real data from `getSectorBreadth()`.
- [x] Hero strip tiles: RS%, breadth, state all populated from `getSectorsForDate()`.
- [ ] Multidim chart: absent — no price data rendered.
- [ ] RS multi-baseline grid: absent — no data populated.
- [ ] Sub-industry decomposition: absent — no data populated.

## Per-gap closure plan

1. **Multidim price chart absent** — files: create `frontend/src/components/v6/SectorPriceChart.tsx` using Recharts; render sector index OHLCV (from `atlas_index_ohlcv` or equivalent) with S/R overlays, RS-signal diamonds, volume pane, 20D-MA. Wire into `SectorDetailClient.tsx` after the breadth panel. The data query would need a `getSectorPriceHistory(sectorName, days)` in `lib/queries/v6/sectors.ts`.

2. **RS multi-baseline grid absent** — files: create `frontend/src/components/v6/SectorRSGrid.tsx`; table with the sector vs 5+ baselines across 1M/3M/6M/12M; colored heat cells using the pos/neg heatmap pattern from `SectorHeatmap`. Data: `atlas_sector_rs_history` or compute from `atlas_sector_metrics_daily`; wire into `SectorDetailClient.tsx`.

3. **Sub-industry decomposition absent** — files: create `frontend/src/components/v6/SubIndustryTable.tsx`; render sub-industries within the sector (from `atlas_universe_stocks.sub_industry`) with stock count, breadth %, RS delta. Wire into `SectorDetailClient.tsx`. Query: `getSubIndustryBreakdown(sectorName, snapshotDate)` in `lib/queries/v6/sectors.ts`.

4. **Page title size too small vs mockup** — file: `frontend/src/app/v6/sectors/[name]/page.tsx` (the page header rendered before `SectorDetailClient`); change: the breadcrumb div uses `font-sans text-xs` for the sector name; `SectorDetailClient` needs an explicit h1 with `font-serif text-[44px]` matching the mockup's `.page-title` style. Currently the sector name only appears in the breadcrumb, not as a standalone large title.

5. **OVERWEIGHT stamp inline with title absent** — file: `frontend/src/components/v6/SectorDetailClient.tsx`; change: add a `page-stamp`-style badge next to the sector name in the page header, styled per sector state (`bg-signal-pos text-paper` for Overweight, `bg-signal-neg text-paper` for Avoid, etc.).
