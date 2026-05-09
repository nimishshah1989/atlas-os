# Atlas OS — Stocks Page Design Spec
_Design-reviewed 2026-05-09. All design decisions locked below._

---

## What's Already Built (Do Not Rebuild)
- `/` — Market Regime page
- `/sectors` — Sector listing (watchlist, bubble matrix, decision table, heatmap)
- `/sectors/[name]` — Sector deep-dive (Overview + Stocks tabs)

## Session Bootstrap: Read These Files First
1. [frontend/src/app/sectors/page.tsx](frontend/src/app/sectors/page.tsx) — page structure pattern
2. [frontend/src/lib/queries/sectors.ts](frontend/src/lib/queries/sectors.ts) — DB query patterns (postgres.js)
3. [frontend/src/components/sectors/StocksTable.tsx](frontend/src/components/sectors/StocksTable.tsx) — sortable table (helpers will be extracted to stock-formatters.ts)
4. [frontend/src/components/sectors/TopPicksCallout.tsx](frontend/src/components/sectors/TopPicksCallout.tsx) — top picks (extend cross-sector)
5. [frontend/src/components/sectors/SectorOverviewTab.tsx](frontend/src/components/sectors/SectorOverviewTab.tsx) — 2-col chart+commentary pattern; IndicatorChart at `@/components/regime/IndicatorChart`
6. [frontend/src/lib/queries/sector-deep-dive.ts](frontend/src/lib/queries/sector-deep-dive.ts) — StockRow type + getStocksInSector query
7. [frontend/src/app/sectors/[name]/not-found.tsx](frontend/src/app/sectors/%5Bname%5D/not-found.tsx) — not-found pattern to copy for stocks

---

## Critical Architectural Constraint
nginx on production routes `/api/*` to dead port 8010 → always 502.
ALL data fetching must be SSR (server components).
NEVER write client-side `fetch('/api/...')`.
Data flows: DB → server component → props → client component for interactivity only.

---

## Database Tables (postgres.js, schema = atlas)

```sql
atlas_universe_stocks:
  instrument_id (UUID), symbol, company_name, sector, tier (Tier1/Tier2/Tier3)
  in_nifty_50, in_nifty_100, in_nifty_500 (BOOLEAN)
  effective_to DATE (NULL = currently active)

atlas_stock_metrics_daily (one row per stock per trading day):
  instrument_id, date,
  ret_1m, ret_3m, ret_6m, ret_12m (NUMERIC — decimals: 0.10 = 10%)
  rs_3m_tier        ← stock RS vs Nifty 500 (ret_3m_stock - ret_3m_benchmark)
  rs_3m_tier_gold   ← same denominated in gold
  rs_pctile_3m      ← within-tier percentile 0.0–1.0 (primary ranking signal)
  ema_10_ratio, ema_20_ratio
  ema_10_at_20d_high BOOLEAN
  weinstein_gate_pass BOOLEAN
  above_30w_ma BOOLEAN       ← Weinstein 30-week MA (use for breadth, NOT "50-day EMA")

atlas_stock_states_daily:
  instrument_id, date,
  rs_state ('Overweight_RS' | 'Underweight_RS')
  momentum_state ('Improving' | 'Stable' | 'Deteriorating')
  risk_state, volume_state

atlas_stock_decisions_daily:
  instrument_id, date,
  is_investable BOOLEAN
  position_size_pct NUMERIC (0.0–1.0, e.g. 0.03 = 3%)
```

