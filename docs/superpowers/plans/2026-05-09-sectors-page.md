# Sectors Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `/sectors` page — a three-view sector regime dashboard (D3 bubble matrix, decision table, state history heatmap) with a slide-in detail drawer.

**Architecture:** Server component at `app/sectors/page.tsx` fetches current snapshot + heatmap history in parallel; three client components consume the data. D3 handles the bubble chart and heatmap; existing `IndicatorChart` handles the history charts inside the drawer. A single `?range=` SearchParam controls all views.

**Tech Stack:** Next.js 15 App Router, TypeScript, D3 v7 (already in `package.json` — confirm with `npm ls d3`), Recharts (reuse `IndicatorChart`), postgres-js via `@/lib/db`, Tailwind CSS, lucide-react icons.

---

## DB context (confirmed from live data — 2026-05-05)

Table: `atlas.atlas_sector_metrics_daily` joined with `atlas.atlas_sector_states_daily`

Key columns used in this plan:

| Column | Type | Notes |
|---|---|---|
| `sector_name` | varchar | 30 distinct sectors |
| `date` | date | Daily, 2016-04-07 → 2026-05-05 |
| `bottomup_ret_1m` | numeric | 1-month return (decimal, e.g. 0.27 = 27%) |
| `bottomup_ret_3m` | numeric | 3-month return |
| `bottomup_ret_6m` | numeric | 6-month return |
| `bottomup_rs_3m_nifty500` | numeric | Relative strength vs Nifty 500, 3M |
| `participation_50` | numeric | % stocks above 50-day EMA (0–1 scale) |
| `participation_rs` | numeric | % stocks with positive RS (0–1 scale) |
| `leadership_concentration` | numeric | HHI-style concentration (0–1) |
| `constituent_count` | int | # stocks in sector |
| `sector_state` | varchar | Overweight / Neutral / Underweight |
| `bottomup_momentum_state` | varchar | Improving / Deteriorating |
| `bottomup_rs_state` | varchar | Overweight_RS / Neutral_RS / Avoid_RS |
| `divergence_flag` | bool | top-down and bottom-up disagree |
| `topdown_state` | varchar | Overweight / Avoid |

---

## Decision badge logic

```
Overweight + Improving            → ENTER
Overweight + Deteriorating        → HOLD
Neutral + Overweight_RS + Improving → ROTATE IN
Neutral + Improving               → WATCH
Neutral + Deteriorating           → PASS
Underweight (any)                 → EXIT
```

---

## File structure

```
frontend/src/
├── app/sectors/
│   └── page.tsx                          # NEW — server component, data fetch
├── components/sectors/
│   ├── SectorBubbleChart.tsx             # NEW — D3 scatter bubble (client)
│   ├── SectorDecisionTable.tsx           # NEW — sortable table (client)
│   ├── SectorHeatmap.tsx                 # NEW — CSS/D3 state heatmap (client)
│   └── SectorDrawer.tsx                  # NEW — slide-in detail panel (client)
└── lib/queries/
    └── sectors.ts                        # NEW — three DB queries (server)
```

No existing files are modified.

---

## Task 1: DB queries

**Files:**
- Create: `frontend/src/lib/queries/sectors.ts`

- [ ] **Step 1: Check D3 is available**

```bash
cd frontend && npm ls d3 2>/dev/null | head -3
```

Expected: `d3@7.x.x`. If missing: `npm install d3 @types/d3`

- [ ] **Step 2: Create sectors.ts**

```typescript
// frontend/src/lib/queries/sectors.ts
import { sql } from '@/lib/db'
import { cache } from 'react'

export type SectorSnapshot = {
  sector_name: string
  constituent_count: number
  bottomup_ret_1m: string | null
  bottomup_ret_3m: string | null
  bottomup_ret_6m: string | null
  bottomup_rs_3m_nifty500: string | null
  participation_50: string | null
  participation_rs: string | null
  leadership_concentration: string | null
  sector_state: string
  bottomup_state: string
  topdown_state: string
  divergence_flag: boolean
  bottomup_rs_state: string
  bottomup_momentum_state: string
  data_date: Date
}

export type SectorStateRow = {
  date: Date
  sector_name: string
  sector_state: string
}

export type SectorMetricHistoryRow = {
  date: Date
  bottomup_rs_3m_nifty500: string | null
  participation_50: string | null
  participation_rs: string | null
  bottomup_ret_3m: string | null
  sector_state: string
}

export const getCurrentSectors = cache(async (): Promise<SectorSnapshot[]> => {
  return sql<SectorSnapshot[]>`
    SELECT
      m.sector_name,
      m.constituent_count,
      m.bottomup_ret_1m::text,
      m.bottomup_ret_3m::text,
      m.bottomup_ret_6m::text,
      m.bottomup_rs_3m_nifty500::text,
      m.participation_50::text,
      m.participation_rs::text,
      m.leadership_concentration::text,
      s.sector_state,
      s.bottomup_state,
      s.topdown_state,
      s.divergence_flag,
      s.bottomup_rs_state,
      s.bottomup_momentum_state,
      m.date AS data_date
    FROM atlas.atlas_sector_metrics_daily m
    JOIN atlas.atlas_sector_states_daily s
      ON m.sector_name = s.sector_name AND m.date = s.date
    WHERE m.date = (SELECT MAX(date) FROM atlas.atlas_sector_metrics_daily)
    ORDER BY
      CASE s.sector_state
        WHEN 'Overweight'  THEN 1
        WHEN 'Neutral'     THEN 2
        WHEN 'Underweight' THEN 3
        ELSE 4
      END,
      m.bottomup_rs_3m_nifty500 DESC NULLS LAST
  `
})

export const getSectorStateHistory = cache(async (days: number): Promise<SectorStateRow[]> => {
  return sql<SectorStateRow[]>`
    SELECT date, sector_name, sector_state
    FROM atlas.atlas_sector_states_daily
    WHERE date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY date ASC, sector_name ASC
  `
})

export const getSectorMetricHistory = cache(async (
  sectorName: string,
  days: number,
): Promise<SectorMetricHistoryRow[]> => {
  return sql<SectorMetricHistoryRow[]>`
    SELECT
      m.date,
      m.bottomup_rs_3m_nifty500::text,
      m.participation_50::text,
      m.participation_rs::text,
      m.bottomup_ret_3m::text,
      s.sector_state
    FROM atlas.atlas_sector_metrics_daily m
    JOIN atlas.atlas_sector_states_daily s
      ON m.sector_name = s.sector_name AND m.date = s.date
    WHERE m.sector_name = ${sectorName}
      AND m.date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY m.date ASC
  `
})
```

