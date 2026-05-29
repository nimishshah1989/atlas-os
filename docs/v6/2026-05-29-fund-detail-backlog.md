# Fund Detail Page — Next-Sprint Plan

**Status:** Not started. Stock detail (`/stocks/[symbol]`) and ETF detail (`/etfs/[ticker]`) are both done as the v6 redesigned template. This document captures the Fund detail design before implementation begins.

## What's different from Stock and ETF pages

| Concern | Stock | ETF | Fund |
|---|---|---|---|
| **Chart source** | TradingView embed | TradingView embed | **Atlas-built Recharts** (TV does not cover Indian mutual funds) |
| **Fundamentals** | TV screener (PE, PS, PB, D/E, ROE) | TV screener (TER, AUM via deepdive) | **Morningstar API** (TER, AUM, alpha 1Y/3Y/5Y, Sharpe, sortino, max drawdown, capture ratios) |
| **News / Profile** | TV widgets work for NSE stocks | TV widgets work for NSE ETFs | TV does NOT have MF news — must source elsewhere (or omit) |
| **Holdings** | n/a | top_holdings JSONB | Morningstar holdings JSON (top 20 + sector composition + asset allocation) |
| **NAV chart** | n/a (price is price) | premium-to-NAV gauge | **Primary chart** — NAV time series + rolling 1Y/3Y CAGR overlay |
| **Verdict** | conviction_tape from atlas_stock_conviction_daily | composite_score from mv_etf_deepdive | **needs design** — likely category-relative score |

## Section template (mirrors Stock + ETF shape, 14 sections)

1. **Breadcrumb** — Atlas › Funds › {scheme_name}
2. **Verdict / Hero strip** — fund name, AMC, category, plan/option, AUM, TER, current NAV, since-launch return, rating chip
3. **Fund Gates Panel (6 gates)**
   - **Size**: AUM ≥ ₹500 cr (avoid micro-funds with capacity issues at the wrong end)
   - **Cost**: TER ≤ category median × 1.2 (avoid expensive funds)
   - **Track Record**: fund age ≥ 3 years (need a real history)
   - **Alpha**: rolling 3Y alpha vs benchmark > 0
   - **Category Strength**: category state from Atlas methodology
   - **Market**: regime gate (same as stock/ETF)
4. **Returns table** — 1M / 3M / 6M / 1Y / 3Y / 5Y absolute returns + benchmark + alpha + category rank
5. **Sector / Category context strip** — category state, breadth, category rank, fund rank in category
6. **NAV vs Category Average sparklines (2 mini Recharts)** — 12M comparison
7. **Atlas NAV chart** — Recharts area/line chart of NAV history from `de_mf_navs` with rolling drawdown shaded + benchmark overlay + key events marked
8. **Rolling performance windows** — 1Y rolling alpha + 3Y rolling Sharpe + 5Y rolling outperformance hit-rate (compact 3-panel layout)
9. **ETF Signal Trajectory Grid (12 fund metrics)**:
   - alpha_1y, alpha_3y, alpha_5y
   - sharpe_1y, sharpe_3y
   - sortino_3y
   - rolling outperformance hit-rate
   - max_drawdown_3y
   - tracking_error_3y
   - capture_ratio_up, capture_ratio_down
   - vol_3y
10. **Holdings panel** — top 20 with sector + market cap tier; allocation pie (large/mid/small)
11. **Sector composition vs benchmark** — bar comparison
12. **Peer matrix** — top 4 funds in same category by AUM/composite
13. **Supporting Detail drawers** — fund profile/AMC, manager history, dividend history, exit-load schedule
14. **Act** — invest button (SIP / lump sum)

## Backend pieces needed

### New queries (in `frontend/src/lib/queries/v6/fund-detail.ts`)

```typescript
getFundByMstarId(mstar_id: string): Promise<FundRow | null>
getFundNAVHistory(mstar_id: string, days: number): Promise<NavBar[]>
getFundRollingPerformance(mstar_id: string): Promise<{
  alpha_1y_series: TimeSeries[];
  alpha_3y_series: TimeSeries[];
  sharpe_3y_series: TimeSeries[];
  outperf_hit_rate: TimeSeries[];
}>
getFundHoldings(mstar_id: string, topN: number): Promise<Holding[]>
getFundCategoryContext(category: string, mstar_id: string): Promise<CategoryContext>
getFundPeers(category: string): Promise<PeerRow[]>
```

### New endpoints (or in-process server queries)

- `GET /v1/funds/{mstar_id}/rolling-performance` — computes 1Y/3Y/5Y rolling alpha/Sharpe/Sortino/hit-rate from NAV history (Python; ~50 LOC pandas)
- `GET /v1/funds/{mstar_id}/holdings-decomposition` — sector + asset allocation breakdown from Morningstar JSON

