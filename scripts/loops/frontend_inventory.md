# Atlas frontend inventory (v4 replication base) — 2026-06-22

Durable reference for the page-by-page alignment. Source: full read of `frontend/src`
(Next.js app router). Chart tags: **TV** = TradingView (embed widget OR Lightweight
Charts wrapper `AtlasLightweightChart`); **CUSTOM** = Recharts / D3 / hand-SVG.

## Navigation IA (TopNav.tsx, v6.2)

| Group | Page | Route |
|---|---|---|
| **MARKETS TODAY** | Regime | `/` |
| | India Pulse | `/india-pulse` |
| **DEEP DIVE** | Markets RS | `/markets-rs` |
| | Sectors | `/sectors` (+ `/sectors/[sector]`) |
| | Stocks | `/stocks` (+ `/stocks/[symbol]`) |
| | ETFs | `/etfs` (+ `/etfs/[ticker]`) |
| | Funds | `/funds` (+ `/funds/[mstar_id]`) |
| **PORTFOLIOS** | Calls | `/calls` |
| | Custom Portfolios | `/portfolios` (+ `/[id]`, `/new`, `/[id]/analytics`) |
| **ADMIN** | Overview & Health | `/admin` (+ composite-proposals, weight-performance, validator, thresholds) |
| | Portfolio Setup | `/setup` (+ policy, new-portfolio) |
| **REPORTS** | Daily Brief | `/intelligence/daily-brief` |
| (not in nav) | Intelligence hub / Agents | `/intelligence`, `/intelligence/agents` |
| (not in nav) | Signals | `/signals` (+ `/[id]`) |
| (not in nav) | Strategies / Lab | `/strategies` (+ `/[id]`, `/lab/*`) |
| (not in nav) | Methodology | `/methodology` |
| (legacy, non-India) | Global | `/global` (+ `/country/[ticker]`) |
| (legacy, non-India) | US | `/us` (+ `/stocks`, `/etfs`, `/sectors/[name]`) |

## Page-by-page (what renders today)

### MARKETS TODAY
- **Regime (`/`)** — regime dashboard: RegimeVerdict, SignalScorecard, TodayWorklist, RegimeHeadline,
  IntradayNiftyStrip, **RegimeOverlayChart [CUSTOM Recharts]**, classifier inputs, Trend/Breadth/Momentum/
  Participation sections (**~13 IndicatorCharts [CUSTOM Recharts]**), RegimeJourney12w, TodayConvictionTabs.
  *Already partially merges India Pulse breadth table when LENS_V4=1.*
- **India Pulse (`/india-pulse`)** — HeroStrip(4 regime inputs), HeadlineIndices(8 cards), Breadth table,
  **Dispersion [CUSTOM Recharts]**, Volatility(VIX), TierLeadership, SectorHeatmap, **MacroCards sparklines
  [CUSTOM Recharts]**, narrative. Data: `mv_india_pulse` (nightly 20:30 IST).
- **Markets RS (`/markets-rs`)** — 4-card hero, 9×5 RS grid (baselines × windows), narrative,
  **6 detail charts [CUSTOM hand-SVG MultidimChartSvg]**.

### DEEP DIVE
- **Sectors (`/sectors`)** — SectorPulseGrid, hero readout, **SectorRRGChart [CUSTOM Recharts+SVG]**,
  SectorLensHeatmap (LENS_V4), multi-window heatmap, breadth panel.
- **Sector detail (`/sectors/[sector]`)** — verdict header, RS windows table, **RS ratio charts [TV
  Lightweight]**, top picks, constituents, **StrengthDist [CUSTOM Recharts]**, open signals, sub-industry.
- **Stocks (`/stocks`)** — hero stats, HeroStories, **ConvictionBubbleChart [CUSTOM Recharts]** + Matrix24Cell,
  **CompositeTrajectories [CUSTOM Recharts]**, SixPicks, LensRankingTable (LENS_V4), full screener.