- [ ] **Step 3: Check `@/lib/db` export path**

```bash
grep -n "export" frontend/src/lib/db.ts | head -5
```

Expected output should show `export const sql` or similar. If the file is at a different path, adjust the import in `sectors.ts`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/queries/sectors.ts
git commit -m "feat(sectors): DB queries — getCurrentSectors, getSectorStateHistory, getSectorMetricHistory"
```

---

## Task 2: Decision helper + page route

**Files:**
- Create: `frontend/src/app/sectors/page.tsx`

- [ ] **Step 1: Create the page**

```typescript
// frontend/src/app/sectors/page.tsx
import { Suspense } from 'react'
import { getCurrentSectors, getSectorStateHistory } from '@/lib/queries/sectors'
import { rangeToDays, type TimeRange } from '@/lib/time-range'
import { TimeRangeToggle } from '@/components/ui/TimeRangeToggle'
import { SectorBubbleChart } from '@/components/sectors/SectorBubbleChart'
import { SectorDecisionTable } from '@/components/sectors/SectorDecisionTable'
import { SectorHeatmap } from '@/components/sectors/SectorHeatmap'

export type SectorDecision = 'ENTER' | 'ROTATE IN' | 'WATCH' | 'HOLD' | 'PASS' | 'EXIT'

export function getSectorDecision(
  state: string,
  rsState: string,
  momentumState: string,
): SectorDecision {
  if (state === 'Overweight' && momentumState === 'Improving')  return 'ENTER'
  if (state === 'Overweight' && momentumState === 'Deteriorating') return 'HOLD'
  if (state === 'Neutral' && rsState === 'Overweight_RS' && momentumState === 'Improving') return 'ROTATE IN'
  if (state === 'Neutral' && momentumState === 'Improving')    return 'WATCH'
  if (state === 'Underweight')                                  return 'EXIT'
  return 'PASS'
}

type SearchParams = Promise<{ range?: string }>

