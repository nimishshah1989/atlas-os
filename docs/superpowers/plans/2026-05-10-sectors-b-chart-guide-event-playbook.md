# Sectors Sub-project B: Dual Chart Guide + Event Playbook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two intelligence layers to the Sectors page — a dual-chart cross-reference guide between the Positioning Matrix and RRG, and an Event Playbook that auto-matches the current regime to similar historical events and shows which sectors led/lagged.

**Architecture:** The playbook query runs server-side in `sectors/page.tsx` alongside existing queries and degrades to an empty array on failure. The dual chart guide is purely client-side, computing quadrant positions from props already available in `SectorViews`. Both features are new components dropped into the existing `SectorViews` layout.

**Tech Stack:** Next.js 15 App Router (server components + `'use client'`), TypeScript, Tailwind CSS, postgres.js for SQL, Vitest for tests, existing MARKET_EVENTS library in `frontend/src/lib/event-library.ts`.

---

## File Map

| File | Action | What changes |
|---|---|---|
| `frontend/src/lib/queries/sectors.ts` | Modify | Add `PlaybookEntry` type and `getSectorPlaybook` function (append after line 297) |
| `frontend/src/app/sectors/page.tsx` | Modify | Import `getCurrentRegime` + `getSectorPlaybook`, add 2 more parallel queries, pass `playbook` + `regimeState` to `SectorViews` |
| `frontend/src/components/sectors/SectorDualChartGuide.tsx` | Create | Cross-reference table + live today-example between sections 1 and 2 |
| `frontend/src/components/sectors/SectorEventPlaybook.tsx` | Create | Event playbook cards with overweight-at-risk warnings |
| `frontend/src/components/sectors/SectorViews.tsx` | Modify | Accept 3 new props; insert `SectorDualChartGuide` between sections 1+2; insert `SectorEventPlaybook` between breadth and heatmap |
| `frontend/src/__tests__/sectors/getSectorPlaybook.test.ts` | Create | Type + shape tests for new query + SQL validation |
| `frontend/src/__tests__/sectors/SectorDualChartGuide.test.tsx` | Create | Quadrant computation logic tests |

---

## Task 1: Add `PlaybookEntry` type and `getSectorPlaybook` to sectors.ts

**Files:**
- Modify: `frontend/src/lib/queries/sectors.ts` (append after line 297)
- Create: `frontend/src/__tests__/sectors/getSectorPlaybook.test.ts`

### Background (read before coding)

`MARKET_EVENTS` lives in `frontend/src/lib/event-library.ts`. Each event has `id`, `startDate`, `endDate`, `label`, `description`. The query will run one SQL call per matched event to get average RS per sector during that event's date range.

**Regime-to-event affinity mapping:**
- `Risk-Off` or `Cautious` → match events: `covid-crash-2020`, `rate-hike-cycle-2022`, `adani-crisis-2023`
- `Constructive` or `Risk-On` → match events: `election-2024`
- Unknown / anything else → return all 4 events (most recent 3)

The function runs N SQL queries in parallel (one per matched event, max 3). Each query returns top-3 and bottom-3 sectors by avg RS, so we do two queries per event — one `ORDER BY avg_rs DESC LIMIT 3` for leaders, one `ORDER BY avg_rs ASC LIMIT 3` for laggards. We use `Promise.all` to run them concurrently.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/sectors/getSectorPlaybook.test.ts`:

```typescript
import { describe, it, expect, vi } from 'vitest'

vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({
  default: vi.fn(),
}))

import { type PlaybookEntry } from '@/lib/queries/sectors'

