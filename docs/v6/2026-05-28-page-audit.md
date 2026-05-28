# v6 Page Audit — 2026-05-28

## Summary
- **Pages DONE**: 2/8 (Market Regime + India Pulse mapped, mostly stub/partial data)
- **Pages PARTIAL**: 3/8 (Markets RS, Sectors, ETFs routed + components exist, limited sections live)
- **Pages MISSING**: 3/8 (Stocks detail, Funds detail, Calls ledger not yet final routes)
- **Route deduplication needed**: v6/ prefix still on sectors, stocks, funds detail pages — needs migration to root

---

## Per-page detail

### Page 01 — Market Regime (Landing)
- **Mockup**: `01-market-regime.html`
- **Target route**: `frontend/src/app/page.tsx` (root)
- **Existing route status**: **PARTIAL** (route exists at `/`, renders core regime + scorecard, missing hero 12-week journey graph + conviction tabs)
- **Components rendered**: 
  - RegimeVerdict, SignalScorecard, TodayWorklist (NEW additions from spec)
  - RegimeHeadline, IntradayNiftyStrip, RegimeOverlayChart
  - TrendSection, BreadthSection, MomentumSection, ParticipationSection
- **Section matrix**:

| Mockup section | Status | Backing MV/table | Notes |
|---|---|---|---|
| Current regime verdict + deployment | DONE | `atlas_regime_state` + `mv_regime_context` | Renders from getCurrentRegime() + getRegimeScorecard() |
| Four signals favoured (cell cards) | STUB | `atlas_matrix_cells` | SignalScorecard shows summary, cell detail cards missing |
| Trailing 12 weeks · journey bar + metrics | **MISSING** | `atlas_regime_state` (daily history) | Mockup has 12-week regime bar + 4 metric rows. Page.tsx has no journey graph. |
| Today's conviction (3 tabs: stocks/funds/ETFs) | **MISSING** | `atlas_signal_calls` + conviction data | Mockup has conviction ledger. Page.tsx has none. Delegated to /v6/today. |
| Trend, Breadth, Momentum, Participation sections | DONE | `mv_nifty_metrics_daily` | Four sections render with historical charting. |

---

### Page 02 — India Pulse
- **Mockup**: `02-india-pulse.html`
- **Target route**: `frontend/src/app/india-pulse/page.tsx` (NOT YET ROUTED — spec says `/` or `/india-pulse`)
- **Existing route status**: **MISSING** (route does not exist; v6 version at `/v6/today` is different focus — regime snapshot, not pulse)
- **Components rendered**: None — no page at `/india-pulse` or `/` alternate yet
- **Section matrix**:

| Mockup section | Status | Backing MV/table | Notes |
|---|---|---|---|
| Headline indices (8 rich cards) | MISSING | `mv_index_state_daily` (Nifty 50/100/Mid/Small, Nifty 500, Bank, IT, Gold) | Mockup has RS vs Nifty 500, multi-window reads (1M/3M/6M), narrative. No page component. |
| Breadth (dense table, 8 rows) | MISSING | `mv_breadth_daily` + `mv_advance_decline` | %above DMA, 52W highs/lows, A/D ratio, McClellan, breadth thrust. No page. |
| Dispersion & concentration | MISSING | `mv_dispersion_daily` | Stacked bar showing concentration, skew narrative. No page. |
| Volatility (India VIX context) | MISSING | `atlas_vix_daily` | VIX tile + macro narrative. No page. |
| Tier leadership · mid/small vs large | MISSING | `mv_tier_leadership_daily` | Multi-line chart (1M/3M/6M/12M) showing small/mid vs large cap RS. No page. |
| Sectoral indices heatmap | MISSING | `mv_sector_indices_heatmap` | 11-sector grid with RS values + colors. No page. |
| Macro context (4-card grid + narrative) | MISSING | `atlas_macro_daily` | INR, G-Sec, UST, Credit spreads. No page. |

**Action**: Create `/india-pulse/page.tsx` with full-stack implementation of all 7 sections.