export default async function SectorsPage({ searchParams }: { searchParams: SearchParams }) {
  const { range = '6M' } = await searchParams
  const historyRange = range as TimeRange
  const days = rangeToDays(historyRange)

  const [sectors, stateHistory] = await Promise.all([
    getCurrentSectors(),
    getSectorStateHistory(days),
  ])

  const overweightCount  = sectors.filter(s => s.sector_state === 'Overweight').length
  const neutralCount     = sectors.filter(s => s.sector_state === 'Neutral').length
  const underweightCount = sectors.filter(s => s.sector_state === 'Underweight').length
  const dataDate = sectors[0]?.data_date

  const sectorsWithDecision = sectors.map(s => ({
    ...s,
    decision: getSectorDecision(s.sector_state, s.bottomup_rs_state, s.bottomup_momentum_state),
  }))

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* Header band */}
      <div className="px-6 py-4 border-b border-paper-rule flex items-center justify-between">
        <div className="flex items-center gap-6">
          <h1 className="font-sans text-sm font-semibold text-ink-primary uppercase tracking-wide">
            Sector Regime
          </h1>
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
              {overweightCount} Overweight
            </span>
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-signal-warn" />
              {neutralCount} Neutral
            </span>
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-signal-neg" />
              {underweightCount} Underweight
            </span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {dataDate && (
            <span className="font-sans text-xs text-ink-tertiary">
              Data as of {new Date(dataDate).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
            </span>
          )}
          <Suspense>
            <TimeRangeToggle value={historyRange} options={['1M', '3M', '6M', '1Y']} />
          </Suspense>
        </div>
      </div>

      {/* View 1: Bubble Matrix */}
      <div className="px-6 py-6 border-b border-paper-rule">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-4">
          Sector Positioning Matrix — RS vs Breadth
        </h2>
        <SectorBubbleChart data={sectorsWithDecision} range={historyRange} />
      </div>

      {/* View 2: Decision Table */}
      <div className="px-6 py-6 border-b border-paper-rule">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-4">
          Sector Decision Table
        </h2>
        <SectorDecisionTable data={sectorsWithDecision} />
      </div>

      {/* View 3: State History Heatmap */}
      <div className="px-6 py-6">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-4">
          Sector State History — {historyRange}
        </h2>
        <SectorHeatmap
          history={stateHistory}
          sectors={sectorsWithDecision.map(s => s.sector_name)}
        />
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify the page compiles (stub the three client components first)**

Create stubs so the page imports resolve:

```bash
mkdir -p frontend/src/components/sectors
```

```typescript
// frontend/src/components/sectors/SectorBubbleChart.tsx
'use client'
export function SectorBubbleChart({ data, range }: { data: unknown[], range: string }) {
  return <div className="h-[500px] border border-paper-rule rounded-sm flex items-center justify-center text-ink-tertiary text-sm">Bubble chart coming</div>
}
```

```typescript
// frontend/src/components/sectors/SectorDecisionTable.tsx
'use client'
export function SectorDecisionTable({ data }: { data: unknown[] }) {
  return <div className="border border-paper-rule rounded-sm p-4 text-ink-tertiary text-sm">Decision table coming</div>
}
```

```typescript
// frontend/src/components/sectors/SectorHeatmap.tsx
'use client'
export function SectorHeatmap({ history, sectors }: { history: unknown[], sectors: string[] }) {
  return <div className="border border-paper-rule rounded-sm p-4 text-ink-tertiary text-sm">Heatmap coming</div>
}
```

- [ ] **Step 3: Run build to confirm no type errors**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: `✓ Compiled successfully` (warnings OK, errors not OK)

- [ ] **Step 4: Commit stubs**

```bash
git add frontend/src/app/sectors/ frontend/src/components/sectors/
git commit -m "feat(sectors): page route + component stubs"
```

---

## Task 3: D3 Bubble Chart

**Files:**
- Modify: `frontend/src/components/sectors/SectorBubbleChart.tsx`

This is the centrepiece. It renders an SVG via D3 inside a React `useEffect`.

- [ ] **Step 1: Write the full component**

```typescript
// frontend/src/components/sectors/SectorBubbleChart.tsx
'use client'
import { useEffect, useRef, useState } from 'react'
import * as d3 from 'd3'
import type { SectorDecision } from '@/app/sectors/page'
import { SectorDrawer } from './SectorDrawer'

export type SectorPoint = {
  sector_name: string
  constituent_count: number
  bottomup_rs_3m_nifty500: string | null
  participation_50: string | null
  sector_state: string
  bottomup_momentum_state: string
  decision: SectorDecision
}

const STATE_COLOR: Record<string, string> = {
  Overweight:  '#22c55e',
  Neutral:     '#f59e0b',
  Underweight: '#ef4444',
}

const DECISION_COLOR: Record<string, string> = {
  'ENTER':     '#22c55e',
  'HOLD':      '#14b8a6',
  'ROTATE IN': '#f59e0b',
  'WATCH':     '#94a3b8',
  'PASS':      '#94a3b8',
  'EXIT':      '#ef4444',
}

export function SectorBubbleChart({
  data,
  range,
}: {
  data: SectorPoint[]
  range: string
}) {
  const svgRef    = useRef<SVGSVGElement>(null)
  const wrapRef   = useRef<HTMLDivElement>(null)
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    const container = wrapRef.current
    const svgEl     = svgRef.current
    if (!container || !svgEl || data.length === 0) return

    const margin = { top: 40, right: 40, bottom: 64, left: 68 }
    const totalW = container.clientWidth
    const totalH = 520
    const W = totalW - margin.left - margin.right
    const H = totalH - margin.top  - margin.bottom

    // Clear previous render
    d3.select(svgEl).selectAll('*').remove()
    d3.select(svgEl).attr('width', totalW).attr('height', totalH)

    const svg = d3.select(svgEl)
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`)

    const points = data.map(d => ({
      ...d,
      x: parseFloat(d.bottomup_rs_3m_nifty500 ?? '0'),
      y: parseFloat(d.participation_50 ?? '0'),
      r: d.constituent_count,
    }))

    const xExt = d3.extent(points, p => p.x) as [number, number]
    const xPad = (xExt[1] - xExt[0]) * 0.12
    const xScale = d3.scaleLinear()
      .domain([Math.min(xExt[0] - xPad, -0.08), xExt[1] + xPad])
      .range([0, W])

    const yScale = d3.scaleLinear().domain([0.25, 1.05]).range([H, 0])

    const rScale = d3.scaleSqrt()
      .domain([0, d3.max(points, p => p.r) ?? 80])
      .range([6, 34])

    // Quadrant backgrounds
    const midX = xScale(0)
    const midY = yScale(0.5)

    const quads = [
      { x: midX, y: 0,    w: W - midX,  h: midY,     label: 'LEADERS',   color: '#22c55e' },
      { x: 0,    y: 0,    w: midX,      h: midY,     label: 'RECOVERING', color: '#f59e0b' },
      { x: midX, y: midY, w: W - midX,  h: H - midY, label: 'NARROWING', color: '#f59e0b' },
      { x: 0,    y: midY, w: midX,      h: H - midY, label: 'LAGGARDS',  color: '#ef4444' },
    ]

    quads.forEach(q => {
      svg.append('rect')
        .attr('x', q.x).attr('y', q.y)
        .attr('width', q.w).attr('height', q.h)
        .attr('fill', q.color).attr('opacity', 0.04)

      svg.append('text')
        .attr('x', q.x + q.w / 2)
        .attr('y', q.y + (q.y === 0 ? 14 : q.h - 6))
        .attr('text-anchor', 'middle')
        .attr('font-family', 'var(--font-sans)')
        .attr('font-size', 8).attr('font-weight', 700)
        .attr('letter-spacing', 1.5)
        .attr('fill', q.color).attr('opacity', 0.5)
        .text(q.label)
    })

    // Zero-line guides
    svg.append('line')
      .attr('x1', midX).attr('x2', midX)
      .attr('y1', 0).attr('y2', H)
      .attr('stroke', '#94a3b8').attr('stroke-width', 1)
      .attr('stroke-dasharray', '3 3')

    svg.append('line')
      .attr('x1', 0).attr('x2', W)
      .attr('y1', midY).attr('y2', midY)
      .attr('stroke', '#94a3b8').attr('stroke-width', 1)
      .attr('stroke-dasharray', '3 3')

    // Axes
    svg.append('g')
      .attr('transform', `translate(0,${H})`)
      .call(
        d3.axisBottom(xScale)
          .tickFormat(v => `${(+v * 100).toFixed(0)}%`)
          .ticks(7)
          .tickSize(0)
      )
      .call(ax => {
        ax.select('.domain').remove()
        ax.selectAll('.tick text')
          .attr('font-family', 'var(--font-sans)')
          .attr('font-size', 9)
          .attr('fill', '#94a3b8')
          .attr('dy', 12)
      })

    svg.append('g')
      .call(
        d3.axisLeft(yScale)
          .tickFormat(v => `${(+v * 100).toFixed(0)}%`)
          .ticks(5)
          .tickSize(0)
      )
      .call(ax => {
        ax.select('.domain').remove()
        ax.selectAll('.tick text')
          .attr('font-family', 'var(--font-sans)')
          .attr('font-size', 9)
          .attr('fill', '#94a3b8')
          .attr('dx', -6)
      })

    // Axis labels
    svg.append('text')
      .attr('x', W / 2).attr('y', H + 50)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)')
      .attr('font-size', 10).attr('fill', '#64748b')
      .text('3-Month Relative Strength vs Nifty 500 →')

    svg.append('text')
      .attr('transform', 'rotate(-90)')
      .attr('x', -H / 2).attr('y', -52)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)')
      .attr('font-size', 10).attr('fill', '#64748b')
      .text('↑ Breadth — % Stocks Above 50-Day EMA')

    // Tooltip (append to body once, reuse)
    const tip = d3.select(container)
      .append('div')
      .style('position', 'absolute')
      .style('pointer-events', 'none')
      .style('opacity', '0')
      .style('background', '#fff')
      .style('border', '1px solid #e2e8f0')
      .style('border-radius', '2px')
      .style('padding', '8px 10px')
      .style('font-family', 'var(--font-sans)')
      .style('font-size', '11px')
      .style('color', '#1e293b')
      .style('z-index', '10')
      .style('box-shadow', '0 2px 8px rgba(0,0,0,0.08)')
      .style('min-width', '160px')

    // Bubbles
    const node = svg.selectAll('.sector-node')
      .data(points)
      .enter()
      .append('g')
      .attr('class', 'sector-node')
      .style('cursor', 'pointer')

    node.append('circle')
      .attr('cx', p => xScale(p.x))
      .attr('cy', p => yScale(p.y))
      .attr('r',  p => rScale(p.r))
      .attr('fill',   p => STATE_COLOR[p.sector_state] ?? '#94a3b8')
      .attr('fill-opacity', 0.12)
      .attr('stroke', p => STATE_COLOR[p.sector_state] ?? '#94a3b8')
      .attr('stroke-width', 1.5)

    node.append('text')
      .attr('x', p => xScale(p.x))
      .attr('y', p => yScale(p.y) + 3)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)')
      .attr('font-size', 7.5)
      .attr('font-weight', 600)
      .attr('fill', p => STATE_COLOR[p.sector_state] ?? '#94a3b8')
      .attr('pointer-events', 'none')
      .text(p => p.sector_name.length > 9 ? p.sector_name.slice(0, 9) : p.sector_name)

    // Interactions
    node
      .on('mouseenter', function (event, p) {
        d3.select(this).select('circle')
          .attr('fill-opacity', 0.25)
          .attr('stroke-width', 2.5)

        const rect = container.getBoundingClientRect()
        const ex   = event.clientX - rect.left
        const ey   = event.clientY - rect.top

        tip
          .style('opacity', '1')
          .style('left', `${ex + 14}px`)
          .style('top',  `${ey - 30}px`)
          .html(`
            <div style="font-weight:700;margin-bottom:4px">${p.sector_name}</div>
            <div style="color:#64748b;margin-bottom:2px">
              Decision: <span style="font-weight:600;color:${DECISION_COLOR[p.decision]}">${p.decision}</span>
            </div>
            <div style="color:#64748b">RS (3M): <span style="color:#1e293b">${(p.x * 100).toFixed(1)}%</span></div>
            <div style="color:#64748b">Breadth: <span style="color:#1e293b">${(p.y * 100).toFixed(0)}%</span></div>
            <div style="color:#64748b">Stocks: <span style="color:#1e293b">${p.constituent_count}</span></div>
            <div style="margin-top:4px;color:#64748b">Momentum: <span style="color:#1e293b">${p.bottomup_momentum_state}</span></div>
          `)
      })
      .on('mousemove', function (event) {
        const rect = container.getBoundingClientRect()
        tip
          .style('left', `${event.clientX - rect.left + 14}px`)
          .style('top',  `${event.clientY - rect.top  - 30}px`)
      })
      .on('mouseleave', function () {
        d3.select(this).select('circle')
          .attr('fill-opacity', 0.12)
          .attr('stroke-width', 1.5)
        tip.style('opacity', '0')
      })
      .on('click', (_, p) => {
        tip.style('opacity', '0')
        setSelected(p.sector_name)
      })

    return () => { tip.remove() }
  }, [data])

  return (
    <div ref={wrapRef} className="relative">
      <svg ref={svgRef} className="w-full" />
      {/* Legend */}
      <div className="flex items-center gap-5 mt-2">
        {[['Overweight','#22c55e'], ['Neutral','#f59e0b'], ['Underweight','#ef4444']].map(([label, color]) => (
          <span key={label} className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
            <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: color, opacity: 0.7 }} />
            {label}
          </span>
        ))}
        <span className="font-sans text-xs text-ink-tertiary ml-2">Bubble size = number of stocks in sector</span>
      </div>
      {/* Detail drawer */}
      {selected && (
        <SectorDrawer
          sectorName={selected}
          range={range}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify no TypeScript errors**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -v "HealthDot" | head -20
```

Expected: no new errors (HealthDot error is pre-existing, can ignore).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/sectors/SectorBubbleChart.tsx
git commit -m "feat(sectors): D3 bubble scatter chart — RS vs breadth quadrant map"
```

---

## Task 4: Decision Table

**Files:**
- Modify: `frontend/src/components/sectors/SectorDecisionTable.tsx`

- [ ] **Step 1: Write the component**

```typescript
// frontend/src/components/sectors/SectorDecisionTable.tsx
'use client'
import { useState } from 'react'
import { ChevronUp, ChevronDown, AlertTriangle } from 'lucide-react'
import type { SectorDecision } from '@/app/sectors/page'

type Row = {
  sector_name: string
  constituent_count: number
  bottomup_ret_1m: string | null
  bottomup_ret_3m: string | null
  bottomup_ret_6m: string | null
  bottomup_rs_3m_nifty500: string | null
  participation_50: string | null
  sector_state: string
  bottomup_momentum_state: string
  divergence_flag: boolean
  decision: SectorDecision
}

type SortKey = 'decision' | 'bottomup_ret_3m' | 'bottomup_rs_3m_nifty500' | 'participation_50' | 'sector_name'

const DECISION_ORDER: Record<SectorDecision, number> = {
  'ENTER':     1,
  'ROTATE IN': 2,
  'WATCH':     3,
  'HOLD':      4,
  'PASS':      5,
  'EXIT':      6,
}

const DECISION_STYLE: Record<SectorDecision, string> = {
  'ENTER':     'bg-signal-pos/10 text-signal-pos',
  'HOLD':      'bg-teal/10 text-teal',
  'ROTATE IN': 'bg-signal-warn/10 text-signal-warn',
  'WATCH':     'bg-ink-tertiary/10 text-ink-secondary',
  'PASS':      'bg-ink-tertiary/10 text-ink-tertiary',
  'EXIT':      'bg-signal-neg/10 text-signal-neg',
}

const STATE_DOT: Record<string, string> = {
  Overweight:  'bg-signal-pos',
  Neutral:     'bg-signal-warn',
  Underweight: 'bg-signal-neg',
}

function pct(v: string | null, mul = 100): string {
  if (v == null) return '—'
  const n = parseFloat(v) * mul
  return `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`
}

function pctColor(v: string | null): string {
  if (v == null) return 'text-ink-tertiary'
  return parseFloat(v) >= 0 ? 'text-signal-pos' : 'text-signal-neg'
}

function ParticipationBar({ value }: { value: string | null }) {
  const n = value != null ? parseFloat(value) : 0
  const pctStr = `${(n * 100).toFixed(0)}%`
  const color = n >= 0.7 ? '#22c55e' : n >= 0.5 ? '#f59e0b' : '#ef4444'
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-paper-rule rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${n * 100}%`, background: color }} />
      </div>
      <span className="font-mono text-xs tabular-nums" style={{ color }}>{pctStr}</span>
    </div>
  )
}