**Schema memory (do not repeat these mistakes):**
- `rs_3m_nifty500` is always NULL → use `rs_3m_tier` (it IS the RS vs Nifty 500, just named differently)
- `above_30w_ma` is the correct "trend filter" field — NOT a 50-day EMA participation metric (that doesn't exist at stock level)

---

## Design System (Locked — Follow Exactly)

```
font-sans      → UI labels, headings
font-mono      → all numbers (tabular-nums)
font-serif text-3xl → page/stock symbol headings

signal-pos     → positive returns, Overweight RS state
signal-neg     → negative returns, Underweight RS state
signal-warn    → amber / Neutral / Deteriorating
teal (#1D9E75) → accent, teal state, links
paper          → background
paper-rule     → borders, dividers
ink-primary / secondary / tertiary → text hierarchy
```

**RS Pctile bars**: green if >0.7, amber if >0.4, red below

**Sector badge colors** (fixed map — use consistently across all components):
```typescript
const SECTOR_COLORS: Record<string, { bg: string; text: string }> = {
  'Energy':        { bg: 'bg-teal/15',           text: 'text-teal' },
  'Financials':    { bg: 'bg-blue-500/15',        text: 'text-blue-600' },
  'IT':            { bg: 'bg-violet-500/15',       text: 'text-violet-600' },
  'Healthcare':    { bg: 'bg-emerald-500/15',      text: 'text-emerald-600' },
  'Consumer Disc': { bg: 'bg-orange-500/15',       text: 'text-orange-600' },
  'Consumer Staples': { bg: 'bg-yellow-500/15',   text: 'text-yellow-700' },
  'Industrials':   { bg: 'bg-slate-500/15',        text: 'text-slate-600' },
  'Materials':     { bg: 'bg-amber-500/15',        text: 'text-amber-700' },
  'Utilities':     { bg: 'bg-cyan-500/15',         text: 'text-cyan-700' },
  'Real Estate':   { bg: 'bg-rose-500/15',         text: 'text-rose-600' },
  'Telecom':       { bg: 'bg-purple-500/15',       text: 'text-purple-600' },
  'Auto':          { bg: 'bg-lime-500/15',          text: 'text-lime-700' },
}
// Fallback for unmapped sectors:
const DEFAULT_SECTOR_COLOR = { bg: 'bg-paper-rule/30', text: 'text-ink-secondary' }
```

**SectorBadge component** (create once, reuse everywhere):
```tsx
function SectorBadge({ sector }: { sector: string }) {
  const colors = SECTOR_COLORS[sector] ?? DEFAULT_SECTOR_COLOR
  return (
    <Link href={`/sectors/${encodeURIComponent(sector)}`}
      className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold ${colors.bg} ${colors.text} hover:opacity-80 transition-opacity`}>
      {sector}
    </Link>
  )
}
```

---

## Navigation Update
**Already done** — `frontend/src/components/nav/TopNav.tsx:9` has `{ href: '/stocks', label: 'Stocks' }` in NAV_LINKS. No action needed.

---

## Build Order

Components must exist before the pages that import them:

1. `frontend/src/lib/stock-formatters.ts` — shared formatting helpers (new)
2. `frontend/src/components/stocks/SectorBadge.tsx` — shared badge component (new)
3. `frontend/src/lib/queries/stocks.ts` — all stock queries (new)
4. `frontend/src/components/stocks/StockTopPicks.tsx` (new)
5. `frontend/src/components/stocks/StockBreadthPanel.tsx` (new)
6. `frontend/src/components/stocks/StockScreener.tsx` (new)
7. `frontend/src/app/stocks/page.tsx` — page shell, SSR (new)
8. `frontend/src/components/stocks/StockDeepDiveHeader.tsx` (new)
9. `frontend/src/components/stocks/StockSnapshotTiles.tsx` (new)
10. `frontend/src/components/stocks/StockOverviewTab.tsx` (new)
11. `frontend/src/components/stocks/StockHistoryTab.tsx` (new)
12. `frontend/src/app/stocks/[symbol]/page.tsx` (new)
13. `frontend/src/app/stocks/[symbol]/not-found.tsx` (new)

Deploy after each file compiles clean.

---

## File 0: `frontend/src/lib/stock-formatters.ts` (new, client-safe)

Shared formatting helpers and React components used by StocksTable, StockScreener, StockTopPicks, and StockOverviewTab. Extracted from StocksTable.tsx (those functions stay in StocksTable for now but will be re-imported from here going forward).

```typescript
import type { ReactNode } from 'react'

export function pct(v: string | null, digits = 1, signed = true): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  const sign = signed && n >= 0 ? '+' : ''
  return `${sign}${n.toFixed(digits)}%`
}

export function pctColor(v: string | null): string {
  if (v == null) return 'text-ink-tertiary'
  return parseFloat(v) >= 0 ? 'text-signal-pos' : 'text-signal-neg'
}

export function PosSizeBar({ value }: { value: string | null }): ReactNode {
  if (value == null) return <span className="font-mono text-xs text-ink-tertiary">—</span>
  const n = parseFloat(value)
  const display = `${(n * 100).toFixed(2)}%`
  const widthPct = Math.min(100, (n / 0.05) * 100)
  const color = n >= 0.03 ? '#2F6B43' : n >= 0.015 ? '#1D9E75' : '#94a3b8'
  return (
    <div className="flex items-center gap-2">
      <div className="w-12 h-1.5 bg-paper-rule rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${widthPct}%`, background: color }} />
      </div>
      <span className="font-mono text-xs tabular-nums" style={{ color }}>{display}</span>
    </div>
  )
}

export function RSPctileBar({ value }: { value: string | null }): ReactNode {
  if (value == null) return <span className="font-mono text-xs text-ink-tertiary">—</span>
  const n = parseFloat(value)  // 0.0–1.0
  const pct = Math.min(100, Math.max(0, n * 100))
  const color = n >= 0.7 ? '#2F6B43' : n >= 0.4 ? '#f59e0b' : '#ef4444'
  const label = `${pct.toFixed(0)}`
  return (
    <div className="flex items-center gap-2 justify-end">
      <div className="w-14 h-1.5 bg-paper-rule rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="font-mono text-xs tabular-nums w-6 text-right" style={{ color }}>{label}</span>
    </div>
  )
}