---

### Page 03 — Markets RS (Relative Strength)
- **Mockup**: `03-markets-rs.html`
- **Target route**: `frontend/src/app/markets-rs/page.tsx` (root path, per spec D4)
- **Existing route status**: **DONE/ROUTED** (route exists, RSC shell at `/markets-rs` delegates to MarketsRsClient)
- **Components rendered**: 
  - MarketsRsClient (all logic inside)
- **Section matrix**:

| Mockup section | Status | Backing MV/table | Notes |
|---|---|---|---|
| Hero readout (4 cards: leadership, India ranking, within-India, RS grade) | **PARTIAL** | `mv_markets_rs_grid` | MarketsRsClient renders grid, hero summary likely partial/stub |
| RS grid (9 baselines × 5 windows) | **PARTIAL** | `mv_markets_rs_grid` | Mockup shows India + 8 foreign baselines (SP500, MSCI World, MSCI EM, Gold, etc). Rendered but unknown toggle completeness. |
| Detail charts (price, volume, RS side-by-side) | **STUB** | `mv_markets_rs_detail_charts` | Mockup shows 2×3 grid of multidim charts. Client likely renders placeholder or basic charts. |

**Note**: Route is correct (no /v6/ prefix), component exists, but completeness of detail charts + narrative unknown without reading MarketsRsClient.

---

### Page 04 — Sectors (List)
- **Mockup**: `04-sectors.html`
- **Target route**: `frontend/src/app/sectors/page.tsx` (root, per spec D3)
- **Current implementation**: `frontend/src/app/v6/sectors/page.tsx` (still under /v6/ prefix)
- **Existing route status**: **WRONG_LOCATION** (lives at `/v6/sectors`, needs migration to `/sectors`)
- **Components rendered**: 
  - SectorsListV6 (client component, all logic)
  - Suspense boundary with SectorsSkeleton
  - State summary pills (Overweight, Neutral, Underweight, Avoid)
- **Section matrix**:

| Mockup section | Status | Backing MV/table | Notes |
|---|---|---|---|
| Sector rotation graph (RRG) | DONE | `atlas_sector_rrg` + history | Mockup shows 2D RRG chart + legend. SectorsListV6 renders via getRRGHistory(84). |
| Sector table · everything in one view (heatmap) | DONE | `mv_sector_cards` | Multi-window heatmap (1M/3M/6M/12M) showing RS values. SectorsListV6 renders table with sparklines. |
| Sectors Atlas is over/underweighting (hero readout) | DONE | `atlas_sector_states_daily` | Hero cards show Overweight/Neutral/Underweight/Avoid counts via getSectorsForDate(). |

**Action**: Migrate `/v6/sectors` → `/sectors`, keep `/v6/sectors/[name]` → `/sectors/[name]` (detail stays under /sectors too).

---

### Page 04a — Sector Detail (Energy)
- **Mockup**: `04a-sector-energy.html`
- **Target route**: `frontend/src/app/sectors/[name]/page.tsx` (detail param)
- **Current implementation**: `frontend/src/app/v6/sectors/[name]/page.tsx`
- **Existing route status**: **WRONG_LOCATION** (at `/v6/sectors/[name]`, needs move to `/sectors/[name]`)
- **Components rendered**: 
  - SectorDetailClient (all logic)
  - DataSourceBanner, breadcrumb
- **Section matrix**:

| Mockup section | Status | Backing MV/table | Notes |
|---|---|---|---|
| Nifty [Sector] · multidim view (price chart with RS baseline) | DONE | `mv_sector_deepdive` | SectorDetailClient fetches sector data + stocks, renders chart. |
| RS vs 5 baselines · 5 windows | **PARTIAL** | `mv_sector_rrg` + `mv_sector_deepdive` | SectorDetailClient has access to RRG history, but detail rendering unknown. |
| Sub-industry decomposition (stacked bar) | **PARTIAL** | `mv_sector_deepdive` | Likely rendered, but depth unknown. |
| Constituent stocks · 62 names (ladder) | DONE | `mv_stock_landscape` filtered by sector | getStocksForDate(snapshotDate, {sector: decoded}) fetches all stocks in sector. SectorDetailClient renders list. |
| Atlas methodology · why this verdict | STUB | `atlas_methodology_doc` (static) | Mockup has narrative card. SectorDetailClient likely has placeholder or doc link. |
| Macro overlays · forces around Energy | **MISSING** | `atlas_macro_overlay_sector` | Mockup has 4-card grid (Oil, UST curve, INR, supply). No page component reads this. |
| Cross-market · how India Energy stacks up globally | **MISSING** | `mv_sector_rs_global` | Mockup compares India Energy to MSCI World Energy, GICS subindustry peers. Not implemented. |

**Action**: Migrate to `/sectors/[name]`, implement macro overlay cards + cross-market comparison charts.

---

### Page 05 — Stocks (List)
- **Mockup**: `05-stocks.html`
- **Target route**: `frontend/src/app/stocks/page.tsx` (root, per spec D5)
- **Existing route status**: **DONE/ROUTED** (route exists at `/stocks`, matches mockup location)
- **Components rendered**: 
  - StocksClientShell (all logic)
  - State summary pills (Investable count, Leaders, Accelerating)
- **Section matrix**:

| Mockup section | Status | Backing MV/table | Notes |
|---|---|---|---|
| Today's story (headline + hero tiles) | **STUB** | `atlas_regime_state` + `atlas_stock_conviction_daily` | Page header shows counts (investable, leaders, accelerating). Story narrative missing. |
| Conviction landscape (scatter plot) | **MISSING** | `mv_stock_landscape` | Mockup shows 2D plot: y=convenience tier, x=momentum state. Not in StocksClientShell UI. |
| Composite trajectories · 30 days (line chart grid) | **MISSING** | `mv_stock_trajectory_30d` | Mockup shows 9 sparkline rows (one per cell type × tier combination). Not implemented. |
| Six picks worth a click (6 cards) | **MISSING** | `atlas_top_convictions_daily` | Mockup shows top conviction stocks. StocksClientShell likely shows screener, not hand-curated top 6. |
| All instruments · 750-name table (screener) | DONE | `atlas_stock_universe` | StocksClientShell renders screener table with filtering. getAllStocks() fetches all investable stocks. |
| Methodology · the cells doing the work (cell grid) | **STUB** | `atlas_matrix_cells` + `atlas_cell_methodology_doc` | Mockup shows 6 cell cards explaining fire patterns. Page has no dedicated methodology grid. |

**Action**: Add "Today's story" narrative + constellation view, "Six picks" carousel, populate methodology section with live cell cards.

---

### Page 05a — Stock Detail
- **Mockup**: `05a-stock-reliance.html`
- **Target route**: `frontend/src/app/stocks/[symbol]/page.tsx` (detail param)
- **Existing route status**: **DONE/ROUTED** (at `/stocks/[symbol]`)
- **Components rendered**: 
  - StockDeepDiveHeader, StockDeepDiveBody
  - MasterStateCard, ComponentScorecard, OBVContinuousChart, ATRContractionGauge
  - WithinStatePeers, DwellTimeline, HitRateRow, ActButton
- **Section matrix**:

| Mockup section | Status | Backing MV/table | Notes |
|---|---|---|---|
| Price · multidim view (OHLC + RS + volume) | DONE | `mv_stock_deepdive` | StockDeepDiveBody renders chart via getStockMetricHistory(). Multidim layout (price/RS/volume lanes). |
| Cell-fire timeline · 365 days | **PARTIAL** | `atlas_cell_fire_events` + `atlas_state_history` | DwellTimeline renders state dwell bars. Cell-fire overlay unknown. |
| Why these cells fire · methodology detail | DONE | `atlas_matrix_cells` + `atlas_cell_rules_doc` | ComponentScorecard shows validation detail for each component. |
| Relative strength · cross-baseline + peer set | DONE | `mv_stock_deepdive` + `atlas_baseline_cohort` | Multidim chart includes RS lanes. WithinStatePeers shows cohort peers (top 30 by rank). |
| Fundamentals snapshot | **PARTIAL** | `de_stock_fundamentals` (PE, DY, growth, debt) | Page has getStockFooterMetrics() call. Detail cards unknown. |
| Open Atlas positions + realised history | **STUB** | `atlas_portfolio_positions` + `atlas_trade_history` | Mockup shows current position size + realized P&L. ActButton exists (position entry), history unknown. |
| Stock-specific macro overlays | **MISSING** | `atlas_macro_overlay_stock` | Mockup shows 4-card grid (sector trends, earnings cycle, FX sensitivity, supply). Not implemented. |
| Recent events (news/catalyst timeline) | **MISSING** | `atlas_news_feed_stock` or external source | Mockup shows 6-item event log. No page component reads this. |

---

### Page 06 — Funds (List)
- **Mockup**: `06-funds.html`
- **Target route**: `frontend/src/app/funds/page.tsx` (root, per spec)
- **Existing route status**: **DONE/ROUTED** (at `/funds`, matches location)
- **Components rendered**: 
  - FundPageClient (all logic)
  - TileCount aggregation (server-side): n_recommended, n_leader_nav, n_aligned, n_strong_hold, n_suspended
- **Section matrix**:

| Mockup section | Status | Backing MV/table | Notes |
|---|---|---|---|
| Today's story (hero tiles + commentary) | DONE | `atlas_fund_decision_daily` + tile counts | Page builds FundCommentaryContext, passes to FundPageClient. Narrative renderinglikely present. |
| AMC leaderboard + category quartile heatmap | **PARTIAL** | `mv_fund_list_v6` (groupby category, AMC) | FundPageClient likely shows heatmap, but top category summary unknown depth. |
| Quartile trajectory · 24 months | **PARTIAL** | `mv_fund_deepdive` (quartile history) | Page computes medianRsPctile from rs_pctile_3m. Trajectory chart likely in FundPageClient. |
| Six funds worth a click (6 cards) | **PARTIAL** | `atlas_fund_recommendations_daily` | Page shows topCategory (best mean RS pctile). Hand-curated "six worth a click" unknown. |
| All funds · 587-scheme table (screener) | DONE | `mv_fund_list_v6` | FundPageClient renders screener, getAllFunds() fetches all funds. |
| SWITCH methodology · how the rule fires | **STUB** | `atlas_fund_switch_rules_doc` + `atlas_fund_decision_logic` | Mockup shows 6-card grid explaining rule. Page has no dedicated methodology grid. |

---

### Page 06a — Fund Detail
- **Mockup**: `06a-fund-ppfas.html`
- **Target route**: `frontend/src/app/funds/[mstar_id]/page.tsx` (detail param)
- **Existing route status**: **DONE/ROUTED** (at `/funds/[mstar_id]`, matches route spec)
- **Components rendered**: 
  - FundDeepDiveHeader, CommentaryBlock
  - FundLens1 (RS pctile trend), FundLens2 (Composition), FundLens3 (Holdings gate)
  - FundNavChart, FundRiskPanel, FundDecisionHistory, FundHoldingsTab, FundLensHistory
  - LeaderHoldingsPanel
- **Section matrix**:

| Mockup section | Status | Backing MV/table | Notes |
|---|---|---|---|
| Rolling performance · 5 years | DONE | `mv_fund_deepdive` + `de_mf_nav_daily` (1825 days) | FundNavChart renders via getFundNavHistory(1825). |
| Drawdown · 5 years | **PARTIAL** | `mv_fund_deepdive` (volatility, max DD) | FundRiskPanel renders drawdown metrics. Detail chart unknown. |
| Portfolio · top 10 holdings, allocation, attribution | DONE | `de_mf_portfolio_daily` | FundHoldingsTab shows top 20 holdings. Attribution unknown. |
| Same-category peer set · Flexi-cap (50 funds) | DONE | `mv_fund_list_v6` (filtered by category_name) | getFundMaster() includes category_name. Peer table likely in FundLensHistory or separate component. |
| Quartile transition · 60 months | **PARTIAL** | `mv_fund_deepdive` (quartile history) | FundLensHistory renders trajectory. 60-month heatmap unknown detail. |
| SWITCH rule check · why this fund fires SWITCH IN | DONE | `atlas_fund_decision_daily` + `atlas_fund_decision_logic` | FundDecisionHistory shows decision log + rule state. Decision narrative in CommentaryBlock. |

---

### Page 07 — ETFs (List)
- **Mockup**: `07-etfs.html`
- **Target route**: `frontend/src/app/etfs/page.tsx` (root, per spec)
- **Existing route status**: **DONE/ROUTED** (at `/etfs`, matches location)
- **Components rendered**: 
  - ETFScreener, ETFMetricTiles, ETFBubbleChart, ETFIntelligencePanel
- **Section matrix**:

| Mockup section | Status | Backing MV/table | Notes |
|---|---|---|---|
| Today's story (hero tiles) | **PARTIAL** | `atlas_regime_state` + `atlas_etf_conviction_daily` | Page shows investableCount, leaderCount. Story narrative missing. |
| Category bands · 4 ways ETFs come (stacked bar legend) | **MISSING** | `mv_etf_category_bands` | Mockup shows 4-band breakdown (Large-cap, Mid-cap, Sector, Commodity). Not in ETFMetricTiles UI. |
| AMC tile row · 9 AMCs sized by AUM | **MISSING** | `mv_etf_list_v6` (groupby amc, sum aum) | Mockup shows bubble row of AMCs by size. ETFBubbleChart is trend strength vs rank, not AMC AUM. |
| NAV vs market price · premium/discount scatter | **MISSING** | `mv_etf_deepdive` (nav, market_price daily) | Mockup shows scatter: x=time, y=premium %. Not in page components. |
| Six ETFs worth a click (6 cards) | **MISSING** | `atlas_etf_recommendations_daily` | Hand-curated top ETFs. Page likely shows screener only. |
| All ETFs · 34-ETF table (screener) | DONE | `mv_etf_list_v6` | ETFScreener renders screener. getAllETFs() fetches all ETFs. |

---

### Page 07a — ETF Detail
- **Mockup**: `07a-etf-goldbees.html`
- **Target route**: `frontend/src/app/etfs/[ticker]/page.tsx` (detail param)
- **Existing route status**: **DONE/ROUTED** (at `/etfs/[ticker]`, matches route spec)
- **Components rendered**: 
  - ETFDeepDiveHeader, ETFSnapshotTiles, ETFDeepDiveTabs
  - LeaderHoldingsPanel
- **Section matrix**:

| Mockup section | Status | Backing MV/table | Notes |
|---|---|---|---|
| Price · multidim view (OHLC + NAV) | DONE | `mv_etf_deepdive` | ETFDeepDiveTabs renders "Overview" tab with price chart + NAV overlay. |
| NAV vs market price · AP arbitrage check (2-line chart) | **PARTIAL** | `mv_etf_deepdive` (nav, market_price daily) | Snapshot tiles show "NAV Premium %" (point-in-time). Chart unknown. |
| Tracking error · 12 months | **PARTIAL** | `mv_etf_deepdive` (TE daily) | Page calls getETFMetricHistory(decoded, days). TE rendering unknown. |
| Composition · what's actually inside (top 20 holdings grid) | DONE | `de_etf_portfolio_daily` | ETFDeepDiveTabs renders holdings in Holdings tab. |
| Same-category peer set · Commodity ETFs (6) | **PARTIAL** | `mv_etf_list_v6` (filter by category/asset_class) | Snapshot tiles show peer count. Detailed peer table unknown. |
| Macro overlays · what's moving Gold (4-card grid) | **MISSING** | `atlas_macro_overlay_etf` (USD, real rates, equities, geo risk) | Mockup shows macro drivers. Not in page components. |