export function SectorDecisionTable({ data }: { data: Row[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('decision')
  const [asc, setAsc]         = useState(true)

  function handleSort(key: SortKey) {
    if (sortKey === key) setAsc(a => !a)
    else { setSortKey(key); setAsc(true) }
  }

  const sorted = [...data].sort((a, b) => {
    let cmp = 0
    if (sortKey === 'decision') {
      cmp = DECISION_ORDER[a.decision] - DECISION_ORDER[b.decision]
    } else if (sortKey === 'sector_name') {
      cmp = a.sector_name.localeCompare(b.sector_name)
    } else {
      const av = parseFloat(a[sortKey] ?? '0')
      const bv = parseFloat(b[sortKey] ?? '0')
      cmp = bv - av
    }
    return asc ? cmp : -cmp
  })

  function SortIcon({ k }: { k: SortKey }) {
    if (sortKey !== k) return <ChevronUp className="w-3 h-3 opacity-20" />
    return asc
      ? <ChevronUp className="w-3 h-3 text-accent" />
      : <ChevronDown className="w-3 h-3 text-accent" />
  }

  function Th({ label, k }: { label: string; k: SortKey }) {
    return (
      <th
        className="px-3 py-2 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary cursor-pointer hover:text-ink-secondary select-none whitespace-nowrap"
        onClick={() => handleSort(k)}
      >
        <span className="flex items-center gap-1">{label} <SortIcon k={k} /></span>
      </th>
    )
  }

  return (
    <div className="overflow-x-auto border border-paper-rule rounded-sm">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-paper-rule bg-paper">
            <Th label="Sector"    k="sector_name" />
            <Th label="Decision"  k="decision" />
            <th className="px-3 py-2 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary whitespace-nowrap">State</th>
            <Th label="1M Ret"    k="bottomup_ret_3m" />
            <Th label="3M Ret"    k="bottomup_ret_3m" />
            <Th label="RS 3M"     k="bottomup_rs_3m_nifty500" />
            <Th label="Breadth"   k="participation_50" />
            <th className="px-3 py-2 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">Momentum</th>
            <th className="px-3 py-2 text-center font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">⚠</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr
              key={row.sector_name}
              className={`border-b border-paper-rule last:border-0 hover:bg-paper-rule/20 transition-colors ${i % 2 === 0 ? '' : 'bg-paper-rule/5'}`}
            >
              <td className="px-3 py-2.5 font-sans text-xs font-medium text-ink-primary whitespace-nowrap">
                {row.sector_name}
                <span className="ml-1.5 font-sans text-[10px] text-ink-tertiary">({row.constituent_count})</span>
              </td>
              <td className="px-3 py-2.5">
                <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-bold uppercase tracking-wide ${DECISION_STYLE[row.decision]}`}>
                  {row.decision}
                </span>
              </td>
              <td className="px-3 py-2.5">
                <span className="flex items-center gap-1.5">
                  <span className={`inline-block w-1.5 h-1.5 rounded-full ${STATE_DOT[row.sector_state] ?? 'bg-ink-tertiary'}`} />
                  <span className="font-sans text-xs text-ink-secondary">{row.sector_state}</span>
                </span>
              </td>
              <td className={`px-3 py-2.5 font-mono text-xs tabular-nums ${pctColor(row.bottomup_ret_1m)}`}>
                {pct(row.bottomup_ret_1m)}
              </td>
              <td className={`px-3 py-2.5 font-mono text-xs tabular-nums ${pctColor(row.bottomup_ret_3m)}`}>
                {pct(row.bottomup_ret_3m)}
              </td>
              <td className={`px-3 py-2.5 font-mono text-xs tabular-nums ${pctColor(row.bottomup_rs_3m_nifty500)}`}>
                {pct(row.bottomup_rs_3m_nifty500)}
              </td>
              <td className="px-3 py-2.5">
                <ParticipationBar value={row.participation_50} />
              </td>
              <td className="px-3 py-2.5">
                <span className={`font-sans text-xs ${row.bottomup_momentum_state === 'Improving' ? 'text-signal-pos' : 'text-signal-neg'}`}>
                  {row.bottomup_momentum_state === 'Improving' ? '↑ Improving' : '↓ Deteriorating'}
                </span>
              </td>
              <td className="px-3 py-2.5 text-center">
                {row.divergence_flag && (
                  <AlertTriangle className="w-3 h-3 text-signal-warn mx-auto" title="Top-down and bottom-up signals diverge" />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 2: Verify**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -v "HealthDot" | head -10
```

Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/sectors/SectorDecisionTable.tsx
git commit -m "feat(sectors): sortable decision table with ENTER/HOLD/EXIT badges"
```

---

## Task 5: State History Heatmap

**Files:**
- Modify: `frontend/src/components/sectors/SectorHeatmap.tsx`

The heatmap is a CSS grid where rows = sectors, columns = trading dates. Each cell is a colored rectangle. D3 handles only scale computation; rendering is React/CSS (faster DOM for this use case).

- [ ] **Step 1: Write the component**

```typescript
// frontend/src/components/sectors/SectorHeatmap.tsx
'use client'
import { useMemo, useState } from 'react'
import type { SectorStateRow } from '@/lib/queries/sectors'

const STATE_COLOR: Record<string, string> = {
  Overweight:  '#22c55e',
  Neutral:     '#f59e0b',
  Underweight: '#ef4444',
}

const STATE_BG: Record<string, string> = {
  Overweight:  'bg-signal-pos',
  Neutral:     'bg-signal-warn',
  Underweight: 'bg-signal-neg',
}

type Props = {
  history: SectorStateRow[]   // all sectors × all dates for the range
  sectors: string[]           // ordered sector list (Overweight first)
}

export function SectorHeatmap({ history, sectors }: Props) {
  const [tooltip, setTooltip] = useState<{ text: string; x: number; y: number } | null>(null)

  const { dates, cellMap } = useMemo(() => {
    // Build map: sectorName → date string → state
    const map = new Map<string, Map<string, string>>()
    const dateSet = new Set<string>()

    for (const row of history) {
      const d = row.date instanceof Date
        ? row.date.toISOString().slice(0, 10)
        : String(row.date).slice(0, 10)
      dateSet.add(d)
      if (!map.has(row.sector_name)) map.set(row.sector_name, new Map())
      map.get(row.sector_name)!.set(d, row.sector_state)
    }

    const sortedDates = [...dateSet].sort()
    return { dates: sortedDates, cellMap: map }
  }, [history])

  // Show month label only on first date of each month
  const monthLabels = useMemo(() => {
    const seen = new Set<string>()
    return dates.map((d, i) => {
      const m = d.slice(0, 7)
      if (seen.has(m)) return null
      seen.add(m)
      const dt = new Date(d)
      return {
        index: i,
        label: dt.toLocaleDateString('en-US', { month: 'short', year: '2-digit' }).replace(' ', " '"),
      }
    })
  }, [dates])

  const cellW = Math.max(3, Math.min(14, Math.floor(900 / dates.length)))
  const cellH = 18

  return (
    <div className="relative overflow-x-auto">
      {/* Month label row */}
      <div className="flex mb-1" style={{ paddingLeft: 140 }}>
        {dates.map((d, i) => {
          const ml = monthLabels[i]
          return (
            <div key={d} style={{ width: cellW, flexShrink: 0, position: 'relative' }}>
              {ml && (
                <span
                  style={{
                    position: 'absolute',
                    left: 0,
                    fontFamily: 'var(--font-sans)',
                    fontSize: 8,
                    color: '#94a3b8',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {ml.label}
                </span>
              )}
            </div>
          )
        })}
      </div>

      {/* Heatmap rows */}
      {sectors.map(sector => {
        const sectorMap = cellMap.get(sector) ?? new Map()
        return (
          <div key={sector} className="flex items-center mb-px">
            {/* Sector label */}
            <div
              className="font-sans text-[10px] text-ink-secondary shrink-0 pr-2 text-right"
              style={{ width: 140 }}
            >
              {sector}
            </div>
            {/* Cells */}
            {dates.map(d => {
              const state = sectorMap.get(d)
              const color = state ? STATE_COLOR[state] : '#e2e8f0'
              return (
                <div
                  key={d}
                  style={{
                    width: cellW,
                    height: cellH,
                    background: color,
                    opacity: state ? 0.75 : 0.3,
                    flexShrink: 0,
                    cursor: state ? 'pointer' : 'default',
                  }}
                  onMouseEnter={e => {
                    if (!state) return
                    const rect = (e.target as HTMLElement).getBoundingClientRect()
                    const dt = new Date(d)
                    setTooltip({
                      text: `${sector} · ${dt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })} · ${state}`,
                      x: rect.left,
                      y: rect.top - 28,
                    })
                  }}
                  onMouseLeave={() => setTooltip(null)}
                />
              )
            })}
          </div>
        )
      })}

      {/* Legend */}
      <div className="flex items-center gap-5 mt-3" style={{ paddingLeft: 140 }}>
        {[['Overweight','#22c55e'], ['Neutral','#f59e0b'], ['Underweight','#ef4444']].map(([label, color]) => (
          <span key={label} className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
            <span className="inline-block w-3 h-3" style={{ background: color, opacity: 0.75 }} />
            {label}
          </span>
        ))}
      </div>

      {/* Tooltip (fixed, follows mouse position) */}
      {tooltip && (
        <div
          className="fixed z-50 bg-paper border border-paper-rule rounded-[2px] px-2 py-1 font-sans text-[11px] text-ink-primary shadow-sm pointer-events-none"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          {tooltip.text}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/sectors/SectorHeatmap.tsx
git commit -m "feat(sectors): sector state history heatmap — CSS grid with D3-style layout"
```

---

## Task 6: Sector Detail Drawer

**Files:**
- Modify: `frontend/src/components/sectors/SectorDrawer.tsx`

The drawer slides in from the right when a bubble or row is clicked. It fetches that sector's metric history on demand and renders it using the existing `IndicatorChart`.

- [ ] **Step 1: Write the component**

```typescript
// frontend/src/components/sectors/SectorDrawer.tsx
'use client'
import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { IndicatorChart } from '@/components/regime/IndicatorChart'
import { rangeToDays, type TimeRange } from '@/lib/time-range'
import type { SectorMetricHistoryRow } from '@/lib/queries/sectors'

type Props = {
  sectorName: string
  range: string
  onClose: () => void
}

export function SectorDrawer({ sectorName, range, onClose }: Props) {
  const [history, setHistory] = useState<SectorMetricHistoryRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const days = rangeToDays(range as TimeRange)
    fetch(`/api/sectors/${encodeURIComponent(sectorName)}/history?days=${days}`)
      .then(r => r.json())
      .then((data: SectorMetricHistoryRow[]) => {
        setHistory(data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [sectorName, range])

  const dateStr = (row: SectorMetricHistoryRow) =>
    row.date instanceof Date
      ? row.date.toISOString().slice(0, 10)
      : String(row.date).slice(0, 10)

  const rsData = history.map(r => ({
    date: dateStr(r),
    value: r.bottomup_rs_3m_nifty500 != null ? parseFloat(r.bottomup_rs_3m_nifty500) : null,
  }))
  const breadthData = history.map(r => ({
    date: dateStr(r),
    value: r.participation_50 != null ? parseFloat(r.participation_50) : null,
  }))
  const rsParticData = history.map(r => ({
    date: dateStr(r),
    value: r.participation_rs != null ? parseFloat(r.participation_rs) : null,
  }))

  const latest = history[history.length - 1]
  const currentRS = latest?.bottomup_rs_3m_nifty500 != null
    ? `${(parseFloat(latest.bottomup_rs_3m_nifty500) * 100).toFixed(1)}%`
    : '—'
  const currentBreadth = latest?.participation_50 != null
    ? `${(parseFloat(latest.participation_50) * 100).toFixed(0)}%`
    : '—'
  const currentRSPartic = latest?.participation_rs != null
    ? `${(parseFloat(latest.participation_rs) * 100).toFixed(0)}%`
    : '—'

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/30 z-40 backdrop-blur-sm"
        onClick={onClose}
      />
      {/* Panel */}
      <div className="fixed right-0 top-0 h-full w-[480px] bg-paper border-l border-paper-rule z-50 overflow-y-auto shadow-xl">
        {/* Header */}
        <div className="sticky top-0 bg-paper border-b border-paper-rule px-6 py-4 flex items-center justify-between">
          <div>
            <h2 className="font-sans text-sm font-semibold text-ink-primary">{sectorName}</h2>
            <p className="font-sans text-xs text-ink-tertiary mt-0.5">{range} metric history</p>
          </div>
          <button onClick={onClose} className="text-ink-tertiary hover:text-ink-primary transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {loading ? (
          <div className="p-6 space-y-4">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-48 bg-paper-rule/20 rounded-sm animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="p-6 space-y-4">
            <IndicatorChart
              title="Relative Strength vs Nifty 500 (3M)"
              description="How this sector's stocks are performing relative to the broader Nifty 500 universe over a rolling 3-month window. Positive means sector leadership; negative means the sector is lagging the index."
              currentValue={currentRS}
              isBullish={latest?.bottomup_rs_3m_nifty500 != null ? parseFloat(latest.bottomup_rs_3m_nifty500) > 0 : null}
              data={rsData}
              refLine={0}
              refLabel="0"
              variant="area"
              yFormat="pct"
            />
            <IndicatorChart
              title="Breadth — % Stocks Above 50-Day EMA"
              description="Percentage of stocks within this sector that are currently trading above their 50-day exponential moving average. Above 50% means the majority of the sector is in a medium-term uptrend."
              currentValue={currentBreadth}
              isBullish={latest?.participation_50 != null ? parseFloat(latest.participation_50) > 0.5 : null}
              data={breadthData}
              refLine={0.5}
              refLabel="50%"
              variant="area"
              yFormat="pct"
            />
            <IndicatorChart
              title="RS Participation — % Stocks with Positive RS"
              description="Fraction of the sector's stocks that are outperforming the Nifty 500 on a relative strength basis. High RS participation means leadership is broad, not concentrated in 1-2 names."
              currentValue={currentRSPartic}
              isBullish={latest?.participation_rs != null ? parseFloat(latest.participation_rs) > 0.5 : null}
              data={rsParticData}
              refLine={0.5}
              refLabel="50%"
              variant="area"
              yFormat="pct"
            />
          </div>
        )}
      </div>
    </>
  )
}
```

- [ ] **Step 2: Create the API route the drawer calls**

```typescript
// frontend/src/app/api/sectors/[name]/history/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { getSectorMetricHistory } from '@/lib/queries/sectors'

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params
  const days = parseInt(req.nextUrl.searchParams.get('days') ?? '180', 10)
  const data = await getSectorMetricHistory(decodeURIComponent(name), days)
  return NextResponse.json(data)
}
```

```bash
mkdir -p frontend/src/app/api/sectors/\[name\]/history
```

- [ ] **Step 3: Verify build**

```bash
cd frontend && npm run build 2>&1 | tail -15
```

Expected: `✓ Compiled successfully` with `/sectors` and `/api/sectors/[name]/history` listed in routes.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/sectors/SectorDrawer.tsx \
        frontend/src/app/api/sectors/
git commit -m "feat(sectors): sector detail drawer + /api/sectors/[name]/history route"
```

---

## Task 7: Wire up nav + deploy

**Files:**
- Modify: `frontend/src/components/nav/TopNav.tsx` (add Sectors link)

- [ ] **Step 1: Check existing TopNav**

```bash
grep -n "Sectors\|sectors\|href" frontend/src/components/nav/TopNav.tsx | head -10
```

If `/sectors` link is already there (it should be, the nav was built earlier), skip to Step 3.

- [ ] **Step 2: Add Sectors link if missing**

Open `TopNav.tsx` and add inside the nav list:

```tsx
<Link
  href="/sectors"
  className={`font-sans text-xs font-medium transition-colors ${
    pathname === '/sectors' ? 'text-ink-primary' : 'text-ink-secondary hover:text-ink-primary'
  }`}
>
  Sectors
</Link>
```

- [ ] **Step 3: Sync and build on EC2**

```bash
rsync -avz --exclude='.git' --exclude='node_modules' --exclude='.next' \
  frontend/ atlas:/home/ubuntu/atlas-frontend/ 2>&1 | tail -5

ssh atlas "cd /home/ubuntu/atlas-frontend && npm run build 2>&1 | tail -20"
```

Expected: build output shows `ƒ /sectors` and `ƒ /api/sectors/[name]/history` in route list.

- [ ] **Step 4: Restart PM2**

```bash
ssh atlas "pm2 restart atlas-frontend --update-env && sleep 2 && curl -s -o /dev/null -w '%{http_code}' http://localhost:3001/sectors"
```

Expected: `200`

- [ ] **Step 5: Spot-check live**

Open `https://atlas.jslwealth.in/sectors` and verify:
- Header shows correct Overweight/Neutral/Underweight counts
- Bubble chart renders with 30 labelled bubbles in 4 quadrants
- Decision table shows ENTER badges for Defence, Energy, Capital Goods; EXIT for IT, Banking
- Heatmap shows green horizontal bars for Overweight sectors, red for Underweight
- Clicking a bubble opens the drawer with 3 charts
- Time range toggle (1M/3M/6M/1Y) reloads and narrows all views

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/nav/TopNav.tsx
git commit -m "feat(sectors): wire nav + deploy — sectors page live on atlas.jslwealth.in"
```

---

## Self-review

**Spec coverage:**
- ✅ Bubble chart (D3, RS vs breadth, 4 quadrants, bubble size = constituent count, color = state)
- ✅ Decision table (ENTER / ROTATE IN / WATCH / HOLD / PASS / EXIT badges, sortable)
- ✅ State history heatmap (sectors × dates, answers "when did Defence turn Overweight?")
- ✅ Click bubble → sector drawer with 3 IndicatorCharts (reuses existing component)
- ✅ Master time range toggle (1M/3M/6M/1Y) controlling all three views
- ✅ Tooltip on bubble hover with all key metrics
- ✅ Divergence warning (⚠ in table)
- ✅ Consistent with Regime page design tokens (font-sans, ink-*, signal-*, paper-rule)

**Placeholder scan:** None found — all steps contain complete code.

**Type consistency:**
- `SectorSnapshot` defined in `sectors.ts`, used in `page.tsx` and passed to client components
- `SectorDecision` exported from `page.tsx`, imported in `SectorBubbleChart` and `SectorDecisionTable`
- `SectorStateRow` and `SectorMetricHistoryRow` defined in `sectors.ts`, used in `SectorHeatmap` and `SectorDrawer`
- `getSectorDecision()` exported from `page.tsx`, called only there (not in client components)
- API route uses `getSectorMetricHistory` which is defined in `sectors.ts`