export function StateChip({ rs, mom }: { rs: string | null; mom: string | null }): ReactNode {
  if (!rs) return <span className="font-sans text-[10px] text-ink-tertiary">—</span>
  const isOver = rs === 'Overweight_RS'
  const tone = isOver
    ? mom === 'Improving' ? 'bg-signal-pos/15 text-signal-pos'
      : mom === 'Deteriorating' ? 'bg-signal-warn/15 text-signal-warn'
      : 'bg-teal/15 text-teal'
    : 'bg-signal-neg/15 text-signal-neg'
  const label = isOver
    ? mom === 'Improving' ? '↑ Strong'
      : mom === 'Deteriorating' ? '↓ Fading'
      : '→ Stable'
    : '↓ Weak'
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold ${tone}`}>
      {label}
    </span>
  )
}
```

Also move the commentary functions (`interpretRSPctile`, `interpretMomentumState`, `interpretWeinsteinGate`, `interpretEMARatio`) into this file so they can be imported by `StockOverviewTab` without duplicating logic.

---

## File 0b: `frontend/src/components/stocks/SectorBadge.tsx` (new, client-safe)

```tsx
'use client'
import Link from 'next/link'

const SECTOR_COLORS: Record<string, { bg: string; text: string }> = {
  'Energy':           { bg: 'bg-teal/15',           text: 'text-teal' },
  'Financials':       { bg: 'bg-blue-500/15',        text: 'text-blue-600' },
  'IT':               { bg: 'bg-violet-500/15',       text: 'text-violet-600' },
  'Healthcare':       { bg: 'bg-emerald-500/15',      text: 'text-emerald-600' },
  'Consumer Disc':    { bg: 'bg-orange-500/15',       text: 'text-orange-600' },
  'Consumer Staples': { bg: 'bg-yellow-500/15',       text: 'text-yellow-700' },
  'Industrials':      { bg: 'bg-slate-500/15',        text: 'text-slate-600' },
  'Materials':        { bg: 'bg-amber-500/15',        text: 'text-amber-700' },
  'Utilities':        { bg: 'bg-cyan-500/15',         text: 'text-cyan-700' },
  'Real Estate':      { bg: 'bg-rose-500/15',         text: 'text-rose-600' },
  'Telecom':          { bg: 'bg-purple-500/15',       text: 'text-purple-600' },
  'Auto':             { bg: 'bg-lime-500/15',          text: 'text-lime-700' },
}
const DEFAULT_SECTOR_COLOR = { bg: 'bg-paper-rule/30', text: 'text-ink-secondary' }

// IMPORTANT: verify these key strings against actual DB values before shipping:
// SELECT DISTINCT sector FROM atlas.atlas_universe_stocks WHERE effective_to IS NULL ORDER BY sector;
// Update SECTOR_COLORS keys if DB strings differ (e.g. "Consumer Discretionary" vs "Consumer Disc").

export function SectorBadge({ sector }: { sector: string }) {
  const colors = SECTOR_COLORS[sector] ?? DEFAULT_SECTOR_COLOR
  return (
    <Link
      href={`/sectors/${encodeURIComponent(sector)}`}
      className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold ${colors.bg} ${colors.text} hover:opacity-80 transition-opacity`}
    >
      {sector}
    </Link>
  )
}
```

---

## File 1: `frontend/src/lib/queries/stocks.ts` (new, server-only)

```typescript
import 'server-only'
import sql from '@/lib/db'
import type { StockRow } from './sector-deep-dive'

// above_30w_ma added here only — not needed in the per-sector StockRow
export type StockRowWithSector = StockRow & {
  sector: string
  above_30w_ma: boolean | null
}
```

**getAllStocks()** — same JOIN pattern as `getStocksInSector`, no sector WHERE clause, adds `u.sector` and `m.above_30w_ma` to SELECT.

```sql
-- Key additions vs getStocksInSector:
-- u.sector AS sector
-- m.above_30w_ma
-- No WHERE u.sector = $name filter
-- ORDER BY d.is_investable DESC NULLS LAST, m.rs_pctile_3m DESC NULLS LAST
```

**getTopPicksAcrossSectors()** — `d.is_investable = true` AND `s.rs_state = 'Overweight_RS'`, top 20 by `rs_pctile_3m DESC NULLS LAST`. Same SELECT as `getAllStocks()`. LIMIT 20.

**getStockBySymbol(symbol)** — returns `StockRowWithSector | null`. Same JOIN as `getAllStocks()` but `WHERE u.symbol = ${symbol} AND u.effective_to IS NULL`. Use `LIMIT 1`. Returns `rows[0] ?? null`.

**getStockMetricHistory(instrumentId: string, days = 180)**:
```typescript
// Validate days — same guard as getSectorMetricHistory
if (!Number.isInteger(days) || days < 1 || days > 3650) {
  throw new Error(`days must be an integer between 1 and 3650, got: ${days}`)
}
return sql<MetricHistoryRow[]>`
  SELECT
    date,
    rs_pctile_3m::text  AS rs_pctile_3m,
    rs_3m_tier::text    AS rs_3m_nifty500,
    ret_3m::text        AS ret_3m,
    ema_10_ratio::text  AS ema_10_ratio
  FROM atlas.atlas_stock_metrics_daily
  WHERE instrument_id = ${instrumentId}
    AND date >= CURRENT_DATE - (${days} || ' days')::interval
  ORDER BY date ASC
`
```

**getStockStateHistory(instrumentId: string, days = 180)**:
```typescript
// Same days validation guard
return sql<StateHistoryRow[]>`
  SELECT date, rs_state, momentum_state, risk_state, volume_state
  FROM atlas.atlas_stock_states_daily
  WHERE instrument_id = ${instrumentId}
    AND date >= CURRENT_DATE - (${days} || ' days')::interval
  ORDER BY date ASC
`
```

**Type definitions** (add to the file):
```typescript
export type MetricHistoryRow = {
  date: Date
  rs_pctile_3m: string | null
  rs_3m_nifty500: string | null
  ret_3m: string | null
  ema_10_ratio: string | null
}

export type StateHistoryRow = {
  date: Date
  rs_state: string | null
  momentum_state: string | null
  risk_state: string | null
  volume_state: string | null
}
```

---

## File 2: `frontend/src/app/stocks/page.tsx` (new server component)

```typescript
export const dynamic = 'force-dynamic'  // always fresh — nightly pipeline updates
```

Pattern identical to `/sectors/page.tsx`. Parallel fetch (breadth computed in-memory from stocks array — no separate query):
```typescript
const [stocks, topPicks] = await Promise.all([
  getAllStocks(),
  getTopPicksAcrossSectors(),
])