---

### Page 08 — Calls / Performance Ledger
- **Mockup**: `08-calls-performance.html`
- **Target route**: `frontend/src/app/calls/page.tsx` (or `/signals`, per spec D8)
- **Current implementation**: `frontend/src/app/signals/page.tsx` (different focus — TradingView pine script triggers, not Atlas calls ledger)
- **Existing route status**: **WRONG_CONTENT** (route `/signals` exists but renders TV alert feed, not v6 calls ledger)
- **Components rendered**: 
  - SignalCard (TV feed only, not Atlas calls)
- **Section matrix**:

| Mockup section | Status | Backing MV/table | Notes |
|---|---|---|---|
| Today's story (hero tiles + narrative) | **MISSING** | `atlas_call_performance_daily` | Mockup shows YTD excess, Sharpe, win rate %. SignalCard renders TV alerts. |
| Realized excess landscape (scatter: entry → exit) | **MISSING** | `mv_calls_performance` (full ledger) | Mockup shows realized P&L scatter. Not in SignalCard feed. |
| Cell realized-IC trajectories · 30-day rolling (line charts) | **MISSING** | `mv_calls_performance` (by cell, rolling IC) | Mockup shows 6 or more sparkline panels. Not implemented. |
| Six cells worth a click (6 cards: top realizers) | **MISSING** | `atlas_top_call_cells_daily` | Mockup shows top 6 cells by realized IC. Not in SignalCard. |
| All calls · 1,847-row ledger (complete trade log) | **MISSING** | `mv_calls_performance` (full 1000+ row table with sorting/filter) | Mockup shows complete ledger: entry date, symbol, cell, entry/exit price, return, days held, etc. SignalCard shows tiny subset (TV only). |
| Methodology · what the ledger is telling us | **MISSING** | `atlas_calls_methodology_doc` | Mockup has narrative card explaining ledger columns + IC interpretation. Not in page. |

**Action**: Create dedicated `/calls` page (or rename `/signals` focus to `/calls`). Implement full ledger + realized IC tracking. This is a **priority** gap — mockup shows 1,847 rows of call history (high detail), current `/signals` only shows live TV alerts.

---

## Critical gaps by mockup section type

### Missing entirely (no page component):
1. **India Pulse** (Page 02) — 7 sections all missing
2. **Calls/Performance** (Page 08) — 6 sections all missing
3. Stock detail: Macro overlays, Recent events
4. Sector detail: Macro overlays, Cross-market comparison
5. ETF detail: Macro overlays, NAV premium chart detail
6. Funds detail: Attribution

### Stubbed (route exists, section placeholder):
1. Page 01 Regime: 12-week journey graph, Conviction tabs
2. Page 03 Markets RS: Hero readout depth, Detail charts narrative
3. Page 04 Sectors: None (complete)
4. Page 05 Stocks: Today's story, Conviction landscape, Trajectory grid, Six picks, Methodology grid
5. Page 06 Funds: Methodology grid, Six picks hand-curation
6. Page 07 ETFs: Today's story, Category bands, AMC bubbles, Premium/discount scatter, Six picks

### Location wrong:
- `/v6/sectors` → needs `/sectors`
- `/v6/sectors/[name]` → needs `/sectors/[name]`

---

## Action list (sorted by chunk priority)

### **F.1 chunks** (Landing, India Pulse, Calls foundation)

1. **Create `/india-pulse/page.tsx`** (Page 02 full stack)
   - Fetches 7 datasources: headline indices, breadth, dispersion, volatility, tier RS, sectoral heatmap, macro
   - RSC shell + client component for interactivity
   - Priority: **HIGH** — completely missing, high-section-count mockup