- **Stock detail (`/stocks/[symbol]`)** — TraderViewHeader, EventHeader, GatesPanel + returns, LensVectorPanel
  (LENS_V4), SectorContextStrip, **Sparkline-vs-sector [TV Lightweight]**, **StockChartPanel [TV Advanced
  Chart]**, RSConfirmation, conviction decomp, **SparklineTrajectoryGrid (12) [CUSTOM Recharts]**, Lifecycle,
  **TVTechnicalAnalysis / TVFinancials / TVNews / TVCompanyProfile [TV widgets]**, PeerMatrix, ActButton.
- **ETFs (`/etfs`)** — hero, HeroStories, CategoryBands, AmcTileRow, **PremiumDiscountScatter [CUSTOM
  Recharts]**, **ETFBubbleChart [CUSTOM D3]**, screener + intelligence.
- **ETF detail (`/etfs/[ticker]`)** — hero, gates + returns, **TVMiniOverview [TV]**, **PriceMultidim180d
  [CUSTOM Recharts]**, NAV-vs-price gauge + tracking-error gauge [CUSTOM], **sparkline grid [CUSTOM Recharts]**,
  **TVTechnicalAnalysis / TVNews / TVCompanyProfile [TV]**, peers, leader holdings.
- **Funds (`/funds`)** — IndustrySnapshot, **BubbleRiskReturnChart [CUSTOM Recharts]**, SignatureMatrix
  [CUSTOM heatmap], ranked table. Data: `mv_fund_list_v6`.
- **Fund detail (`/funds/[mstar_id]`)** — header, commentary, **FundNavChart [CUSTOM Recharts]**, 3 Lens panels
  (**FundLens1 [CUSTOM Recharts]** + gates), **FundRiskPanel [CUSTOM Recharts ×3]**, **FundLensHistory [CUSTOM
  Recharts area]**, holdings table (look-through to stock detail via LinkedTicker), leader holdings, decisions.

### PORTFOLIOS / ADMIN / REPORTS
- **Calls (`/calls`)** — win-rate matrix (tier×tenor×dir), cell trajectories, **cumulative excess [CUSTOM
  Recharts]**, ledger.
- **Portfolios (`/portfolios`)** — list + detail (current vs target, policy, deterioration, rebalance).
- **Setup (`/setup`)** — policy + new-portfolio forms.
- **Admin (`/admin`)** — proposals, weight-performance (**IC sparkline [CUSTOM Recharts]**), validator, health.
- **Daily Brief (`/intelligence/daily-brief`)** — Claude narrative (SEBI-safe). Intelligence hub + Agents chat.

### NOT-IN-NAV / LEGACY
- **Signals (`/signals`)** — TV Pine alert feed + **TV embed [TV]**.
- **Strategies (`/strategies`)** — backtests: **EquityCurve / Drawdown / RegimeBreakdown [CUSTOM Recharts]**.
- **Methodology (`/methodology`)** — 7-tab explainer (no data).
- **Global (`/global`), US (`/us`)** — cross-border / US universe, **all CUSTOM D3+Recharts**. Non-India;
  candidates to drop for v4.

## Cross-cutting facts
1. **Two generations:** older `components/*` (mostly preserved) + newer `components/v6/*` (live). Most live
   pages already use v6.
2. **LENS_V4 gating today** touches only: home breadth table, `/stocks` LensRankingTable, `/stocks/[symbol]`
   LensVectorPanel, `/sectors` SectorLensHeatmap. ETFs/Funds NOT yet gated.
3. **Charts reality vs "all TradingView":** TradingView (widgets + Lightweight Charts) is the right home for
   ALL **price / time-series / technical** charts — price, NAV, RS-ratio, equity curve, drawdown, regime
   overlay, dispersion, macro sparklines, metric sparkline grids. Several already are TV; the rest are CUSTOM
   Recharts and should migrate. BUT TradingView canNOT render the **analytical/positioning** charts — RRG,
   bubble/scatter, breadth heatmaps, win-rate matrix, stacked-composition areas. Those are not price series;
   they stay bespoke (lightweight custom) or get redesigned. → needs an explicit FM call on scope.
4. **Frontend reads Postgres directly** (server components, `lib/queries/*`), no Python API in between; many
   pages are MV-backed (`mv_india_pulse`, `mv_sector_*`, `mv_etf_*`, `mv_fund_list_v6`, `mv_stock_landscape`).
   v4 wiring = feed these (or the snapshot) FRESH decile/leadership data, not the stale composite column.