// Compute breadth from stocks — no extra DB round-trip
const above30wMaCount  = stocks.filter(s => s.above_30w_ma).length
const investableCount  = stocks.filter(s => s.is_investable).length
const overweightRsCount = stocks.filter(s => s.rs_state === 'Overweight_RS').length
const improvingCount   = stocks.filter(s => s.momentum_state === 'Improving').length
```

**Empty state** (stocks.length === 0):
```tsx
<div className="p-8">
  <p className="font-sans text-sm text-ink-secondary">
    No stock data available. Run the nightly pipeline first.
  </p>
</div>
```

**Page layout** (design decision D1 — Screener first):
```
HEADER BAND
STOCK SCREENER          ← primary surface, leads
STOCK BREADTH PANEL     ← secondary context
STOCK TOP PICKS         ← secondary context, bottom
```

**Header band** (matches /sectors pattern):
- Left: `font-sans text-sm font-semibold uppercase tracking-wide` "Stock Universe"
- Chips: `{investableCount} Investable` (teal dot), `{overweightRsCount} Overweight RS` (green dot), `{improvingCount} Improving` (green dot)
- Right: data date from `stocks[0]?.data_date` in `text-xs text-ink-tertiary`

Pass to `StockBreadthPanel`: `stocks`, `above30wMaCount`.

---

## File 3: `frontend/src/components/stocks/StockScreener.tsx` (new, 'use client')

Imports from `@/lib/stock-formatters` (pct, pctColor, PosSizeBar, StateChip, RSPctileBar) and `./SectorBadge`.

**New columns:**
- Sector column: `<SectorBadge sector={row.sector} />` — colored pill, links to `/sectors/[sector]`
- Symbols are clickable links (URL-encoded for symbols like M&M):
  ```tsx
  <Link href={`/stocks/${encodeURIComponent(row.symbol)}`}>{row.symbol}</Link>
  ```

**Search input** (left of filter chips):
```tsx
<input
  type="search"
  placeholder="Search symbol or company..."
  value={search}
  onChange={e => setSearch(e.target.value)}
  className="px-3 py-1.5 border border-paper-rule rounded-sm font-sans text-sm text-ink-primary bg-paper placeholder:text-ink-tertiary focus:outline-none focus:ring-1 focus:ring-teal/50 w-56"
/>
```
Live filter via `useMemo` on input — no debounce needed (client-side data).

**Filter chips** (`<button>` elements with `aria-pressed`):
```
All | Nifty 50 | Nifty 100 | Nifty 500 | Investable | Strong (Overweight RS + Improving)
```
Active chip: `bg-teal text-paper`. Inactive: `bg-paper-rule/20 text-ink-secondary hover:bg-paper-rule/40`.

**Stock count**: `font-sans text-xs text-ink-tertiary` "Showing {filtered.length} of {stocks.length} stocks" — right of filter chips.

**Sort keys extend to include 'sector'** (string sort via localeCompare).

**Empty state** (design decision D5 — inline table message):
When `filtered.length === 0`, render a single table row spanning all columns:
```tsx
<tr>
  <td colSpan={9} className="px-6 py-10 text-center">
    <p className="font-sans text-sm text-ink-secondary mb-2">
      No stocks match the current filter.
    </p>
    <button onClick={clearFilters} className="font-sans text-xs text-teal hover:underline">
      Clear filters
    </button>
  </td>
</tr>
```

---

## File 4: `frontend/src/components/stocks/StockBreadthPanel.tsx` (server component)

**Props**: `{ stocks: StockRowWithSector[]; above30wMaCount: number }`

**Big number** (design decision — correct schema):
"X of Y stocks above their 30W MA" (using `above_30w_ma` boolean, NOT "50-day EMA").

**Layout** — compact horizontal band:
```
[Left: Big number + progress bar]    [4 mini tiles: Nifty 50 | Nifty 100 | Nifty 500 | All]
```

Each mini tile — computed from the `stocks` prop:
```typescript
const n50 = stocks.filter(s => s.in_nifty_50)
const pctOwRs  = (arr: StockRowWithSector[]) =>
  arr.length === 0 ? null : arr.filter(s => s.rs_state === 'Overweight_RS').length / arr.length
const pctImpr  = (arr: StockRowWithSector[]) =>
  arr.length === 0 ? null : arr.filter(s => s.momentum_state === 'Improving').length / arr.length