2. **Expand `/calls` or rename `/signals` to calls ledger** (Page 08 full stack)
   - Replace TV alert focus with Atlas calls performance ledger (mv_calls_performance)
   - Today's story hero tiles, realized excess scatter, rolling IC trajectories, top 6 cells, 1800+ row table, methodology
   - Priority: **HIGH** — mockup shows extensive use case (1,847 rows), currently stubbed as TV feed

3. **Add 12-week journey graph to `/page.tsx`** (Page 01 enhancement)
   - Regime bar + 4 metric rows (Small-cap RS, Breadth %, VIX, Dispersion) spanning 12 weeks
   - Priority: **MEDIUM** — enhances existing route, foundational to regime narrative

4. **Add today's conviction tabs to `/page.tsx`** (Page 01 enhancement)
   - 3 tabs (Stocks, Funds, ETFs) showing top conviction ledger with signal + bar + verdict
   - Fetches from conviction_tape + signal_calls
   - Priority: **MEDIUM** — required mockup section

### **F.2 chunks** (Sector & Stock list enhancements)

5. **Add six sector cards section to `/sectors`** (Page 04 enhancement)
   - Hero readout: Overweight/Neutral/Underweight counts (already in page), plus 3 narrative blocks (one per category)
   - SectorsListV6 client already fetches needed data
   - Priority: **MEDIUM** — mockup shows hero enrichment, page skeleton exists

6. **Add conviction landscape + trajectory grid to `/stocks`** (Page 05 enhancements)
   - Conviction scatter (tier × momentum), 9-sparkline trajectory grid (6m perspective)
   - Six picks carousel or sticky band showing top convictions
   - Priority: **MEDIUM** — visual gaps in Page 05, data available

7. **Create cells methodology grid for `/stocks`** (Page 05 enhancement)
   - 6-card grid explaining cell fire patterns (currently in hero narrative on `/`)
   - Move or duplicate from homepage context
   - Priority: **LOW** — supporting detail, not critical to flow

### **F.3 chunks** (Detail pages: depth + macro)

8. **Migrate `/v6/sectors` → `/sectors` (and detail)** (Pages 04/04a rerouting)
   - Alias /v6/sectors* to /sectors* or move completely
   - No code change, just routing
   - Priority: **HIGH** — spec alignment, reduces confusion

9. **Add macro overlay cards to sector detail** (`/sectors/[name]`)
   - 4-card grid: Oil price, UST curve, INR, supply. Static or from atlas_macro_overlay_sector
   - Priority: **MEDIUM** — mockup shows narrative depth

10. **Add cross-market comparison to sector detail** (`/sectors/[name]`)
    - How India [Sector] stacks vs MSCI World + GICS peers. Chart + narrative.
    - Requires mv_sector_rs_global query
    - Priority: **LOW** — aspirational, nice-to-have

11. **Add macro overlays to stock detail** (`/stocks/[symbol]`)
    - 4-card grid: Sector trends, Earnings cycle, FX sensitivity, Supply
    - Static narratives or from atlas_macro_overlay_stock
    - Priority: **LOW** — enhances context, non-critical

12. **Add macro overlays to ETF detail** (`/etfs/[ticker]`)
    - 4-card grid: USD, Real rates, Equity flows, Geo risk
    - Priority: **LOW** — aspirational

### **F.4 chunks** (ETF & Fund detail polish)

13. **Add NAV premium/discount chart to `/etfs/[ticker]`** (Page 07a enhancement)
    - Scatter or line: NAV vs market price, highlight arbitrage zones
    - Data in mv_etf_deepdive, rendering likely in ETFDeepDiveTabs
    - Priority: **MEDIUM** — important for nav/creation unit decisions

14. **Add AMC leaderboard to `/etfs`** (Page 07 enhancement)
    - 9-tile bubble grid sized by AUM, colored by leading index
    - Requires aggregation of mv_etf_list_v6 by amc
    - Priority: **MEDIUM** — visual gap on list page

15. **Populate `/funds` six-picks carousel** (Page 06 enhancement)
    - Hand-curated or algorithm-driven (top by RS pctile, performance gate pass, etc.)
    - Priority: **LOW** — nice-to-have, screener exists

