# F.0 Audit Summary · v6 9-Page Design-Review Gate

**Audit date:** 2026-05-27
**Auditor:** Forge Implementer subagent
**Scope:** 9 live pages vs locked mockups in `~/.gstack/projects/atlas-os/designs/v6-redesign-20260526-mockups/`

---

## Verdict table

| # | Live route | Mockup | Verdict | Gap count | Worst gap |
|---|---|---|---|---|---|
| 01 | `/regime` (404) → `/v6/regime` | `01-market-regime.html` | **major** | 7 | Route is 404; 4-signal tiles, journey matrix 5 rows, conviction section all absent |
| 04 | `/v6/sectors` | `04-sectors.html` | **major** | 7 | Hero enriched readout, multi-window heatmap, sector card grid all absent; RRG side panel absent |
| 04a | `/v6/sectors/Energy` | `04a-sector-energy.html` | **major** | 5 | Multidim price chart, RS multi-baseline grid, sub-industry decomp all absent |
| 05 | `/v6/stocks` | `05-stocks.html` | **major** | 7 | Hero stories, bubble+matrix 2-up, RS trajectories, stock card grid all absent |
| 05a | `/v6/stocks/STLTECH` | `05a-stock-reliance.html` | **minor** | 5 | Multidim price chart, cell-fire timeline, predicate panel absent; waterfall benchmarks synthetic |
| 06 | `/v6/funds` | `06-funds.html` | **major** | 5 | Hero stories, AMC quartile bars, fund card grid, NAV trajectory strip absent |
| 06a | `/v6/funds/F00001EBDX` | `06a-fund-ppfas.html` | **minor** | 6 | NAV chart, drawdown chart, peer table, quartile timeline, SWITCH check card absent |
| 07 | `/v6/etfs` | `07-etfs.html` | **major** | 6 | Category bands, AMC tiles, NAV-vs-price scatter, ETF card grid, hero stories absent |
| 07a | `/v6/etfs/GOLDBEES` | `07a-etf-goldbees.html` | **minor** | 7 | Price chart, NAV-vs-price chart, tracking error chart, peer table, macro overlay absent |

**Totals:** 5 major, 4 minor, 0 clean.

---

## Score breakdown

| Page | Sections present | Sections partial | Sections absent | Token violations | Data issues |
|---|---|---|---|---|---|
| Regime | 3 | 2 | 4 | 1 (hex colors in RegimeHero) | 2 (4-input signals, transition probs) |
| Sectors list | 3 | 1 | 6 | 0 | 2 (flat trajectory stub, hero readout) |
| Sector detail | 5 | 1 | 5 | 0 | 1 (no price/RS history) |
| Stocks list | 4 | 1 | 5 | 0 | 2 (no firing-today, no stories) |
| Stock detail | 8 | 2 | 3 | 0 | 1 (waterfall benchmarks synthetic) |
| Funds list | 4 | 1 | 5 | 0 | 1 (peer_quartile proxy accuracy) |
| Fund detail | 7 | 2 | 5 | 0 | 3 (NAV history, Sharpe, alpha) |
| ETFs list | 3 | 1 | 6 | 0 | 1 (conviction tape all NEUTRAL) |
| ETF detail | 6 | 1 | 6 | 0 | 2 (waterfall cohort synthetic, premium `—`) |

---

## Cross-cutting patterns

### 1. Missing "visualization" charts on every page (8 of 9 pages)

The mockups specify a **multidim price chart** (4-lane: price + S/R + RS diamonds + volume + 20D-MA) on stock detail, sector detail, and ETF detail pages. None of these three pages have any price chart. Additionally, the list pages (sectors, stocks, funds, ETFs) all specify **bubble chart + card grid + story block** sections above the main table — the bubble chart is present on sectors/funds/ETFs but the card grids and story blocks are universally absent.

The root cause: no `StockPriceChart`, `SectorPriceChart`, or `ETFPriceChart` component exists in `components/v6/`. This is the highest-impact gap — it affects 3 detail pages and is called out explicitly in the mockup's `section-sub` text on every deep-dive page.

### 2. Hero stories / 4-column narrative block absent on all list pages (4 of 4 list pages)

Every list page mockup (stocks, funds, ETFs, sectors) has a 4-column story block at the top: "Entering BUY / Entering SELL / High confidence / Exits" (stocks), "Switch-In / Switch-Out / Hold / New" (funds), "BUY / Watch / Strong-track / New" (ETFs), "Leading / Lagging / Watch / Regime context" (sectors). None of these are built. They require:
- For stocks: `atlas_signal_calls` delta (today vs yesterday)
- For funds: `atlas_switch_rules` proposal grouping
- For ETFs: grouping from `atlas_etf_scorecard.is_atlas_leader` + tracking error buckets
- For sectors: state grouping from `getSectorsForDate()`

The data largely exists; the missing part is the UI component.

### 3. Page title fonts are undersized (6 of 9 pages)