```

Tile display:
```
Nifty 50
% OW RS:  72%   (colored: ≥60 = green, ≥40 = amber, <40 = red)
% Impr:   58%   (colored: ≥50 = green, ≥30 = amber, <30 = red)
```

---

## File 5: `frontend/src/components/stocks/StockTopPicks.tsx` (server component)

Imports from `@/lib/stock-formatters` (pct, pctColor, PosSizeBar, RSPctileBar) and `./SectorBadge`.

**Layout** (design decision D6 — horizontal ranked table, NOT 3-column card grid):

```tsx
<div className="px-4 py-3 border border-signal-pos/30 bg-signal-pos/5 rounded-sm">
  <div className="flex items-center gap-2 mb-3">
    <Sparkles className="w-3.5 h-3.5 text-signal-pos" />
    <span className="font-sans text-xs font-semibold text-signal-pos uppercase tracking-wider">
      Top Picks
    </span>
    <span className="font-sans text-[11px] text-ink-tertiary">
      investable · Overweight RS · ranked by 3M RS Pctile
    </span>
    <span className="ml-auto font-sans text-[11px] text-ink-tertiary">
      {picks.length} picks
    </span>
  </div>
  <table className="w-full border-collapse">
    <thead>
      <tr className="border-b border-paper-rule">
        <th className="py-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary w-8">#</th>
        <th className="py-1.5 text-left ..."">Symbol</th>
        <th className="py-1.5 text-left ...">Sector</th>
        <th className="py-1.5 text-right ...">RS Pctile</th>
        <th className="py-1.5 text-right ...">3M Ret</th>
        <th className="py-1.5 text-right ...">Pos Size</th>
      </tr>
    </thead>
    <tbody>
      {picks.map((p, i) => (
        <tr key={p.instrument_id} className="border-b border-paper-rule last:border-0 hover:bg-paper-rule/10">
          <td className="py-2 font-mono text-xs text-ink-tertiary">{i + 1}</td>
          <td className="py-2">
            <Link href={`/stocks/${encodeURIComponent(p.symbol)}`}>
              <div className="font-sans text-xs font-semibold text-ink-primary">{p.symbol}</div>
              <div className="font-sans text-[10px] text-ink-tertiary truncate max-w-[160px]">{p.company_name}</div>
            </Link>
          </td>
          <td className="py-2"><SectorBadge sector={p.sector} /></td>
          <td className="py-2 text-right">
            {/* RS Pctile bar: green >70, amber >40, red below */}
            <RSPctileBar value={p.rs_pctile_3m} />
          </td>
          <td className={`py-2 text-right font-mono text-xs ${pctColor(p.ret_3m)}`}>{pct(p.ret_3m)}</td>
          <td className="py-2 text-right"><PosSizeBar value={p.position_size_pct} /></td>
        </tr>
      ))}
    </tbody>
  </table>
</div>
```

**Empty state** (0 investable stocks):
```tsx
<div className="px-4 py-3 border border-paper-rule bg-paper-rule/10 rounded-sm">
  <div className="flex items-center gap-2 mb-1">
    <Sparkles className="w-3.5 h-3.5 text-ink-tertiary" />
    <span className="font-sans text-xs font-semibold text-ink-secondary uppercase tracking-wider">Top Picks</span>
  </div>
  <p className="font-sans text-xs text-ink-tertiary">
    No investable stocks with Overweight RS today. Market breadth is unfavorable — 
    reduce position sizing across the portfolio.
  </p>
</div>
```

---

## File 6: `frontend/src/app/stocks/[symbol]/page.tsx` (new server component)

```typescript
export const dynamic = 'force-dynamic'

export default async function StockPage({ params }: { params: Promise<{ symbol: string }> }) {
  // decode before lookup — handles M&M → M%26M → M&M round-trip
  const symbol = decodeURIComponent((await params).symbol).toUpperCase()
  const stock = await getStockBySymbol(symbol)
  if (!stock) notFound()  // → not-found.tsx (design decision D4)

  // Parallel fetch history
  const [metrics, states] = await Promise.all([
    getStockMetricHistory(stock.instrument_id, 180),  // 180 days default (decision D10)
    getStockStateHistory(stock.instrument_id, 180),
  ])
  ...
}
```

**Page layout**:
```
STICKY HEADER (top-14, z-30)   — StockDeepDiveHeader
SNAPSHOT TILES                  — StockSnapshotTiles
TABS: Overview | History        — tab state managed client-side
TAB CONTENT                     — StockOverviewTab | StockHistoryTab
```

**404**: `notFound()` → `frontend/src/app/stocks/[symbol]/not-found.tsx`.

---

## File 6b: `frontend/src/app/stocks/[symbol]/not-found.tsx` (new)

Pattern from `frontend/src/app/sectors/[name]/not-found.tsx`:

```tsx
import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="max-w-[800px] mx-auto p-12 text-center">
      <h1 className="font-serif text-2xl font-semibold text-ink-primary mb-2">
        Stock not found
      </h1>
      <p className="font-sans text-sm text-ink-secondary mb-6">
        That symbol isn&apos;t in the current universe. It may be delisted,
        misspelled, or not yet classified in Atlas.
      </p>
      <Link
        href="/stocks"
        className="inline-block px-4 py-2 border border-paper-rule rounded-sm font-sans text-sm text-ink-primary hover:bg-paper-rule/20"
      >
        ← Back to all stocks
      </Link>
    </div>
  )
}
```

---

## Stock Deep-Dive Header Component

Pattern from `SectorDeepDiveHeader.tsx`:

```tsx
<div className="sticky top-14 bg-paper border-b border-paper-rule z-30">
  <div className="px-6 py-4">
    {/* Row 1: Breadcrumb */}
    <nav className="flex items-center gap-1 font-sans text-xs text-ink-tertiary mb-3" aria-label="Breadcrumb">
      <Link href="/stocks" className="hover:text-ink-secondary transition-colors">Stocks</Link>
      <ChevronRight className="w-3 h-3" />
      <span className="text-ink-secondary">{stock.symbol}</span>
    </nav>
    
    {/* Row 2: Symbol + meta */}
    <div className="flex items-end justify-between flex-wrap gap-4">
      <div className="flex items-end gap-4">
        {/* Symbol: responsive font-size to handle long names like MAHINDRA&MAHINDRA */}
        <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary leading-none">
          {stock.symbol}
        </h1>
        <span className="font-sans text-sm text-ink-secondary">{stock.company_name}</span>
        <SectorBadge sector={stock.sector} />
        <StateChip rs={stock.rs_state} mom={stock.momentum_state} />
        {stock.in_nifty_50 && <span className="inline-flex ... text-[10px]">Nifty 50</span>}
        {!stock.in_nifty_50 && stock.in_nifty_100 && <span ...>Nifty 100</span>}
        {!stock.in_nifty_100 && stock.in_nifty_500 && <span ...>Nifty 500</span>}
      </div>
      <div className="flex items-center gap-4 text-xs text-ink-tertiary">
        {stock.position_size_pct && (
          <span>
            Pos Size: <span className="font-mono font-semibold text-ink-primary">
              {(parseFloat(stock.position_size_pct) * 100).toFixed(2)}%
            </span>
          </span>
        )}
        <span>Data as of {dataDate}</span>
      </div>
    </div>
  </div>
