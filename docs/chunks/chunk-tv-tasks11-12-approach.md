# Chunk: TV Tasks 11 & 12 — TVChartPanel + TVMetricsBadge + Portfolio Analytics

## Data scale
No DB queries — pure frontend components consuming API data already fetched by RSC pages.
No Python needed; this chunk is TypeScript/React only.

## Approach

### Task 11 — TVMetricsBadge + TVChartPanel (TV-05)

**TVMetricsBadge**
- New file: `frontend/src/components/v6/TVMetricsBadge.tsx`
- Renders a row of pills in StockHero below the metrics strip (Row 4 area)
- Guard: returns null if `tvRecommendLabel` is null
- Stale detection: compare `fetchedAt` ISO string to `Date.now() - 2*86400*1000`
- Skeleton: `isLoading` prop → 3 `animate-pulse` skeleton pills
- No new dependencies required

**TVChartPanel**
- New file: `frontend/src/components/v6/TVChartPanel.tsx`
- `flex flex-row` layout: left w-[36%] bg-paper-deep, right flex-1 bg `#161a25`
- TradingView iframe with `tvWidgetUrl` construction
- iframe `onError` → boolean state → error fallback panel
- Mobile: `md:flex-row flex-col` — stacks below 768px
- No recharts needed in this component (only iframe)

**StockDetailClient wiring**
- Add `tvMetrics` to `StockDetailClientProps` (optional)
- Add `'chart'` to Tab type union and TABS array (between technicals and audit)
- Render `<TVMetricsBadge>` inside `StockHero` via prop threading OR directly in StockDetailClient below StockHero — chosen: pass down via StockHero since it's in the hero area
- Actually: StockHero doesn't take tvMetrics. Cleaner to render TVMetricsBadge in StockDetailClient JSX AFTER the StockHero component with a wrapping div in the hero section.
  - But StockHero owns its own padding/border. So render TVMetricsBadge as a separate div between StockHero and TabNav — a "sub-hero" band.
  - Spec says "in StockHero right side, below price block" but StockHero doesn't have a price block currently (it's conviction + sizing). We'll render it in the hero area as an additional row by passing it as a prop to StockHero.
  - Decision: add `tvMetricsBadge?: React.ReactNode` slot to StockHero so it renders inside the hero div after Row 5 — cleaner than forking hero's own logic.
  - Alternative: render between StockHero and TabNav in StockDetailClient. Simpler, avoids touching StockHero's internal structure. We'll do this since "below price" translates to "below the hero block" in the v6 layout.

**stocks/[symbol]/page.tsx wiring**
- This is the OLD stock deep-dive page (not v6 StockDetailClient)
- StockDetailClient is used from `frontend/src/app/stocks/[symbol]/page.tsx` — CONFIRMED NOT: that page uses StockDeepDiveHeader etc.
- We need to find where StockDetailClient is actually rendered. Let's check.

**Wiki patterns checked**
- "Young-Instrument Partial Metrics" — TVMetrics may be null; null guard required
- Named imports only, no `import *`

### Task 12 — Portfolio Analytics Page (TV-06)

**Query file**
- New file: `frontend/src/lib/queries/v6/portfolio_analytics.ts`
- Simple fetch wrapper; no `server-only` since it might be called from RSC

**PortfolioAnalyticsClient**
- New file: `frontend/src/components/v6/PortfolioAnalyticsClient.tsx`
- Recharts `LineChart` with `ResponsiveContainer` — cumulative return computation done in component
- Cumulative return formula: reduce `daily_returns`, track running product
- 7-metric grid uses CSS `grid grid-cols-7` with `divide-x divide-paper-rule`
- CSV export: anchor href to `/v1/portfolios/{id}/tv-export.csv`

**Analytics page**
- New file: `frontend/src/app/portfolios/[id]/analytics/page.tsx`
- RSC pattern: async default export, fetch analytics server-side

**Portfolio page wiring**
- Add `<Link href={/portfolios/${id}/analytics}>` in the header section of `frontend/src/app/portfolios/[id]/page.tsx`

## Edge cases
- `tvMetrics` is null → TVChartPanel shows "—" for all values, iframe still loads
- `tvRecommendLabel` null → TVMetricsBadge returns null
- `analytics` null → PortfolioAnalyticsClient shows empty state message
- `daily_returns` empty array → cumulative chart renders empty (no crash)
- Beta null → tooltip "Requires 30+ trading days"
- Stale badge: compare date part only (UTC days diff)
- iframe cross-origin → `onError` may not fire for embed failures; add `onLoad` state too

## Existing code being reused
- `toNumber`, `formatPct` from `@/lib/v6/decimal`
- `GradeChip`, `ConvictionTape` patterns for pill styling
- Recharts `LineChart`, `ResponsiveContainer`, `CartesianGrid`, `Tooltip`, `Line`, `XAxis`, `YAxis` — confirmed in package.json
- `fmtDate` pattern from portfolio page (local copy in analytics client)
- `Link` from `next/link`

## Files to create/modify
**Create:**
1. `frontend/src/components/v6/TVMetricsBadge.tsx`
2. `frontend/src/components/v6/TVChartPanel.tsx`
3. `frontend/src/components/v6/PortfolioAnalyticsClient.tsx`
4. `frontend/src/lib/queries/v6/portfolio_analytics.ts`
5. `frontend/src/app/portfolios/[id]/analytics/page.tsx`

**Modify:**
6. `frontend/src/components/v6/StockDetailClient.tsx` — add Chart tab + TVMetricsBadge
7. `frontend/src/app/stocks/[symbol]/page.tsx` — add tvMetrics fetch (NOTE: this is the OLD page, not the v6 one; need to verify which page uses StockDetailClient)
8. `frontend/src/app/portfolios/[id]/page.tsx` — add View Analytics link

## Expected runtime
- All client components: renders in <100ms
- RSC analytics page fetch: ~300ms (API call + JSON parse)
- Build: ~60s on local Mac

## Decision: TVMetricsBadge placement
Rendered in StockDetailClient between StockHero and TabNav as a "hero extension band".
This avoids touching StockHero's internal layout while keeping the badge visually adjacent to hero content.