### Schema

Most of what's needed already exists:
- `atlas.atlas_universe_funds` — scheme master
- `atlas.atlas_fund_metrics_daily` — daily returns + rolling alpha/Sharpe (computed in `atlas.compute.funds`)
- `atlas.atlas_fund_states_daily` — fund state engine output
- `public.de_mf_navs` — NAV history from AMFI nightly pull
- `public.de_mf_holdings` — Morningstar holdings JSON (Atlas already pulls this)
- `atlas.atlas_fund_scorecard` — category-relative composite (if exists; check `atlas_fund_scorecard`)

**Likely missing:**
- A canonical `atlas_fund_category_states_daily` (mirrors `atlas_sector_states_daily` for sectors but for fund categories: Large Cap, Multi Cap, Mid Cap, etc.)
- Per-fund `contributing_signals` JSONB for conviction decomposition (mirrors stock pattern)

## New components (in `frontend/src/components/v6/fund-detail/`)

- `FundVerdictHeader.tsx` — server component (scheme name, AMC, category, AUM, TER, rating, NAV, since-launch return)
- `FundGatesPanel.tsx` — 6 fund-specific gates
- `FundReturnsTable.tsx` — 1M/3M/6M/1Y/3Y/5Y with benchmark + alpha + rank columns
- `FundNAVChart.tsx` — Recharts area chart of NAV with benchmark overlay + drawdown shading (client component)
- `FundRollingPerformancePanel.tsx` — 3-up Recharts mini chart (rolling alpha / Sharpe / hit-rate)
- `FundSparklineTrajectoryGrid.tsx` — 12-cell sparkline grid (mostly reuses sparkline cell component from stock detail)
- `FundHoldingsPanel.tsx` — top 20 holdings + cap tier breakdown
- `FundSectorCompositionChart.tsx` — bar comparison vs benchmark
- `FundPeerMatrix.tsx` — same-category peers
- `FundCategoryContextStrip.tsx` — category state + breadth + rank

## Reusable from stock/ETF pages

These plug in directly with no changes:
- `TVNews` widget can take the AMC's listed parent (e.g., `HDFCAMC`) for related news, OR omit news entirely
- The drawer pattern for legacy tabs
- The sparkline cell component (extract into a shared `Sparkline.tsx`)
- The gates panel skeleton — only the gate definitions change

## Implementation steps (sequential, ~8 hours total)

1. Read existing fund detail page state (`/funds/[mstar_id]/page.tsx`) — assess what's already there
2. Build `FundGatesPanel`, `FundReturnsTable`, `FundCategoryContextStrip` (~2 hours)
3. Build `FundNAVChart` + `FundRollingPerformancePanel` (~3 hours — the only chart work without TV)
4. Build `FundSparklineTrajectoryGrid` + `FundHoldingsPanel` + `FundSectorCompositionChart` (~1.5 hours)
5. Wire page assembly mirroring stock/ETF template (~1 hour)
6. Verify build + screenshot + commit (~30 min)

## Sector page (abridged version)

After Fund page ships, the **Sector page** (`/sectors/[sector]`) becomes:
- Same 14-section shape
- But density-reduced (no individual peer matrix at sector level; instead show "top 10 leading constituents")
- Macro context instead of category context
- Atlas-built sector RS chart (Recharts) since the underlying is an index
- TV embed for the sector ETF if one exists for that sector
- Sparkline grid of sector-level metrics: bottomup_rs_3m_nifty500, participation_rs_pct, sector_state transitions, breadth, advance/decline

Estimated: ~4 hours (less work because most components ported from stock/ETF).

## Open architectural questions (carry-over from stock page backlog)

1. **yFinance / Claude finance plugins integration** — same question as stock page. Recommendation in `2026-05-29-stock-detail-backlog.md` still stands: use Claude finance plugins as a Hermes research surface, keep TV/Morningstar/AMFI as data backbone.

2. **Fund conviction decomposition** — depends on whether `atlas_fund_scorecard` carries `contributing_signals` JSONB. If yes, port `ConvictionDecompositionPanel.tsx` directly. If no, skip the panel or design a category-relative score breakdown.

3. **News for funds** — TV does not aggregate news per mutual fund scheme. Options:
   - (a) Omit news from fund pages
   - (b) Use TVNews on the AMC listed entity (e.g., HDFC Mutual Fund → HDFCAMC stock)
   - (c) Build a tiny AMC-news mapping table + use a curated news source

My recommendation: **(b)** — minimal effort, decent signal, reuses existing component.