</div>
```

---

## Snapshot Tiles (design decision D2)

Between header and tabs — a compact tile row:

```tsx
<div className="px-6 py-3 border-b border-paper-rule grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
  <Tile label="RS Pctile" value={`${(parseFloat(stock.rs_pctile_3m ?? '0') * 100).toFixed(0)}`} />
  <Tile label="3M Return" value={pct(stock.ret_3m)} color={pctColor(stock.ret_3m)} />
  <Tile label="6M Return" value={pct(stock.ret_6m)} color={pctColor(stock.ret_6m)} />
  <Tile label="RS 3M" value={pct(stock.rs_3m_nifty500)} color={pctColor(stock.rs_3m_nifty500)} />
  <Tile label="Weinstein" value={stock.weinstein_gate_pass ? 'Pass ✓' : 'Fail ✗'} color={stock.weinstein_gate_pass ? 'text-signal-pos' : 'text-signal-neg'} />
  <Tile label="EMA 20D High" value={stock.ema_10_at_20d_high ? 'Yes' : 'No'} color={stock.ema_10_at_20d_high ? 'text-signal-pos' : 'text-ink-tertiary'} />
</div>
```

---

## Overview Tab

Same 2-column grid as SectorOverviewTab: `grid-cols-1 lg:grid-cols-[1fr_280px]`

**Chart 1**: RS Pctile trend (0–1 scale, refLine=0.5, refLabel="50%")
- Commentary: `interpretRSPctile(latest?.rs_pctile_3m)`

**Chart 2**: 3M Return trend (area chart, refLine=0)
- Commentary: interpret3MReturn (reuse from SectorOverviewTab)

**Chart 3**: EMA 10 Ratio trend (refLine=1.0, refLabel="1.0 = parity")
- Commentary: interpretEMARatio (new function, see below)

### Commentary Functions (all required — do not leave as placeholders)

```typescript
function interpretRSPctile(v: string | null): ReactNode {
  if (v == null) return <p>No RS percentile data available.</p>
  const n = parseFloat(v) * 100
  if (n >= 80) return (
    <>
      <p>RS percentile <span className="text-signal-pos font-semibold">{n.toFixed(0)}th</span> — top tier within sector group.</p>
      <p>Outperforming the vast majority of peers. Sustained above 80th pctile confirms a leadership position.</p>
    </>
  )
  if (n >= 60) return (
    <>
      <p>RS percentile <span className="text-signal-pos font-medium">{n.toFixed(0)}th</span> — above-average relative strength.</p>
      <p>Outperforming most peers. Not yet clear leadership — watch for a sustained break above 80th pctile.</p>
    </>
  )
  if (n >= 40) return (
    <>
      <p>RS percentile <span className="text-signal-warn font-medium">{n.toFixed(0)}th</span> — middle of the peer group.</p>
      <p>Performing in line with sector peers. Watch for a break above 60th pctile to confirm improving momentum.</p>
    </>
  )
  return (
    <>
      <p>RS percentile <span className="text-signal-neg font-semibold">{n.toFixed(0)}th</span> — underperforming sector peers.</p>
      <p>Capital rotating away from this stock. Below 40th pctile is an avoid zone for new entries.</p>
    </>
  )
}

function interpretMomentumState(state: string | null): ReactNode {
  if (!state) return <p>No momentum data available.</p>
  if (state === 'Improving') return (
    <>
      <p><span className="text-signal-pos font-semibold">Improving momentum</span> — RS trend is accelerating upward.</p>
      <p>Strongest entry signal. Improving RS + high pctile = high-conviction setup.</p>
    </>
  )
  if (state === 'Deteriorating') return (
    <>
      <p><span className="text-signal-neg font-semibold">Deteriorating momentum</span> — RS trend is weakening.</p>
      <p>Fading strength. Existing positions: watch closely. New positions: wait for stabilization.</p>
    </>
  )
  return (
    <>
      <p><span className="text-ink-secondary font-medium">Stable momentum</span> — RS trend holding steady.</p>
      <p>No acceleration either way. Acceptable for existing positions; not a trigger for new entries on its own.</p>
    </>
  )
}