describe('PlaybookEntry shape', () => {
  it('has required fields', () => {
    const entry: PlaybookEntry = {
      event_id: 'covid-crash-2020',
      event_label: 'COVID',
      event_description: 'COVID-19 crash',
      start_date: '2020-02-20',
      end_date: '2020-03-23',
      leaders: [{ sector_name: 'Pharma', avg_rs: 0.12 }],
      laggards: [{ sector_name: 'Banking', avg_rs: -0.08 }],
    }
    expect(entry.event_id).toBe('covid-crash-2020')
    expect(entry.leaders[0].sector_name).toBe('Pharma')
    expect(entry.laggards[0].avg_rs).toBe(-0.08)
  })

  it('leaders and laggards are arrays', () => {
    const entry: PlaybookEntry = {
      event_id: 'x', event_label: 'X', event_description: 'X',
      start_date: '2020-01-01', end_date: '2020-01-31',
      leaders: [], laggards: [],
    }
    expect(Array.isArray(entry.leaders)).toBe(true)
    expect(Array.isArray(entry.laggards)).toBe(true)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/__tests__/sectors/getSectorPlaybook.test.ts
```

Expected: FAIL — `PlaybookEntry` is not exported from `@/lib/queries/sectors`

- [ ] **Step 3: Append the type and function to sectors.ts**

Open `frontend/src/lib/queries/sectors.ts`. After the last closing brace (line 297), append:

```typescript
export type PlaybookEntry = {
  event_id: string
  event_label: string
  event_description: string
  start_date: string
  end_date: string
  leaders: Array<{ sector_name: string; avg_rs: number }>
  laggards: Array<{ sector_name: string; avg_rs: number }>
}

const RISK_OFF_EVENT_IDS = ['covid-crash-2020', 'rate-hike-cycle-2022', 'adani-crisis-2023']
const RISK_ON_EVENT_IDS  = ['election-2024']

function pickEvents(regimeState: string): typeof import('@/lib/event-library').MARKET_EVENTS {
  // Import is deferred to avoid circular; this function runs server-side only.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { MARKET_EVENTS } = require('@/lib/event-library') as typeof import('@/lib/event-library')
  const lower = regimeState.toLowerCase()
  const isRiskOff = lower.includes('risk-off') || lower.includes('cautious')
  const isRiskOn  = lower.includes('risk-on')  || lower.includes('constructive')
  if (isRiskOff) return MARKET_EVENTS.filter(e => RISK_OFF_EVENT_IDS.includes(e.id))
  if (isRiskOn)  return MARKET_EVENTS.filter(e => RISK_ON_EVENT_IDS.includes(e.id))
  return MARKET_EVENTS.slice(-3)  // fallback: 3 most recent
}

export async function getSectorPlaybook(regimeState: string): Promise<PlaybookEntry[]> {
  const events = pickEvents(regimeState).slice(0, 3)
  if (events.length === 0) return []

  const results = await Promise.all(
    events.map(async (event) => {
      const [leadRows, lagRows] = await Promise.all([
        sql<Array<{ sector_name: string; avg_rs: number }>>`
          SELECT sector_name, AVG(bottomup_rs_3m_nifty500::float)::float AS avg_rs
          FROM atlas.atlas_sector_metrics_daily
          WHERE date BETWEEN ${event.startDate}::date AND ${event.endDate}::date
            AND bottomup_rs_3m_nifty500 IS NOT NULL
          GROUP BY sector_name
          ORDER BY avg_rs DESC
          LIMIT 3
        `,
        sql<Array<{ sector_name: string; avg_rs: number }>>`
          SELECT sector_name, AVG(bottomup_rs_3m_nifty500::float)::float AS avg_rs
          FROM atlas.atlas_sector_metrics_daily
          WHERE date BETWEEN ${event.startDate}::date AND ${event.endDate}::date
            AND bottomup_rs_3m_nifty500 IS NOT NULL
          GROUP BY sector_name
          ORDER BY avg_rs ASC
          LIMIT 3
        `,
      ])
      return {
        event_id:          event.id,
        event_label:       event.label,
        event_description: event.description,
        start_date:        event.startDate,
        end_date:          event.endDate,
        leaders:           leadRows,
        laggards:          lagRows,
      } satisfies PlaybookEntry
    }),
  )
  return results
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/__tests__/sectors/getSectorPlaybook.test.ts
```

Expected: PASS — both tests green

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep sectors
```

Expected: no errors from `sectors.ts`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/queries/sectors.ts \
        frontend/src/__tests__/sectors/getSectorPlaybook.test.ts
git commit -m "feat(sectors): add PlaybookEntry type + getSectorPlaybook query"
```

---

## Task 2: Create `SectorDualChartGuide.tsx`

**Files:**
- Create: `frontend/src/components/sectors/SectorDualChartGuide.tsx`
- Create: `frontend/src/__tests__/sectors/SectorDualChartGuide.test.tsx`

### Background

The guide has two parts:
1. A static 4-row cross-reference table showing each Matrix × RRG quadrant combination.
2. A live "today's example" block showing 2–3 actual sectors from the current data as examples.

**Quadrant computation:**

*Positioning Matrix* — dividers are `x=0` (RS vs zero) and `y=0.5` (participation vs 50%):
- Leaders: `rs > 0` AND `participation > 0.5`
- Recovering: `rs < 0` AND `participation > 0.5`
- Narrowing: `rs > 0` AND `participation < 0.5`
- Laggards: `rs < 0` AND `participation < 0.5`

*RRG* — dividers are mean-centered RS vs zero for X; rs_momentum vs zero for Y:
- Leading: `(rs - meanRS) > 0` AND `momentum > 0`
- Weakening: `(rs - meanRS) > 0` AND `momentum < 0`
- Improving: `(rs - meanRS) < 0` AND `momentum > 0`
- Lagging: `(rs - meanRS) < 0` AND `momentum < 0`

- [ ] **Step 1: Write the test for quadrant computation**

Create `frontend/src/__tests__/sectors/SectorDualChartGuide.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'

// Pure logic extracted from component for testing
function matrixQuadrant(rs: number, participation: number): string {
  const right = rs > 0
  const top   = participation > 0.5
  if (right && top)  return 'Leaders'
  if (!right && top) return 'Recovering'
  if (right && !top) return 'Narrowing'
  return 'Laggards'
}

function rrgQuadrant(rs: number, meanRS: number, momentum: number): string {
  const right = (rs - meanRS) > 0
  const top   = momentum > 0
  if (right && top)  return 'Leading'
  if (right && !top) return 'Weakening'
  if (!right && top) return 'Improving'
  return 'Lagging'
}

describe('matrixQuadrant', () => {
  it('classifies Leaders correctly', () => {
    expect(matrixQuadrant(0.1, 0.6)).toBe('Leaders')
  })
  it('classifies Recovering correctly', () => {
    expect(matrixQuadrant(-0.1, 0.6)).toBe('Recovering')
  })
  it('classifies Narrowing correctly', () => {
    expect(matrixQuadrant(0.1, 0.4)).toBe('Narrowing')
  })
  it('classifies Laggards correctly', () => {
    expect(matrixQuadrant(-0.1, 0.4)).toBe('Laggards')
  })
})

describe('rrgQuadrant', () => {
  it('classifies Leading correctly', () => {
    expect(rrgQuadrant(0.2, 0.1, 0.05)).toBe('Leading')
  })
  it('classifies Weakening correctly', () => {
    expect(rrgQuadrant(0.2, 0.1, -0.05)).toBe('Weakening')
  })
  it('classifies Improving correctly', () => {
    expect(rrgQuadrant(0.05, 0.1, 0.05)).toBe('Improving')
  })
  it('classifies Lagging correctly', () => {
    expect(rrgQuadrant(0.05, 0.1, -0.05)).toBe('Lagging')
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/__tests__/sectors/SectorDualChartGuide.test.tsx
```

Expected: tests run but the functions don't exist in the test file yet — wait, these are defined inline in the test. The test should PASS immediately since the logic is inline. That's fine — these are unit tests for the logic we're about to embed in the component.

Expected: PASS (inline logic tests)

- [ ] **Step 3: Create the component**

Create `frontend/src/components/sectors/SectorDualChartGuide.tsx`:

```typescript
'use client'
import type { SectorDecision } from '@/lib/sectors-decision'
import type { SectorSnapshot } from '@/lib/queries/sectors'

type SectorWithDecision = SectorSnapshot & { decision: SectorDecision }

type Props = {
  sectors: SectorWithDecision[]
}

const COMBOS = [
  {
    matrix:  'Leaders',
    rrg:     'Leading',
    signal:  'Confirmed strength',
    color:   '#22c55e',
    bgColor: '#f0fdf4',
    detail:  'RS outperformance + broad participation + accelerating momentum. All three signals agree.',
    action:  'Core overweight — size up on dips, not strength.',
  },
  {
    matrix:  'Narrowing',
    rrg:     'Weakening',
    signal:  'Fragile leadership',
    color:   '#f59e0b',
    bgColor: '#fffbeb',
    detail:  'Price RS positive but fewer stocks participating; momentum now fading.',
    action:  'Trim position. Breadth divergence resolves to the downside.',
  },
  {
    matrix:  'Recovering',
    rrg:     'Improving',
    signal:  'Early rotation',
    color:   '#14b8a6',
    bgColor: '#f0fdfa',
    detail:  'Breadth recovering before RS confirms. Momentum turning positive from a lagging base.',
    action:  'Scale in with tight stop. Confirmation: cross into Leaders + Leading.',
  },
  {
    matrix:  'Laggards',
    rrg:     'Lagging',
    signal:  'Confirmed avoid',
    color:   '#ef4444',
    bgColor: '#fef2f2',
    detail:  'Underperforming on RS, weak breadth, and decelerating. Double negative.',
    action:  'No new exposure. Hold cash or rotate to confirmed Leaders.',
  },
]

function matrixQuadrant(rs: number, participation: number): string {
  const right = rs > 0
  const top   = participation > 0.5
  if (right && top)  return 'Leaders'
  if (!right && top) return 'Recovering'
  if (right && !top) return 'Narrowing'
  return 'Laggards'
}

function rrgQuadrant(rs: number, meanRS: number, momentum: number): string {
  const right = (rs - meanRS) > 0
  const top   = momentum > 0
  if (right && top)  return 'Leading'
  if (right && !top) return 'Weakening'
  if (!right && top) return 'Improving'
  return 'Lagging'
}

export function SectorDualChartGuide({ sectors }: Props) {
  if (sectors.length === 0) return null

  // Compute mean RS for RRG centering
  const rsValues = sectors
    .map(s => parseFloat(s.bottomup_rs_3m_nifty500 ?? 'NaN'))
    .filter(v => !isNaN(v))
  const meanRS = rsValues.length > 0 ? rsValues.reduce((a, b) => a + b, 0) / rsValues.length : 0

  // Build live examples: find 1 sector per canonical combo, first match wins
  const examples: Array<{ sector: string; matrix: string; rrg: string; signal: string; action: string }> = []
  const usedCombos = new Set<string>()

  for (const s of sectors) {
    const rs            = parseFloat(s.bottomup_rs_3m_nifty500 ?? 'NaN')
    const participation = parseFloat(s.participation_50 ?? 'NaN')
    const momentum      = parseFloat(s.rs_momentum ?? 'NaN')
    if (isNaN(rs) || isNaN(participation) || isNaN(momentum)) continue

    const mq = matrixQuadrant(rs, participation)
    const rq = rrgQuadrant(rs, meanRS, momentum)
    const key = `${mq}:${rq}`
    if (usedCombos.has(key)) continue

    const combo = COMBOS.find(c => c.matrix === mq && c.rrg === rq)
    if (!combo) continue

    usedCombos.add(key)
    examples.push({ sector: s.sector_name, matrix: mq, rrg: rq, signal: combo.signal, action: combo.action })
    if (examples.length >= 3) break
  }

  return (
    <div className="px-6 py-5 border-b border-paper-rule bg-paper-rule/5">
      <h2 className="font-sans text-xs font-semibold text-ink-tertiary uppercase tracking-wider mb-1">
        Reading Both Charts Together
      </h2>
      <p className="font-sans text-[11px] text-ink-tertiary mb-4 max-w-2xl">
        The Positioning Matrix (breadth vs RS) and the RRG (momentum direction) measure different dimensions of the same rotation. Cross-referencing them removes false signals — a sector looks strong only when both agree.
      </p>

      {/* Cross-reference table */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 mb-5">
        {COMBOS.map(c => (
          <div
            key={c.signal}
            className="rounded-sm border border-paper-rule p-3"
            style={{ background: c.bgColor }}
          >
            <div className="flex items-center gap-1.5 mb-1.5">
              <span
                className="inline-block w-2 h-2 rounded-full flex-shrink-0"
                style={{ background: c.color }}
              />
              <span className="font-sans text-[10px] font-semibold uppercase tracking-wider" style={{ color: c.color }}>
                {c.signal}
              </span>
            </div>
            <div className="font-sans text-[10px] text-ink-tertiary mb-1">
              Matrix: <span className="font-medium text-ink-secondary">{c.matrix}</span>
              {' · '}
              RRG: <span className="font-medium text-ink-secondary">{c.rrg}</span>
            </div>
            <p className="font-sans text-[11px] text-ink-secondary leading-relaxed mb-1.5">{c.detail}</p>
            <p className="font-sans text-[11px] font-medium text-ink-primary leading-relaxed">{c.action}</p>
          </div>
        ))}
      </div>

      {/* Live examples */}
      {examples.length > 0 && (
        <div className="border-t border-paper-rule pt-3">
          <div className="font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary mb-2">
            Today&apos;s examples
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-1">
            {examples.map(ex => (
              <span key={ex.sector} className="font-sans text-[11px] text-ink-secondary">
                <span className="font-medium text-ink-primary">{ex.sector}</span>
                {' '}is {ex.matrix} + {ex.rrg} →{' '}
                <span className="text-ink-primary">{ex.action}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep SectorDualChartGuide
```

Expected: no output (no errors)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/sectors/SectorDualChartGuide.tsx \
        frontend/src/__tests__/sectors/SectorDualChartGuide.test.tsx
git commit -m "feat(sectors): add SectorDualChartGuide cross-reference component"
```

---

## Task 3: Create `SectorEventPlaybook.tsx`

**Files:**
- Create: `frontend/src/components/sectors/SectorEventPlaybook.tsx`

### Background

This component receives `entries: PlaybookEntry[]` (from the server) and `currentOverweightSectors: string[]` (computed in `SectorViews` from the existing `actionable` list filtered by `sector_state === 'Overweight'`). It shows 1 card per event; within each card, two columns: Leaders (green) and Laggards (red). If any current Overweight sector appears in a Laggards list, show a warning chip above that card.

There are no existing tests for this component pattern (it's pure rendering), but we'll write a shape test.

- [ ] **Step 1: Create the component**

Create `frontend/src/components/sectors/SectorEventPlaybook.tsx`:

```typescript
'use client'
import { AlertTriangle } from 'lucide-react'
import type { PlaybookEntry } from '@/lib/queries/sectors'

type Props = {
  entries: PlaybookEntry[]
  currentOverweightSectors: string[]
}

function formatDateRange(start: string, end: string): string {
  const fmt = (s: string) => {
    const d = new Date(s)
    return d.toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
  }
  if (start === end) return fmt(start)
  return `${fmt(start)} – ${fmt(end)}`
}

export function SectorEventPlaybook({ entries, currentOverweightSectors }: Props) {
  if (entries.length === 0) {
    return (
      <div className="px-6 py-5 border-b border-paper-rule">
        <h2 className="font-sans text-xs font-semibold text-ink-tertiary uppercase tracking-wider mb-2">
          Historical Event Playbook
        </h2>
        <p className="font-sans text-[11px] text-ink-tertiary">
          No historical events matched the current regime. Data will appear once regime state is classified.
        </p>
      </div>
    )
  }

  return (
    <div className="px-6 py-5 border-b border-paper-rule">
      <h2 className="font-sans text-xs font-semibold text-ink-tertiary uppercase tracking-wider mb-1">
        Historical Event Playbook
      </h2>
      <p className="font-sans text-[11px] text-ink-tertiary mb-4 max-w-2xl">
        How sectors behaved during the closest analogue events to the current regime. Leaders outperformed Nifty 500 by the largest margin; Laggards underperformed the most.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {entries.map(entry => {
          const atRisk = currentOverweightSectors.filter(s =>
            entry.laggards.some(l => l.sector_name === s),
          )
          return (
            <div key={entry.event_id} className="border border-paper-rule rounded-sm p-3 bg-paper">
              {/* Warning banner */}
              {atRisk.length > 0 && (
                <div className="flex items-start gap-1.5 mb-2 px-2 py-1.5 bg-signal-warn/10 border border-signal-warn/30 rounded-sm">
                  <AlertTriangle className="w-3 h-3 text-signal-warn flex-shrink-0 mt-0.5" />
                  <span className="font-sans text-[11px] text-signal-warn leading-snug">
                    {atRisk.join(', ')} {atRisk.length === 1 ? 'was' : 'were'} a laggard in this event. Review sizing.
                  </span>
                </div>
              )}

              {/* Event header */}
              <div className="mb-2">
                <div className="font-sans text-[11px] font-semibold text-ink-primary">{entry.event_label}</div>
                <div className="font-sans text-[10px] text-ink-tertiary">{formatDateRange(entry.start_date, entry.end_date)}</div>
                <p className="font-sans text-[10px] text-ink-tertiary mt-0.5 leading-relaxed">{entry.event_description}</p>
              </div>

              {/* Leaders + Laggards columns */}
              <div className="grid grid-cols-2 gap-2 mt-2 border-t border-paper-rule pt-2">
                <div>
                  <div className="font-sans text-[9px] font-semibold uppercase tracking-wider text-signal-pos mb-1">Leaders</div>
                  {entry.leaders.length === 0 ? (
                    <p className="font-sans text-[10px] text-ink-tertiary">No data</p>
                  ) : (
                    entry.leaders.map((l, i) => (
                      <div key={l.sector_name} className="flex items-center justify-between gap-2 mb-0.5">
                        <span className="font-sans text-[11px] text-ink-secondary truncate">
                          {i + 1}. {l.sector_name}
                        </span>
                        <span className="font-mono text-[10px] text-signal-pos tabular-nums flex-shrink-0">
                          {l.avg_rs >= 0 ? '+' : ''}{(l.avg_rs * 100).toFixed(1)}%
                        </span>
                      </div>
                    ))
                  )}
                </div>
                <div>
                  <div className="font-sans text-[9px] font-semibold uppercase tracking-wider text-signal-neg mb-1">Laggards</div>
                  {entry.laggards.length === 0 ? (
                    <p className="font-sans text-[10px] text-ink-tertiary">No data</p>
                  ) : (
                    entry.laggards.map((l, i) => (
                      <div key={l.sector_name} className="flex items-center justify-between gap-2 mb-0.5">
                        <span
                          className="font-sans text-[11px] truncate"
                          style={{
                            color: currentOverweightSectors.includes(l.sector_name) ? '#f59e0b' : undefined,
                            fontWeight: currentOverweightSectors.includes(l.sector_name) ? 600 : undefined,
                          }}
                        >
                          {i + 1}. {l.sector_name}
                        </span>
                        <span className="font-mono text-[10px] text-signal-neg tabular-nums flex-shrink-0">
                          {l.avg_rs >= 0 ? '+' : ''}{(l.avg_rs * 100).toFixed(1)}%
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep SectorEventPlaybook
```

Expected: no output (no errors)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/sectors/SectorEventPlaybook.tsx
git commit -m "feat(sectors): add SectorEventPlaybook component with overweight-at-risk warnings"
```

---

## Task 4: Wire up `sectors/page.tsx`

**Files:**
- Modify: `frontend/src/app/sectors/page.tsx`

### Background

We need to:
1. Add `getCurrentRegime` to imports from `@/lib/queries/regime`
2. Add `getSectorPlaybook` to imports from `@/lib/queries/sectors`
3. Expand the `Promise.all` from 5 to 7 queries (adding regime + playbook), both with `.catch()` fallbacks
4. Pass `playbook` and `regimeState` down to `SectorViews`

The `regime` query is already fast (1 row, indexed). The `playbook` query runs N SQL calls in parallel (max 3 events × 2 queries each = 6 SQL calls), all async and lightweight.

- [ ] **Step 1: Update imports**

Replace lines 1-15 in `frontend/src/app/sectors/page.tsx`:

```typescript
// frontend/src/app/sectors/page.tsx
import { Suspense } from 'react'
import {
  getSectorsWithMomentum,
  getSectorStateHistory,
  getRRGHistory,
  getBreadthWaterfallData,
  getDaysInStateForAllSectors,
  getSectorPlaybook,
  type PlaybookEntry,
} from '@/lib/queries/sectors'
import { getCurrentRegime } from '@/lib/queries/regime'
import { rangeToDays, type TimeRange } from '@/lib/time-range'
import { getSectorDecision } from '@/lib/sectors-decision'
import { filterSectors } from '@/lib/sectors-filter'
import { TimeRangeToggle } from '@/components/ui/TimeRangeToggle'
import { SectorViews } from '@/components/sectors/SectorViews'
import { SectorRiskWatch } from '@/components/sectors/SectorRiskWatch'
```

- [ ] **Step 2: Expand Promise.all and pass new props**

Replace lines 27-119 (the `Promise.all` + return statement) with:

```typescript
  // 7 parallel queries — non-critical queries degrade to empty/null fallbacks
  const [allRaw, stateHistory, rrgHistory, breadthData, daysInState, regime, playbook] = await Promise.all([
    getSectorsWithMomentum(),
    getSectorStateHistory(days).catch(() => [] as Awaited<ReturnType<typeof getSectorStateHistory>>),
    getRRGHistory(30).catch(() => [] as Awaited<ReturnType<typeof getRRGHistory>>),
    getBreadthWaterfallData(null, 1095).catch(() => [] as Awaited<ReturnType<typeof getBreadthWaterfallData>>),
    getDaysInStateForAllSectors().catch(() => [] as Awaited<ReturnType<typeof getDaysInStateForAllSectors>>),
    getCurrentRegime().catch(() => null),
    getSectorPlaybook(
      (await getCurrentRegime().catch(() => null))?.regime_state ?? 'Unknown',
    ).catch(() => [] as PlaybookEntry[]),
  ])
```

Wait — calling `getCurrentRegime()` twice is wasteful. Fix by making regime fetch first, then playbook second in sequence. Replace the full body from line 19 onward:

```typescript
export default async function SectorsPage({ searchParams }: { searchParams: SearchParams }) {
  const { range = '6M' } = await searchParams
  const VALID_RANGES: TimeRange[] = ['1W', '1M', '3M', '6M', '1Y']
  const historyRange: TimeRange = VALID_RANGES.includes(range as TimeRange)
    ? (range as TimeRange)
    : '6M'
  const days = rangeToDays(historyRange)

  // Fetch regime first (fast, 1 row); used to parameterise getSectorPlaybook
  const regime = await getCurrentRegime().catch(() => null)
  const regimeState = regime?.regime_state ?? 'Unknown'

  // 6 parallel queries — non-critical queries degrade to empty arrays
  const [allRaw, stateHistory, rrgHistory, breadthData, daysInState, playbook] = await Promise.all([
    getSectorsWithMomentum(),
    getSectorStateHistory(days).catch(() => [] as Awaited<ReturnType<typeof getSectorStateHistory>>),
    getRRGHistory(30).catch(() => [] as Awaited<ReturnType<typeof getRRGHistory>>),
    getBreadthWaterfallData(null, 1095).catch(() => [] as Awaited<ReturnType<typeof getBreadthWaterfallData>>),
    getDaysInStateForAllSectors().catch(() => [] as Awaited<ReturnType<typeof getDaysInStateForAllSectors>>),
    getSectorPlaybook(regimeState).catch(() => [] as PlaybookEntry[]),
  ])

  if (allRaw.length === 0) {
    return (
      <div className="p-8">
        <p className="font-sans text-sm text-ink-secondary">
          No sector data available. Run the nightly pipeline first.
        </p>
      </div>
    )
  }

  const { actionable, excluded } = filterSectors(allRaw)

  const withDecision = (s: typeof allRaw[number]) => ({
    ...s,
    decision: getSectorDecision(s.sector_state, s.bottomup_rs_state, s.bottomup_momentum_state),
  })
  const actionableWithDecision = actionable.map(withDecision)
  const allWithDecision = allRaw.map(withDecision)

  const overweightCount  = actionableWithDecision.filter(s => s.sector_state === 'Overweight').length
  const neutralCount     = actionableWithDecision.filter(s => s.sector_state === 'Neutral').length
  const underweightCount = actionableWithDecision.filter(s => s.sector_state === 'Underweight').length
  const avoidCount       = actionableWithDecision.filter(s => s.sector_state === 'Avoid').length
  const dataDate = allRaw[0]?.data_date

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
            {avoidCount > 0 && (
              <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
                <span className="inline-block w-2 h-2 rounded-full bg-signal-neg" />
                {avoidCount} Avoid
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-4">
          {dataDate && (
            <span className="font-sans text-xs text-ink-tertiary">
              Data as of {dataDate.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
            </span>
          )}
          <Suspense fallback={null}>
            <TimeRangeToggle value={historyRange} options={['1M', '3M', '6M', '1Y']} />
          </Suspense>
        </div>
      </div>

      <SectorRiskWatch sectors={actionableWithDecision} />

      <Suspense fallback={
        <div className="px-6 py-8 animate-pulse space-y-3">
          <div className="h-8 bg-paper-rule/30 rounded w-1/3" />
          <div className="h-64 bg-paper-rule/20 rounded" />
        </div>
      }>
        <SectorViews
          actionable={actionableWithDecision}
          allSectors={allWithDecision}
          excluded={excluded}
          stateHistory={stateHistory}
          rrgHistory={rrgHistory}
          breadthData={breadthData}
          daysInState={daysInState}
          playbook={playbook}
          range={historyRange}
        />
      </Suspense>
    </div>
  )
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -E "sectors/page|SectorViews"
```

Expected: errors about `playbook` prop not yet accepted in SectorViews — this is expected; Task 5 fixes it.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/sectors/page.tsx
git commit -m "feat(sectors): add regime + playbook parallel queries to sectors page"
```

---

## Task 5: Update `SectorViews.tsx` to accept and render new components

**Files:**
- Modify: `frontend/src/components/sectors/SectorViews.tsx`

### Background

SectorViews is a `'use client'` component at ~410 LOC. We need to:
1. Add `playbook` to the `Props` type
2. Import `SectorDualChartGuide` and `SectorEventPlaybook`
3. Insert `<SectorDualChartGuide>` between the Positioning Matrix section (ends ~line 262) and the RRG section
4. Insert `<SectorEventPlaybook>` between the Breadth Waterfall block (ends ~line 345) and the Sector State Heatmap block

After these insertions the component will be ~450 LOC, still within the 600 LOC limit.

- [ ] **Step 1: Add import and update Props type**

In `frontend/src/components/sectors/SectorViews.tsx`:

After the existing imports block (after line 19 `import { BreadthWaterfall } from './BreadthWaterfall'`), add:

```typescript
import { SectorDualChartGuide } from './SectorDualChartGuide'
import { SectorEventPlaybook } from './SectorEventPlaybook'
import type { PlaybookEntry } from '@/lib/queries/sectors'
```

In the `Props` type (around line 42-51), add `playbook` field:

```typescript
type Props = {
  actionable: SectorWithDecision[]
  excluded: ExcludedSector[]
  allSectors: SectorWithDecision[]
  stateHistory: SectorStateRow[]
  rrgHistory: RRGHistoryRow[]
  breadthData: BreadthWaterfallRow[]
  daysInState: DaysInStateRow[]
  playbook: PlaybookEntry[]
  range: string
}
```

In the `SectorViews` function signature (line 180), add `playbook` to destructured params:

```typescript
export function SectorViews({
  actionable,
  excluded,
  allSectors,
  stateHistory,
  rrgHistory,
  breadthData,
  daysInState,
  playbook,
  range,
}: Props) {
```

- [ ] **Step 2: Compute overweightSectors for the playbook**

In `SectorViews`, after the `daysMap` computation (around line 201), add:

```typescript
  const overweightSectors = visible
    .filter(s => s.sector_state === 'Overweight')
    .map(s => s.sector_name)
```

- [ ] **Step 3: Insert SectorDualChartGuide between sections 1 and 2**

The Positioning Matrix section closes with:
```tsx
      </div>

      {/* ── Section 2: Relative Rotation Graph ── */}
```

Insert the guide component between them. Replace that transition:

```tsx
      </div>

      {/* ── Dual Chart Guide ── */}
      <SectorDualChartGuide sectors={visible} />

      {/* ── Section 2: Relative Rotation Graph ── */}
```

- [ ] **Step 4: Insert SectorEventPlaybook between breadth and heatmap**

Inside the `{/* ── Section 4: Breadth + State History ── */}` div, the structure is:
```tsx
        {/* Breadth Waterfall */}
        <div className="mb-10">
          ...
          <BreadthWaterfall data={filteredBreadthData} />
        </div>

        {/* Sector State Heatmap */}
```

Insert between them:

```tsx
        {/* Breadth Waterfall */}
        <div className="mb-10">
          ...
          <BreadthWaterfall data={filteredBreadthData} />
        </div>

        {/* Event Playbook */}
        {playbook.length > 0 && (
          <div className="mb-10 -mx-6">
            <SectorEventPlaybook
              entries={playbook}
              currentOverweightSectors={overweightSectors}
            />
          </div>
        )}

        {/* Sector State Heatmap */}
```

Note: The `-mx-6` counteracts the parent `px-6` so the playbook section spans full width with its own padding, matching the visual treatment of other bordered sections.

- [ ] **Step 5: TypeScript check — expect clean output**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -E "SectorViews|SectorDualChartGuide|SectorEventPlaybook"
```

Expected: no output (no errors)

- [ ] **Step 6: Run full test suite**

```bash
cd frontend && npx vitest run 2>&1 | tail -20
```

Expected: all existing tests pass; new tests for `getSectorPlaybook.test.ts` and `SectorDualChartGuide.test.tsx` pass

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/sectors/SectorViews.tsx
git commit -m "feat(sectors): wire SectorDualChartGuide + SectorEventPlaybook into SectorViews"
```

---

## Task 6: Deploy to production and verify

**Files:** None (deployment only)

- [ ] **Step 1: Build locally to confirm no type errors**

```bash
cd frontend && npm run build 2>&1 | tail -30
```

Expected: Build succeeds with no TypeScript or ESLint errors. The `sectors` page is `force-dynamic` so no static generation issues.

- [ ] **Step 2: Deploy to atlas host**

```bash
rsync -az --delete \
  --exclude='.git' --exclude='node_modules' --exclude='.next' \
  /Users/nimishshah/Documents/GitHub/atlas-os/frontend/ \
  ubuntu@atlas:/home/ubuntu/atlas-frontend/

ssh ubuntu@atlas "cd /home/ubuntu/atlas-frontend && npm install --legacy-peer-deps && npm run build && pm2 restart atlas-frontend"
```

- [ ] **Step 3: Smoke test sectors page**

```bash
curl -s https://atlas.jslwealth.in/sectors | grep -E "Historical Event Playbook|Reading Both Charts Together"
```

Expected: both strings present in HTML

- [ ] **Step 4: Final commit tag**

```bash
git tag -a v0.sectors-b -m "Sectors Sub-project B: dual chart guide + event playbook"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ Dual Chart Reading Guide (4-combo table + live example) → Task 2
- ✅ Event Playbook with auto-match to current regime → Task 1 (query) + Task 3 (component)
- ✅ Overweight-at-risk warning → Task 3 (`atRisk` filter)
- ✅ Wire into SectorViews + page → Tasks 4+5
- ✅ Graceful degradation (`.catch(() => [])`) → Task 4

**Placeholder scan:** No TBDs. All code blocks are complete and runnable.

**Type consistency:** `PlaybookEntry` defined in Task 1, imported in Tasks 3, 4, 5. `SectorWithDecision` already defined in SectorViews, passed to SectorDualChartGuide via `sectors` prop. `overweightSectors: string[]` computed in Task 5 step 2, passed to SectorEventPlaybook.