The mockup specifies `44px` serif titles for all pages. Live implementations use `text-2xl lg:text-3xl` (equivalent to ~30-36px). The detail pages (stock, fund, ETF) that use `text-[2.75rem]` or `text-[36px]` in their hero components are closer but still short. Breadcrumbs are also absent from list pages (sectors, stocks, funds, ETFs pages show no `Atlas › Sectors` breadcrumb).

### 4. Peer comparison tables absent on all detail pages (detail pages: sectors, stocks, funds, ETFs)

Every detail mockup has a peer comparison table:
- Stock: other stocks in same tier/sector
- Sector: sub-industry breakdown table
- Fund: category peers with quartile pills
- ETF: ETFs in same category

None of the four detail pages implement this. The live detail pages have `RankDecompositionCards` (score decomposition) which shows rank within category as a number, but no actual table of peers. This is a design-review blocker for each detail page.

### 5. Token violation: inline hex colors in RegimeHero (1 page)

`frontend/src/components/v6/RegimeHero.tsx` lines 33-40: `regimeTailwindBg()` returns hardcoded hex strings in Tailwind JIT format (`bg-[#2F6B43]` etc.) instead of semantic token classes. The correct tokens exist: `bg-signal-pos`, `bg-teal`, `bg-signal-warn`, `bg-signal-neg`. This is a 1-line fix per color.

### 6. Synthetic data in waterfall benchmarks (2 pages: stock detail, ETF detail)

`buildWaterfallData()` in both `frontend/src/app/v6/stocks/[iid]/page.tsx` (line ~42) and `frontend/src/app/v6/etfs/[iid]/page.tsx` (line ~76) set `nifty50_return: '0'`, `nifty500_return: '0'`, and `cohort_return: etfRet * 0.9` — synthetic values. Both files have inline comments flagging this as a v6.1 TODO. `MultiBenchmarkRSWaterfall` renders these as zero bars, which is misleading.

### 7. 12-week trajectory sparkline is flat stub on sectors list (1 page)

`SectorsListV6.tsx` `buildTrajectory()` at ~line 133 returns `Array(12).fill(rank)` — a flat line. The sparkline dots render as a horizontal line instead of a trajectory. This requires `getWeeklyRankHistory()` query on `atlas_sector_states_daily`. The sparkline SVG rendering is correct; only the data is stub.

---

## Pages by severity

**Most gaps (7+ each):** Regime page, Stocks list, Sectors list  
**Least gaps (5):** Stock detail, Funds list  
**Detail pages trend minor:** Stock detail (5 gaps), Fund detail (6), ETF detail (7) — these have strong foundations (hero strips, tab layouts, real data) but lack the chart layers.

---

## Phase C implementation priority order

| Priority | Gap | Pages affected | Effort estimate |
|---|---|---|---|
| P0 | Fix `/regime` 404 — redirect to `/v6/regime` | 1 | Trivial (1-line redirect) |
| P0 | Replace inline hex colors in `RegimeHero.tsx` | 1 | Trivial (4 lines) |
| P0 | Fix waterfall synthetic benchmarks (fetch real Nifty returns) | 2 | Small (1 new query + wire) |
| P1 | Build `StockPriceChart` / `SectorPriceChart` / `ETFPriceChart` (multidim 4-lane) | 3 | Large (new Recharts component + data query) |
| P1 | Build hero stories blocks (4-col) for stocks/funds/ETFs/sectors list pages | 4 | Medium per page (data exists, UI missing) |
| P1 | Build peer comparison tables for stock/fund/ETF detail pages | 3 | Medium per page (1 new query + table component) |
| P1 | Fix 44px page title + add breadcrumb on list pages | 6 | Small (CSS + nav changes) |
| P2 | Build multi-window heatmap for sectors list | 1 | Medium |
| P2 | Build ETF category bands + AMC tile row | 1 | Small |
| P2 | Build NAV growth + drawdown charts for fund detail | 1 | Medium |
| P2 | Build NAV-vs-price + tracking error charts for ETF detail | 1 | Medium |
| P2 | Add 4-signal input tiles + journey matrix rows to regime page | 1 | Medium |
| P3 | Build sector card grid, stock card grid, fund card grid, ETF card grid | 4 | Medium per page |
| P3 | Fix 12W trajectory sparkline stub on sectors | 1 | Small (1 new query) |
| P3 | Build quartile timeline, SWITCH check card for fund detail | 1 | Medium |
| P3 | Build macro overlay row for ETF detail | 1 | Medium |

---

## Definition of "design-review PASS" per page

A page achieves `/design-review` PASS when:
1. All mockup sections are either present or explicitly deferred with a documented reason.
2. No token violations (no inline hex/rgba, no Tailwind color-500 classes, no hardcoded hex).
3. All major data fields populated (no `—` or `0` synthetic values in primary tiles).
4. Page title is 44px serif; breadcrumbs present.
5. Peer comparison table (or equivalent depth comparison) present on detail pages.
6. Chart sections: at minimum the price chart present on stock/sector/ETF detail.

No page currently meets this bar. The stock detail page (05a) and fund detail page (06a) are closest.