function interpretWeinsteinGate(pass: boolean | null, ema20dHigh: boolean | null): ReactNode {
  if (pass == null) return <p>Weinstein gate data unavailable.</p>
  if (pass) return (
    <>
      <p><span className="text-signal-pos font-semibold">Weinstein stage: PASS</span> — stock is in a confirmed Stage 2 uptrend.</p>
      <p>Above the 30-week MA, trend confirmed.{ema20dHigh ? ' EMA at 20-day high adds momentum confirmation.' : ' Monitor EMA for further confirmation.'}</p>
    </>
  )
  return (
    <>
      <p><span className="text-signal-neg font-semibold">Weinstein stage: FAIL</span> — not in a confirmed uptrend.</p>
      <p>Below the 30-week MA or in Stage 3/4 distribution. Avoid new positions regardless of RS. Wait for a stage transition.</p>
    </>
  )
}

function interpretEMARatio(v: string | null): ReactNode {
  if (v == null) return <p>No EMA ratio data available.</p>
  const n = parseFloat(v)
  if (n >= 1.05) return (
    <>
      <p>EMA ratio <span className="text-signal-pos font-semibold">{n.toFixed(3)}</span> — stock EMA is {((n - 1) * 100).toFixed(1)}% above the benchmark EMA.</p>
      <p>Strong trend alignment. The stock is leading the benchmark in momentum terms.</p>
    </>
  )
  if (n >= 0.98) return (
    <>
      <p>EMA ratio <span className="text-ink-secondary font-medium">{n.toFixed(3)}</span> — roughly at parity with the benchmark.</p>
      <p>Stock moving broadly with the benchmark. No strong momentum edge in either direction.</p>
    </>
  )
  return (
    <>
      <p>EMA ratio <span className="text-signal-neg font-semibold">{n.toFixed(3)}</span> — stock EMA is below the benchmark.</p>
      <p>Momentum lagging the index. Consistent with Underweight RS positioning — avoid accumulating.</p>
    </>
  )
}
```

---

## History Tab

**State heatmap** (design decision D8 — all 4 state rows):

Same cell-based approach as `SectorHeatmap.tsx` but 4 rows stacked:

```
Row 1: RS State       [Overweight_RS = green | Underweight_RS = red]
Row 2: Momentum       [Improving = green | Stable = amber | Deteriorating = red]
Row 3: Risk State     [Low = green | Medium = amber | High = red | (map as available)]
Row 4: Volume State   [High = teal | Normal = grey | Low = amber]
```

Row labels: 12ch fixed width (matches SectorHeatmap `sector` label width).
Cell height: 16px per row (slightly thinner than sector heatmap since 4 rows).

**Returns table** (below heatmap, border-top):
```
Period  | Return
--------|--------
1M      | +X.X%  (colored)
3M      | +X.X%  (colored)
6M      | +X.X%  (colored)
12M     | +X.X%  (colored)
```

**Empty state** (0 history rows):
```tsx
<p className="font-sans text-xs text-ink-tertiary py-4">
  No state history available for this range.
</p>
```

---

## Test Plan (Eng Review — Required)

**Test files to create:**

### `frontend/src/__tests__/stocks/stock-formatters.test.ts`
Vitest unit tests for all pure functions in `stock-formatters.ts`:
- `pct(null)` → `'—'`; `pct('0.10')` → `'+10.0%'`; `pct('-0.05')` → `'-5.0%'`
- `pctColor(null)` → `'text-ink-tertiary'`; positive → `'text-signal-pos'`; negative → `'text-signal-neg'`
- `interpretRSPctile(null)` → no-data text; 4 threshold branches (0.80, 0.60, 0.40, <0.40)
- `interpretMomentumState(null/Improving/Deteriorating/Stable)` → correct text for each
- `interpretWeinsteinGate(null/true+true/true+false/false)` → correct text for each
- `interpretEMARatio(null/≥1.05/≥0.98/<0.98)` → correct text for each

### `frontend/src/__tests__/stocks/screener-filter.test.ts`
Vitest unit tests for StockScreener filter + search logic (test as pure JS, mock the stocks array):
- `filter=All` → all stocks shown
- `filter=Nifty50` → only `in_nifty_50 === true`
- `filter=Investable` → only `is_investable === true`
- `filter=Strong` → only `rs_state === 'Overweight_RS' && momentum_state === 'Improving'`
- `search='RELI'` → matches RELIANCE by symbol (case-insensitive)
- `search='mahindra'` → matches by company_name
- combined filter + search
- no-match → `filtered.length === 0`

### Update `frontend/playwright/smoke.spec.ts`
Add E2E smoke tests:
- `/stocks` page loads, breadth panel visible, at least one stock row in table
- Filter chip click (Investable) updates row count
- Symbol link click navigates to `/stocks/[symbol]`
- Breadcrumb on deep-dive page returns to `/stocks`
- `/stocks/DOESNOTEXIST_FAKESYMBOL` → renders not-found content

---

## Interaction State Coverage

| Component | Loading | Empty | Error |
|---|---|---|---|
| StockScreener | Next.js Suspense skeleton | Inline "No stocks match" + "Clear filters" button | — |
| StockTopPicks | Server render — no loading | "No investable stocks with Overweight RS today. Market breadth is unfavorable — reduce position sizing." | — |
| StockBreadthPanel | Server render | Show zeros ("0 of 0 stocks above 30W MA") | — |
| Stock deep-dive header | Server render | N/A (notFound() before render) | — |
| Stock overview charts | IndicatorChart handles null data | "No metric history available for this range." | — |
| Stock history heatmap | Server render | "No state history available for this range." | — |
| `/stocks/[FAKESYMBOL]` | — | notFound() → existing error.tsx (decision D4) | — |

---

## User Journey (confirmed)

1. User lands on `/stocks` → Screener is primary surface (decision D1)
2. Scans breadth panel for market context
3. Applies "Investable" or "Strong" filter
4. Searches for a specific name via search input
5. Clicks symbol → `/stocks/[symbol]` (symbols are `<Link>` elements)
6. Reads snapshot tiles → tabs into Overview
7. Reviews RS pctile trend + commentary → builds conviction
8. Tabs to History → checks state transitions over 6M
9. Clicks "Stocks" breadcrumb → returns to screener

---

## Accessibility Requirements

- Filter chips: `<button>` elements with `aria-pressed={isActive}` attribute
- Search input: `<label>` or `aria-label="Search stocks"` 
- Sortable table headers: `aria-sort` attribute ("ascending"/"descending"/"none")
- Sticky header: `role="banner"` or keep as-is (standard header)
- Symbol font-size: `text-2xl lg:text-3xl` — responsive to handle long NSE symbols

---

## Deployment

```bash
Host: ubuntu@13.202.162.196 (NOT 13.206.34.214)
SSH key: ~/.ssh/jsl-wealth-key.pem
App root: /home/ubuntu/atlas-frontend/