---

## Route deduplication summary

| Current path | Mockup target | Status | Action |
|---|---|---|---|
| `/` | Page 01 (Market Regime) | **CORRECT** | Enhance with 12-week graph + conviction tabs |
| `/india-pulse` | Page 02 | **MISSING** | Create new route + full stack |
| `/markets-rs` | Page 03 | **CORRECT** | Already done, verify detail chart completeness |
| `/v6/sectors` | Page 04 | **WRONG_LOCATION** | Migrate to `/sectors` |
| `/v6/sectors/[name]` | Page 04a | **WRONG_LOCATION** | Migrate to `/sectors/[name]` |
| `/stocks` | Page 05 | **CORRECT** | Enhance with conviction landscape + trajectory grid |
| `/stocks/[symbol]` | Page 05a | **CORRECT** | Mostly complete, add macro overlays |
| `/funds` | Page 06 | **CORRECT** | Mostly complete, six-picks carousel optional |
| `/funds/[mstar_id]` | Page 06a | **CORRECT** | Mostly complete, add attribution detail |
| `/etfs` | Page 07 | **CORRECT** | Add AMC leaderboard, NAV premium legend |
| `/etfs/[ticker]` | Page 07a | **CORRECT** | Add NAV premium chart, macro overlays optional |
| `/signals` | Page 08 | **WRONG_CONTENT** | Rename to `/calls`, rewrite for ledger focus |

---

## Data source alignment

**Queries confirmed in page.tsx files:**
- `mv_india_pulse_*`: Headlines, breadth, dispersion (status: partial — page doesn't exist)
- `mv_sector_*`: Sectors RRG, cards, breadth (status: DONE — SectorsListV6 fetches)
- `mv_stock_landscape`: Stock list + conviction (status: DONE — getAllStocks + StocksClientShell)
- `mv_stock_deepdive`: Stock detail charts (status: DONE — getStockMetricHistory)
- `mv_fund_list_v6`: Fund screener (status: DONE — getAllFunds + FundPageClient)
- `mv_fund_deepdive`: Fund performance, nav (status: DONE — getFundMaster + FundLens*)
- `mv_etf_*`: ETF list, detail (status: DONE — getAllETFs + ETFDeepDiveTabs)
- `mv_calls_performance`: Call ledger (status: MISSING — SignalCard queries TV only, not atlas)
- `mv_regime_*`: Regime + scorecard (status: DONE — getCurrentRegime + getRegimeScorecard)
- `mv_markets_rs_*`: Markets RS grid (status: DONE — getMarketsRsPage)

---

## Notes for frontend chunking

1. **India Pulse is a **new route**, not an enhancement** — requires new RSC shell + client component + 7 independent sections. Budget: high.
2. **Calls ledger is a **major rewrite** of `/signals`** — currently TV-centric, needs flip to Atlas decision ledger. Budget: high.
3. **Route migrations** (`/v6/` prefix removals) are **non-breaking if done with aliases** — old links still work, new spec links land immediately.
4. **Macro overlay cards** (on sector/stock/ETF detail) are **optional polish** — mockups show them, but can be deferred to F.5 without blocking F.1–F.4.
5. **12-week journey graph + conviction tabs** on `/page.tsx` are **blockers for F.1 landing** — fairly high-effort charts, but essential to regime page narrative.

---

## Conclusion

**12/8 pages mapped.** 
- **2 complete**, 3 routed with partial content, 3 completely missing, 2 at wrong locations
- **India Pulse + Calls ledger = biggest gaps**, each requiring full-stack build
- **Sector/stock/fund/ETF detail mostly done**, needs detail-section polish (macro overlays, cross-market, etc.)
- **Route alignment needed** for `/v6/*` → `/*` migrations before launch
- **All datasources mapped to backing MVs** — no unknown data dependencies

Recommend **F.1 priority: India Pulse + Calls + 12-week journey**, then **F.2: sector/stock enhancements**, then **F.3+: polish**.