COPYFILE_DISABLE=1 tar -C frontend --exclude='._*' -czf /tmp/p.tar.gz src/...
scp -i ~/.ssh/jsl-wealth-key.pem /tmp/p.tar.gz ubuntu@13.202.162.196:/tmp/
ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.202.162.196 \
  'cd /home/ubuntu/atlas-frontend && tar -xzf /tmp/p.tar.gz && npm run build \
   && pm2 restart atlas-frontend'
```

**Note**: After deleting routes/pages, run `rm -rf .next` on EC2 before npm run build.

---

## NOT In Scope (Deferred)

- D3 bubble chart for stocks (analogous to SectorBubbleChart) — can be added to /stocks later as a scatter plot view
- CSV export for StockScreener — useful, but not in MVP
- Time range toggle on /stocks page — screener always shows latest snapshot, no time dimension needed
- Watchlist for individual stocks — sector-level watchlist exists, stock-level deferred
- DESIGN.md for the project — should be created in a separate session via /design-consultation

---

## What Already Exists (Reuse, Don't Rebuild)

| Pattern | Source | Use In |
|---|---|---|
| Sticky header + breadcrumb | SectorDeepDiveHeader.tsx | StockDeepDiveHeader |
| StateChip (↑Strong/→Stable/↓Weak) | StocksTable.tsx | StockScreener |
| PosSizeBar | StocksTable.tsx | StockScreener, StockTopPicks |
| pct() + pctColor() | StocksTable.tsx | All components |
| IndicatorChart | SectorOverviewTab.tsx | Stock overview charts |
| Cell-based heatmap | SectorHeatmap.tsx | Stock history heatmap (4 rows) |
| TopPicksCallout empty state | TopPicksCallout.tsx | StockTopPicks empty state |
| Commentary pattern | SectorOverviewTab.tsx | Stock overview commentary |
| TimeRangeToggle | /sectors/page.tsx | Stock deep-dive history range |

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | ISSUES_RESOLVED | 11 findings, all resolved |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 7 issues fixed, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | ISSUES_RESOLVED | score: 4/10 → 8/10, 10 decisions |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**ENG REVIEW FIXES (2026-05-09):**
- D1: Dropped `getMarketBreadthSnapshot()` — breadth computed in-memory from `getAllStocks()` result
- D2: Shared formatters extracted to `frontend/src/lib/stock-formatters.ts` (includes `RSPctileBar`, commentary functions)
- `SectorBadge` component extracted to `frontend/src/components/stocks/SectorBadge.tsx`
- `getStockBySymbol` return type corrected to `StockRowWithSector | null`
- `above_30w_ma` added to `StockRowWithSector` (not in base `StockRow`)
- `MetricHistoryRow` / `StateHistoryRow` types defined
- Days validation guard added to `getStockMetricHistory` / `getStockStateHistory`
- SQL history pseudocode corrected to postgres.js safe pattern: `CURRENT_DATE - (${days} || ' days')::interval`
- URL encoding: all `/stocks/${symbol}` links use `encodeURIComponent()`; `[symbol]/page.tsx` decodes with `decodeURIComponent()`
- `export const dynamic = 'force-dynamic'` added to both page files
- `not-found.tsx` specified for `/stocks/[symbol]/`
- Build order corrected: components before page shell
- Nav step removed (already done in TopNav.tsx:9)
- Sector color verification note added to `SectorBadge.tsx`
- Test plan added (Vitest unit + Playwright E2E)

**DESIGN:** 10 design decisions made. AI slop pattern (3-col card grid) replaced with ranked table. Schema error (50-day EMA → 30W MA) fixed. Sector badge color map specified. Commentary functions written out. History tab state rows resolved.

**CODEX OUTSIDE VOICE (2026-05-09):** 11 findings — 3 already resolved by eng review, 8 new catches (URL encoding, caching, build order, not-found.tsx, sector string verification, "Strong" vs TopPicks semantics note). All resolved.

**UNRESOLVED:** 0

**VERDICT:** ENG REVIEW CLEAR + DESIGN REVIEW CLEAR. Ready to implement.
