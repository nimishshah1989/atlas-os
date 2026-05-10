# Sprint 1: Design System Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared component and utility layer that all 5 intelligence pages depend on — without modifying any existing pages — and ship Migration 026 that gates Sprint 2's days_in_state column.

**Architecture:** New utilities in `frontend/src/lib/` and new components in `frontend/src/components/ui/` establish DRY patterns for screener columns, state chips with scalar values, metric tooltips, and commentary blocks. Existing Recharts bubble charts get their wrong hex values corrected (not rewritten). `screener-utils.tsx` extracts the filter/sort pattern from `StockScreener.tsx` so ETF, Fund, and Sector screeners don't duplicate it. Migration 026 adds `state_since_date DATE` to `atlas_stock_states_daily` via Alembic; the nightly pipeline writes it on every state classification run.

**Tech Stack:** Next.js 14 App Router · TypeScript · Tailwind CSS · Recharts (existing bubble charts — not D3) · Radix UI (tooltips) · Vitest + @testing-library/react (jsdom, globals: true) · Alembic + PostgreSQL

**Spec reference:** `docs/superpowers/specs/2026-05-10-atlas-intelligence-platform-design.md` Sections 1–7, 14–16, and Sprint 1 task list (line ~660)

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `frontend/src/lib/state-segment-utils.ts` | `buildSegments()` extracted from StateTimeline — shared by all timelines |
| Create | `frontend/src/lib/chart-colors.ts` | Canonical CHART_COLORS token map; sourced from globals.css |
| Modify | `frontend/src/lib/stock-formatters.tsx` | Fix RSPctileBar hardcoded wrong hex (#f59e0b → signal-warn token) |
| Modify | `frontend/src/components/ui/StateTimeline.tsx` | Import buildSegments from lib instead of defining inline |
| Modify | `frontend/src/components/stocks/StockBubbleChart.tsx` | Fix stockColor() wrong hex values; import from chart-colors |
| Create | `frontend/src/components/ui/StateValuePair.tsx` | Chip + scalar value layout (wraps RSStateChip/MomentumChip/RiskChip) |
| Create | `frontend/src/components/ui/MetricTooltip.tsx` | Wraps InfoTooltip; adds METRIC_DEFINITIONS lookup by metricKey |
| Create | `frontend/src/components/ui/CommentaryBlock.tsx` | Replaces Commentary.tsx stub; narrative + context cards |
| Create | `frontend/src/lib/screener-utils.ts` | Filter/sort logic to share across StockScreener, ETF, Fund screeners |
| Create | `frontend/src/lib/commentary/stocks.ts` | buildCommentary() condition array for stocks page |
| Create | `migrations/versions/026_add_state_since_date.py` | Alembic migration — adds state_since_date DATE, backfills from history |
| Create | `frontend/src/components/ui/__tests__/StateValuePair.test.tsx` | Tests for StateValuePair |
| Create | `frontend/src/components/ui/__tests__/MetricTooltip.test.tsx` | Tests for MetricTooltip |
| Create | `frontend/src/components/ui/__tests__/CommentaryBlock.test.tsx` | Tests for CommentaryBlock |
| Create | `frontend/src/lib/__tests__/state-segment-utils.test.ts` | Tests for buildSegments |
| Create | `frontend/src/lib/__tests__/screener-utils.test.ts` | Tests for filter/sort utilities |
| Create | `frontend/src/lib/commentary/__tests__/stocks.test.ts` | Tests for every buildCommentary condition branch |

---

## Task 1: Extract buildSegments to a shared utility

**Why:** StateTimeline.tsx defines `buildSegments()` inline. Sprint 2 adds a compact timeline in expandable screener rows and Sprint 3 adds D3-based timelines in deep dives. They all need the same segment logic. Extract it before Sprint 2 so they import, not copy.

**Files:**
- Create: `frontend/src/lib/state-segment-utils.ts`
- Create: `frontend/src/lib/__tests__/state-segment-utils.test.ts`
- Modify: `frontend/src/components/ui/StateTimeline.tsx`

- [ ] **Step 1.1: Write the failing test**

```typescript
// frontend/src/lib/__tests__/state-segment-utils.test.ts
import { describe, it, expect } from 'vitest'
import { buildSegments } from '@/lib/state-segment-utils'

describe('buildSegments', () => {
  it('returns empty array for empty input', () => {
    expect(buildSegments([])).toEqual([])
  })

  it('returns single segment for uniform state', () => {
    const rows = [
      { date: new Date('2024-01-01'), state: 'Risk-On' },
      { date: new Date('2024-01-02'), state: 'Risk-On' },
      { date: new Date('2024-01-03'), state: 'Risk-On' },
    ]
    const result = buildSegments(rows)
    expect(result).toHaveLength(1)
    expect(result[0].state).toBe('Risk-On')
    expect(result[0].days).toBe(3)
  })

  it('splits on state change', () => {
    const rows = [
      { date: new Date('2024-01-01'), state: 'Risk-On' },
      { date: new Date('2024-01-02'), state: 'Risk-On' },
      { date: new Date('2024-01-03'), state: 'Cautious' },
      { date: new Date('2024-01-04'), state: 'Cautious' },
    ]
    const result = buildSegments(rows)
    expect(result).toHaveLength(2)
    expect(result[0].state).toBe('Risk-On')
    expect(result[0].days).toBe(2)
    expect(result[1].state).toBe('Cautious')
    expect(result[1].days).toBe(2)
  })

  it('total days across all segments equals input row count', () => {
    const rows = [
      { date: new Date('2024-01-01'), state: 'A' },
      { date: new Date('2024-01-02'), state: 'B' },
      { date: new Date('2024-01-03'), state: 'A' },
    ]
    const result = buildSegments(rows)
    const total = result.reduce((s, seg) => s + seg.days, 0)
    expect(total).toBe(rows.length)
  })

  it('startDate and endDate are set correctly', () => {
    const rows = [
      { date: new Date('2024-01-01'), state: 'Risk-On' },
      { date: new Date('2024-01-05'), state: 'Cautious' },
    ]
    const result = buildSegments(rows)
    expect(result[0].startDate).toEqual(new Date('2024-01-01'))
    expect(result[0].endDate).toEqual(new Date('2024-01-01'))
    expect(result[1].startDate).toEqual(new Date('2024-01-05'))
  })
})
```

- [ ] **Step 1.2: Run test to confirm it fails (module not found)**

```bash
cd frontend && npx vitest run src/lib/__tests__/state-segment-utils.test.ts
```

Expected: FAIL — `Cannot find module '@/lib/state-segment-utils'`

- [ ] **Step 1.3: Create the utility**

```typescript
// frontend/src/lib/state-segment-utils.ts
export type Segment = {
  state: string
  startDate: Date
  endDate: Date
  days: number
}

export function buildSegments(rows: { date: Date; state: string }[]): Segment[] {
  if (rows.length === 0) return []
  const segments: Segment[] = []
  let current = rows[0]
  let startDate = rows[0].date

  for (let i = 1; i < rows.length; i++) {
    if (rows[i].state !== current.state) {
      segments.push({
        state: current.state,
        startDate,
        endDate: rows[i - 1].date,
        days: i - segments.reduce((s, seg) => s + seg.days, 0),
      })
      current = rows[i]
      startDate = rows[i].date
    }
  }
  segments.push({
    state: current.state,
    startDate,
    endDate: rows[rows.length - 1].date,
    days: rows.length - segments.reduce((s, seg) => s + seg.days, 0),
  })
  return segments
}
```

- [ ] **Step 1.4: Run test to confirm it passes**

```bash
cd frontend && npx vitest run src/lib/__tests__/state-segment-utils.test.ts
```

Expected: PASS — 5 tests

- [ ] **Step 1.5: Update StateTimeline.tsx to import from the utility**

In `frontend/src/components/ui/StateTimeline.tsx`:
- Remove the inline `type Segment = { ... }` block and the inline `function buildSegments(...)` function
- Add this import at the top:

```typescript
import { buildSegments, type Segment } from '@/lib/state-segment-utils'
```

The rest of StateTimeline.tsx is unchanged — it still uses `buildSegments()` and `Segment` by name.

- [ ] **Step 1.6: Verify the app still typechecks**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors related to StateTimeline

- [ ] **Step 1.7: Commit**

```bash
git add frontend/src/lib/state-segment-utils.ts \
        frontend/src/lib/__tests__/state-segment-utils.test.ts \
        frontend/src/components/ui/StateTimeline.tsx
git commit -m "refactor(sprint1): extract buildSegments to lib/state-segment-utils"
```

---

## Task 2: Create canonical CHART_COLORS token map

**Why:** Bubble charts, state timelines, and D3 visualizations all need the same semantic color palette. Right now each file hardcodes its own hex strings — some of them wrong. This utility is the single source of truth: it reads from globals.css design tokens (the strings here must match `--color-*` vars in globals.css).

**Files:**
- Create: `frontend/src/lib/chart-colors.ts`

- [ ] **Step 2.1: Create chart-colors.ts**

```typescript
// frontend/src/lib/chart-colors.ts
// Hex values mirror globals.css CSS custom properties exactly.
// Recharts and D3 both need hex, not Tailwind class names.

export const CHART_COLORS = {
  // RS states (7-level)
  rsLeader:        '#2F6B43',   // --color-signal-pos
  rsStrong:        '#1D9E75',   // --color-teal
  rsEmerging:      '#25394A',   // --color-accent
  rsConsolidating: '#B8860B',   // --color-signal-warn
  rsAverage:       '#8C8278',   // --color-ink-tertiary
  rsWeak:          '#B0492C',   // --color-signal-neg
  rsLaggard:       '#B0492C',   // --color-signal-neg

  // Momentum states
  momAccelerating:  '#2F6B43',
  momImproving:     '#1D9E75',
  momFlat:          '#8C8278',
  momDeteriorating: '#B8860B',
  momCollapsing:    '#B0492C',

  // Regime states
  riskOn:         '#2F6B43',
  constructive:   '#1D9E75',
  cautious:       '#B8860B',
  riskOff:        '#B0492C',

  // Neutral / structural
  grid:        '#C2B8A8',   // --color-paper-rule
  inkTertiary: '#8C8278',   // --color-ink-tertiary
  paper:       '#F8F4EC',   // --color-paper
} as const

/** Map RS state string → chart hex color. Falls back to inkTertiary. */
export function rsStateColor(rsState: string | null): string {
  switch (rsState) {
    case 'Leader':        return CHART_COLORS.rsLeader
    case 'Strong':        return CHART_COLORS.rsStrong
    case 'Emerging':      return CHART_COLORS.rsEmerging
    case 'Consolidating': return CHART_COLORS.rsConsolidating
    case 'Average':       return CHART_COLORS.rsAverage
    case 'Weak':          return CHART_COLORS.rsWeak
    case 'Laggard':       return CHART_COLORS.rsLaggard
    default:              return CHART_COLORS.inkTertiary
  }
}

/** Map RS + Momentum → bubble chart color (Strong fading → warn; others follow RS). */
export function bubbleColor(rsState: string | null, momState: string | null): string {
  if (rsState === 'Leader') return CHART_COLORS.rsLeader
  if (rsState === 'Strong' && (momState === 'Deteriorating' || momState === 'Collapsing'))
    return CHART_COLORS.rsConsolidating
  if (rsState === 'Strong')        return CHART_COLORS.rsStrong
  if (rsState === 'Emerging')      return CHART_COLORS.rsEmerging
  if (rsState === 'Consolidating') return CHART_COLORS.rsConsolidating
  if (rsState === 'Average')       return CHART_COLORS.rsAverage
  return CHART_COLORS.rsWeak
}
```

- [ ] **Step 2.2: Verify it typechecks**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "chart-colors"
```

Expected: no output (no errors)

- [ ] **Step 2.3: Commit**

```bash
git add frontend/src/lib/chart-colors.ts
git commit -m "feat(sprint1): add canonical CHART_COLORS token map"
```

---

## Task 3: Fix bubble chart colors in stocks/StockBubbleChart.tsx

**Why:** The `stockColor()` function in `frontend/src/components/stocks/StockBubbleChart.tsx` uses hex values that don't match the design system. Wrong colors: `#f59e0b` (Consolidating — should be `#B8860B`), `#0ea5e9` (Emerging — should be `#25394A`), `#94a3b8` (Average — should be `#8C8278`), `#ef4444` (Weak/Laggard — should be `#B0492C`). The fix: replace the inline `stockColor()` function with an import from `lib/chart-colors.ts`.

This chart uses **Recharts** (ScatterChart + ResponsiveContainer). Do not migrate it to D3.

**Files:**
- Modify: `frontend/src/components/stocks/StockBubbleChart.tsx`

- [ ] **Step 3.1: In StockBubbleChart.tsx, add the import and remove the inline function**

At the top of `frontend/src/components/stocks/StockBubbleChart.tsx`, add:

```typescript
import { bubbleColor } from '@/lib/chart-colors'
```

Remove the entire `function stockColor(rs: string | null, mom: string | null): string { ... }` block (lines 39–47 in the original file).

Replace the usage on the line that was:
```typescript
color: stockColor(s.rs_state, s.momentum_state),
```
with:
```typescript
color: bubbleColor(s.rs_state, s.momentum_state),
```

- [ ] **Step 3.2: Verify typechecks**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -i "bubble\|stockcolor"
```

Expected: no output

- [ ] **Step 3.3: Verify no lint errors**

```bash
cd frontend && npx eslint src/components/stocks/StockBubbleChart.tsx --max-warnings 0
```

Expected: no errors or warnings

- [ ] **Step 3.4: Commit**

```bash
git add frontend/src/components/stocks/StockBubbleChart.tsx
git commit -m "fix(sprint1): correct bubble chart colors to match design tokens"
```

---

## Task 4: Fix RSPctileBar hardcoded wrong hex in stock-formatters.tsx

**Why:** `RSPctileBar` in `stock-formatters.tsx` uses `#f59e0b` (Tailwind amber-500) instead of `#B8860B` (the design system `--color-signal-warn` / `signal-warn`). Same issue applies to the `#ef4444` for low RS. Fix by using the CHART_COLORS constants.

**Files:**
- Modify: `frontend/src/lib/stock-formatters.tsx`

- [ ] **Step 4.1: Update RSPctileBar**

In `frontend/src/lib/stock-formatters.tsx`, add import at the top:

```typescript
import { CHART_COLORS } from '@/lib/chart-colors'
```

Replace the hardcoded hex in `RSPctileBar`:

```typescript
// BEFORE
const color = n >= 0.7 ? '#2F6B43' : n >= 0.4 ? '#f59e0b' : '#ef4444'

// AFTER
const color = n >= 0.7 ? CHART_COLORS.rsLeader : n >= 0.4 ? CHART_COLORS.rsConsolidating : CHART_COLORS.rsWeak
```

Also fix `PosSizeBar` which has the same problem:

```typescript
// BEFORE
const color = n >= 0.7 ? '#2F6B43' : n >= 0.35 ? '#1D9E75' : n > 0 ? '#94a3b8' : '#ef4444'

// AFTER
const color = n >= 0.7 ? CHART_COLORS.rsLeader : n >= 0.35 ? CHART_COLORS.rsStrong : n > 0 ? CHART_COLORS.inkTertiary : CHART_COLORS.rsWeak
```

- [ ] **Step 4.2: Verify typechecks**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "stock-formatters"
```

Expected: no output

- [ ] **Step 4.3: Commit**

```bash
git add frontend/src/lib/stock-formatters.tsx
git commit -m "fix(sprint1): use CHART_COLORS constants in stock-formatters bars"
```

---

## Task 5: Build StateValuePair component

**Why:** The spec (Section 5 — Shared UI Anatomy) requires that every state chip in a screener column show both the state label and a scalar value (e.g. "Leader · 87th"). This is a new layout wrapper around the existing `RSStateChip`, `MomentumChip`, and `RiskChip` from `stock-formatters.tsx`.

**Files:**
- Create: `frontend/src/components/ui/StateValuePair.tsx`
- Create: `frontend/src/components/ui/__tests__/StateValuePair.test.tsx`

- [ ] **Step 5.1: Write failing tests**

```typescript
// frontend/src/components/ui/__tests__/StateValuePair.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { StateValuePair } from '../StateValuePair'

describe('StateValuePair', () => {
  it('renders the chip and scalar side by side', () => {
    render(<StateValuePair chipType="rs" state="Leader" scalar="87th" />)
    // chip label
    expect(screen.getByText('Leader')).toBeInTheDocument()
    // scalar value
    expect(screen.getByText('87th')).toBeInTheDocument()
  })

  it('renders null scalar as em-dash', () => {
    render(<StateValuePair chipType="rs" state="Strong" scalar={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renders em-dash when state is null', () => {
    render(<StateValuePair chipType="rs" state={null} scalar={null} />)
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('renders momentum chip type', () => {
    render(<StateValuePair chipType="momentum" state="Accelerating" scalar="↑ 12d" />)
    expect(screen.getByText('Accelerating')).toBeInTheDocument()
    expect(screen.getByText('↑ 12d')).toBeInTheDocument()
  })

  it('renders risk chip type', () => {
    render(<StateValuePair chipType="risk" state="Low" scalar="σ 18%" />)
    expect(screen.getByText('Low')).toBeInTheDocument()
    expect(screen.getByText('σ 18%')).toBeInTheDocument()
  })
})
```

- [ ] **Step 5.2: Run test to confirm it fails**

```bash
cd frontend && npx vitest run src/components/ui/__tests__/StateValuePair.test.tsx
```

Expected: FAIL — `Cannot find module '../StateValuePair'`

- [ ] **Step 5.3: Implement StateValuePair**

```typescript
// frontend/src/components/ui/StateValuePair.tsx
'use client'
import { RSStateChip, MomentumChip, RiskChip } from '@/lib/stock-formatters'

type ChipType = 'rs' | 'momentum' | 'risk'

type Props = {
  chipType: ChipType
  state: string | null
  scalar: string | null
  className?: string
}

export function StateValuePair({ chipType, state, scalar, className = '' }: Props) {
  const chip =
    chipType === 'rs'       ? <RSStateChip value={state} /> :
    chipType === 'momentum' ? <MomentumChip value={state} /> :
                              <RiskChip value={state} />

  return (
    <span className={`inline-flex items-center gap-1.5 ${className}`}>
      {chip}
      <span className="font-mono text-[10px] text-ink-tertiary tabular-nums">
        {scalar ?? '—'}
      </span>
    </span>
  )
}
```

- [ ] **Step 5.4: Run test to confirm it passes**

```bash
cd frontend && npx vitest run src/components/ui/__tests__/StateValuePair.test.tsx
```

Expected: PASS — 5 tests

- [ ] **Step 5.5: Commit**

```bash
git add frontend/src/components/ui/StateValuePair.tsx \
        frontend/src/components/ui/__tests__/StateValuePair.test.tsx
git commit -m "feat(sprint1): add StateValuePair component (chip + scalar)"
```

---

## Task 6: Build MetricTooltip component

**Why:** Every metric column in every screener needs an ⓘ tooltip that explains what the metric means. `InfoTooltip` already renders the Radix tooltip UI with a string. `MetricTooltip` adds a lookup layer: given a `metricKey`, it finds the definition in `METRIC_DEFINITIONS` and renders the right content — so callers write `<MetricTooltip metricKey="rs_pctile_3m" />` instead of duplicating the definition string.

`TOOLTIPS` in `lib/tooltips.ts` has regime-page tooltips. `MetricTooltip` needs a screener-specific definition map (`METRIC_DEFINITIONS`) that we co-locate in `MetricTooltip.tsx`.

**Files:**
- Create: `frontend/src/components/ui/MetricTooltip.tsx`
- Create: `frontend/src/components/ui/__tests__/MetricTooltip.test.tsx`

- [ ] **Step 6.1: Write failing tests**

```typescript
// frontend/src/components/ui/__tests__/MetricTooltip.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { MetricTooltip } from '../MetricTooltip'

describe('MetricTooltip', () => {
  it('renders the info button', () => {
    render(<MetricTooltip metricKey="rs_pctile_3m" />)
    expect(screen.getByRole('button', { name: /info/i })).toBeInTheDocument()
  })

  it('renders without error for an unknown metricKey', () => {
    // Should not throw — gracefully renders nothing or a fallback
    expect(() =>
      render(<MetricTooltip metricKey={"nonexistent_key" as never} />)
    ).not.toThrow()
  })
})
```

- [ ] **Step 6.2: Run test to confirm it fails**

```bash
cd frontend && npx vitest run src/components/ui/__tests__/MetricTooltip.test.tsx
```

Expected: FAIL — `Cannot find module '../MetricTooltip'`

- [ ] **Step 6.3: Implement MetricTooltip**

```typescript
// frontend/src/components/ui/MetricTooltip.tsx
'use client'
import { InfoTooltip } from './InfoTooltip'

export const METRIC_DEFINITIONS = {
  rs_pctile_3m:     'RS Percentile (3M): rank of this stock\'s 3-month relative strength vs Nifty 500 peers. 90th = beats 90% of stocks.',
  ret_1m:           '1-month total return (price change, unadjusted for dividends).',
  ret_3m:           '3-month total return.',
  ret_6m:           '6-month total return.',
  ret_1y:           '12-month total return.',
  realized_vol_63:  'Annualized realized volatility over the last 63 trading days (~3 months). Lower = smoother ride.',
  avg_volume_20:    '20-day average daily traded volume. Used to judge liquidity and position sizing.',
  days_in_state:    'Calendar days the stock has been in its current RS state without a state change.',
  rs_state:         'Relative-strength state: Leader / Strong / Emerging / Consolidating / Average / Weak / Laggard. Computed daily from RS percentile trajectory.',
  momentum_state:   'Momentum state: direction and acceleration of RS trend. Accelerating = RS at 20-day high.',
  risk_state:       'Risk state: Low / Normal / Elevated / High — based on realized volatility vs the universe median.',
  volume_state:     'Volume state: Accumulation / Steady-Buying / Neutral / Distribution / Heavy Distribution.',
  position_size_pct:'Recommended position size as % of portfolio. Scaled by RS state, momentum, and regime deployment multiplier.',
  extension:        'Extension above the 20-day EMA (%). High extension = overbought relative to short-term trend.',
  drawdown_from_peak: 'Drawdown from the 52-week closing high. Greater than 20% is a significant pull-back.',
  gold_rs:          'RS percentile vs Gold (₹). Stocks with gold_rs > 50 are outperforming Gold over 3 months.',
  weinstein_gate:   'Weinstein Stage 2 pass/fail. PASS = above rising 30-week MA. FAIL = avoid regardless of RS.',
} as const

export type MetricKey = keyof typeof METRIC_DEFINITIONS

type Props = {
  metricKey: MetricKey
  className?: string
}

export function MetricTooltip({ metricKey, className }: Props) {
  const content = METRIC_DEFINITIONS[metricKey]
  if (!content) return null
  return <InfoTooltip content={content} className={className} />
}
```

- [ ] **Step 6.4: Run tests to confirm they pass**

```bash
cd frontend && npx vitest run src/components/ui/__tests__/MetricTooltip.test.tsx
```

Expected: PASS — 2 tests

- [ ] **Step 6.5: Commit**

```bash
git add frontend/src/components/ui/MetricTooltip.tsx \
        frontend/src/components/ui/__tests__/MetricTooltip.test.tsx
git commit -m "feat(sprint1): add MetricTooltip with METRIC_DEFINITIONS lookup"
```

---

## Task 7: Build CommentaryBlock component

**Why:** `Commentary.tsx` is a 12-line stub that only renders a single `<p>` tag. The spec requires a CommentaryBlock that renders: (1) a narrative paragraph, (2) optional context cards with a metric label + value, and (3) optionally a "last updated" timestamp. The stub is kept for backward-compat until Sprint 2 removes all its call sites.

**Files:**
- Create: `frontend/src/components/ui/CommentaryBlock.tsx`
- Create: `frontend/src/components/ui/__tests__/CommentaryBlock.test.tsx`

- [ ] **Step 7.1: Write failing tests**

```typescript
// frontend/src/components/ui/__tests__/CommentaryBlock.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { CommentaryBlock } from '../CommentaryBlock'

describe('CommentaryBlock', () => {
  it('renders the narrative text', () => {
    render(<CommentaryBlock narrative="Market breadth is improving." />)
    expect(screen.getByText('Market breadth is improving.')).toBeInTheDocument()
  })

  it('renders context cards when provided', () => {
    render(
      <CommentaryBlock
        narrative="Strong regime."
        contextCards={[
          { label: 'Investable', value: '42 stocks' },
          { label: 'Leaders', value: '18' },
        ]}
      />
    )
    expect(screen.getByText('Investable')).toBeInTheDocument()
    expect(screen.getByText('42 stocks')).toBeInTheDocument()
    expect(screen.getByText('Leaders')).toBeInTheDocument()
  })

  it('renders without context cards', () => {
    render(<CommentaryBlock narrative="No cards here." />)
    expect(screen.getByText('No cards here.')).toBeInTheDocument()
  })

  it('renders data_as_of when provided', () => {
    render(<CommentaryBlock narrative="Latest." dataAsOf="2026-05-09" />)
    expect(screen.getByText(/2026-05-09/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 7.2: Run test to confirm it fails**

```bash
cd frontend && npx vitest run src/components/ui/__tests__/CommentaryBlock.test.tsx
```

Expected: FAIL — `Cannot find module '../CommentaryBlock'`

- [ ] **Step 7.3: Implement CommentaryBlock**

```typescript
// frontend/src/components/ui/CommentaryBlock.tsx
type ContextCard = {
  label: string
  value: string
  delta?: string
  deltaPositive?: boolean
}

type Props = {
  narrative: string
  contextCards?: ContextCard[]
  dataAsOf?: string
  className?: string
}

export function CommentaryBlock({ narrative, contextCards, dataAsOf, className = '' }: Props) {
  return (
    <div className={`space-y-3 ${className}`}>
      <p className="font-sans text-sm text-ink-secondary leading-relaxed">{narrative}</p>
      {contextCards && contextCards.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {contextCards.map((card, i) => (
            <div
              key={i}
              className="bg-paper-rule/10 border border-paper-rule/40 rounded-sm px-2.5 py-1.5"
            >
              <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wide">
                {card.label}
              </div>
              <div className="font-sans text-sm font-medium text-ink-primary flex items-center gap-1">
                {card.value}
                {card.delta && (
                  <span className={`text-xs ${card.deltaPositive ? 'text-signal-pos' : 'text-signal-neg'}`}>
                    {card.delta}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      {dataAsOf && (
        <p className="font-sans text-[10px] text-ink-tertiary">
          as of {dataAsOf}
        </p>
      )}
    </div>
  )
}
```

- [ ] **Step 7.4: Run tests to confirm they pass**

```bash
cd frontend && npx vitest run src/components/ui/__tests__/CommentaryBlock.test.tsx
```

Expected: PASS — 4 tests

- [ ] **Step 7.5: Commit**

```bash
git add frontend/src/components/ui/CommentaryBlock.tsx \
        frontend/src/components/ui/__tests__/CommentaryBlock.test.tsx
git commit -m "feat(sprint1): add CommentaryBlock with context cards"
```

---

## Task 8: Extract screener-utils.ts

**Why:** `StockScreener.tsx` contains filter and sort logic (filter chips, search, RS/momentum/risk sort ranking) that ETF and Fund screeners will duplicate verbatim in Sprint 2. Extract the pure logic functions before Sprint 2 starts so they stay in one place.

**Files:**
- Create: `frontend/src/lib/screener-utils.ts`
- Create: `frontend/src/lib/__tests__/screener-utils.test.ts`

- [ ] **Step 8.1: Write failing tests**

```typescript
// frontend/src/lib/__tests__/screener-utils.test.ts
import { describe, it, expect } from 'vitest'
import { stateRank, matchesSearch, buildSortKey } from '@/lib/screener-utils'

describe('stateRank', () => {
  it('returns 0 for the first item in the order', () => {
    const order = ['Leader', 'Strong', 'Average']
    expect(stateRank(order, 'Leader')).toBe(0)
  })

  it('returns index for a known state', () => {
    const order = ['Leader', 'Strong', 'Average']
    expect(stateRank(order, 'Average')).toBe(2)
  })

  it('returns order.length for an unknown state', () => {
    const order = ['Leader', 'Strong']
    expect(stateRank(order, 'Unknown')).toBe(2)
  })

  it('returns order.length for null', () => {
    const order = ['Leader', 'Strong']
    expect(stateRank(order, null)).toBe(2)
  })
})

describe('matchesSearch', () => {
  it('matches symbol case-insensitively', () => {
    expect(matchesSearch({ symbol: 'RELIANCE', companyName: 'Reliance Industries' }, 'rel')).toBe(true)
  })

  it('matches companyName case-insensitively', () => {
    expect(matchesSearch({ symbol: 'HDFC', companyName: 'HDFC Bank Ltd' }, 'bank')).toBe(true)
  })

  it('returns true for empty query', () => {
    expect(matchesSearch({ symbol: 'X', companyName: 'Y' }, '')).toBe(true)
  })

  it('returns false when neither symbol nor name matches', () => {
    expect(matchesSearch({ symbol: 'INFY', companyName: 'Infosys' }, 'reliance')).toBe(false)
  })
})

describe('buildSortKey', () => {
  it('returns a number for rs_pctile', () => {
    const result = buildSortKey('rs_pctile_3m', { rs_pctile_3m: '0.85' } as never)
    expect(typeof result).toBe('number')
  })

  it('treats null numeric as -Infinity for desc sort', () => {
    const result = buildSortKey('rs_pctile_3m', { rs_pctile_3m: null } as never)
    expect(result).toBe(-Infinity)
  })
})
```

- [ ] **Step 8.2: Run test to confirm it fails**

```bash
cd frontend && npx vitest run src/lib/__tests__/screener-utils.test.ts
```

Expected: FAIL — module not found

- [ ] **Step 8.3: Implement screener-utils.ts**

```typescript
// frontend/src/lib/screener-utils.ts

export const RS_ORDER    = ['Leader', 'Strong', 'Consolidating', 'Emerging', 'Average', 'Weak', 'Laggard']
export const MOM_ORDER   = ['Accelerating', 'Improving', 'Flat', 'Deteriorating', 'Collapsing']
export const RISK_ORDER  = ['Low', 'Normal', 'Elevated', 'High', 'Below Trend']
export const VOL_ORDER   = ['Accumulation', 'Steady-Buying', 'Neutral', 'Distribution', 'Heavy Distribution']

/** Index of state in the given order array. Returns order.length if unknown or null. */
export function stateRank(order: string[], val: string | null): number {
  if (!val) return order.length
  const i = order.indexOf(val)
  return i === -1 ? order.length : i
}

/** True if the row matches a free-text search query (case-insensitive, empty = match all). */
export function matchesSearch(
  row: { symbol: string; companyName: string },
  query: string,
): boolean {
  if (!query.trim()) return true
  const q = query.trim().toLowerCase()
  return row.symbol.toLowerCase().includes(q) || row.companyName.toLowerCase().includes(q)
}

type NumericStringRow = Record<string, string | null | boolean | number | undefined>

/**
 * Returns a sort key for a given column on a screener row.
 * Numeric columns: parse to float, null → -Infinity (sink to bottom in DESC).
 * State columns: return stateRank so that 'Leader' sorts before 'Laggard' in ASC.
 * String columns: return the string directly for localeCompare.
 */
export function buildSortKey(
  column: string,
  row: NumericStringRow,
): number | string {
  const v = row[column]
  if (column === 'rs_state')       return stateRank(RS_ORDER, v as string | null)
  if (column === 'momentum_state') return stateRank(MOM_ORDER, v as string | null)
  if (column === 'risk_state')     return stateRank(RISK_ORDER, v as string | null)
  if (column === 'volume_state')   return stateRank(VOL_ORDER, v as string | null)
  // Numeric columns
  if (typeof v === 'string') return v === '' || v == null ? -Infinity : parseFloat(v)
  if (v == null) return -Infinity
  if (typeof v === 'number') return v
  if (typeof v === 'boolean') return v ? 1 : 0
  return -Infinity
}
```

- [ ] **Step 8.4: Run tests to confirm they pass**

```bash
cd frontend && npx vitest run src/lib/__tests__/screener-utils.test.ts
```

Expected: PASS — 9 tests

- [ ] **Step 8.5: Commit**

```bash
git add frontend/src/lib/screener-utils.ts \
        frontend/src/lib/__tests__/screener-utils.test.ts
git commit -m "feat(sprint1): add screener-utils (stateRank, matchesSearch, buildSortKey)"
```

---

## Task 9: Build buildCommentary for stocks page

**Why:** The spec requires a deterministic, condition-array commentary engine for the Stocks page (Section 9). The engine receives pre-fetched `PageAggregates` from the Page server component and returns a narrative string + context cards without a second DB round-trip. Building this in Sprint 1 as a pure function — with a test for every condition branch — means Sprint 2 can wire it into `CommentaryBlock` without debugging logic.

**Files:**
- Create: `frontend/src/lib/commentary/stocks.ts`
- Create: `frontend/src/lib/commentary/__tests__/stocks.test.ts`

- [ ] **Step 9.1: Write failing tests for every condition branch**

```typescript
// frontend/src/lib/commentary/__tests__/stocks.test.ts
import 'server-only' // mocked below
import { describe, it, expect, vi } from 'vitest'

vi.mock('server-only', () => ({}))

import { buildStocksCommentary, type StocksPageAggregates } from '@/lib/commentary/stocks'

const base: StocksPageAggregates = {
  total:                500,
  investable_count:     40,
  leader_count:         30,
  strong_count:         60,
  pct_leader_strong:    0.18,
  median_rs_pctile:     0.55,
  accel_count:          20,
  regime_state:         'Constructive',
  deployment_multiplier: 0.7,
}

describe('buildStocksCommentary', () => {
  it('returns a narrative string', () => {
    const result = buildStocksCommentary(base)
    expect(typeof result.narrative).toBe('string')
    expect(result.narrative.length).toBeGreaterThan(20)
  })

  it('returns context cards array', () => {
    const result = buildStocksCommentary(base)
    expect(Array.isArray(result.contextCards)).toBe(true)
    expect(result.contextCards.length).toBeGreaterThan(0)
  })

  it('mentions deployment % from regime in narrative', () => {
    const result = buildStocksCommentary(base)
    expect(result.narrative).toMatch(/70%|0.7|Constructive/)
  })

  it('flags thin leadership when pct_leader_strong < 0.10', () => {
    const thin = { ...base, pct_leader_strong: 0.08, leader_count: 5, strong_count: 10 }
    const result = buildStocksCommentary(thin)
    expect(result.narrative.toLowerCase()).toMatch(/thin|narrow|few|limited/)
  })

  it('calls out strong breadth when pct_leader_strong > 0.30', () => {
    const broad = { ...base, pct_leader_strong: 0.35, leader_count: 100, strong_count: 75 }
    const result = buildStocksCommentary(broad)
    expect(result.narrative.toLowerCase()).toMatch(/broad|strong breadth|wide/)
  })

  it('references Risk-Off regime when present', () => {
    const riskOff = { ...base, regime_state: 'Risk-Off', deployment_multiplier: 0 }
    const result = buildStocksCommentary(riskOff)
    expect(result.narrative.toLowerCase()).toMatch(/risk-off|no new|0%/)
  })

  it('includes investable_count in context cards', () => {
    const result = buildStocksCommentary(base)
    const investableCard = result.contextCards.find(c => c.label.toLowerCase().includes('investable'))
    expect(investableCard).toBeDefined()
    expect(investableCard?.value).toContain('40')
  })
})
```

- [ ] **Step 9.2: Run tests to confirm they fail**

```bash
cd frontend && npx vitest run src/lib/commentary/__tests__/stocks.test.ts
```

Expected: FAIL — module not found

- [ ] **Step 9.3: Implement buildStocksCommentary**

```typescript
// frontend/src/lib/commentary/stocks.ts
export type StocksPageAggregates = {
  total: number
  investable_count: number
  leader_count: number
  strong_count: number
  pct_leader_strong: number      // fraction 0–1
  median_rs_pctile: number       // fraction 0–1
  accel_count: number
  regime_state: string
  deployment_multiplier: number  // 0–1
}

export type CommentaryResult = {
  narrative: string
  contextCards: { label: string; value: string; delta?: string; deltaPositive?: boolean }[]
}

type Condition = {
  test: (a: StocksPageAggregates) => boolean
  generate: (a: StocksPageAggregates) => string
}

const CONDITIONS: Condition[] = [
  {
    test: a => a.regime_state === 'Risk-Off',
    generate: a =>
      `Market is Risk-Off — deployment at 0%. No new positions regardless of stock signals. ${a.investable_count} stocks remain investable by RS criteria; they can be added when regime improves.`,
  },
  {
    test: a => a.pct_leader_strong < 0.10,
    generate: a =>
      `Leadership is thin: only ${((a.pct_leader_strong) * 100).toFixed(0)}% of stocks (${a.leader_count + a.strong_count}) are Leader or Strong under ${a.regime_state} (${Math.round(a.deployment_multiplier * 100)}% deployment). Narrow markets often precede corrections — prefer high-conviction names from the investable list.`,
  },
  {
    test: a => a.pct_leader_strong >= 0.30,
    generate: a =>
      `Broad strength: ${((a.pct_leader_strong) * 100).toFixed(0)}% of the universe is Leader or Strong — a wide breadth reading. Under ${a.regime_state} at ${Math.round(a.deployment_multiplier * 100)}% deployment, ${a.investable_count} stocks qualify for new positions.`,
  },
  {
    test: () => true,
    generate: a =>
      `${a.leader_count + a.strong_count} stocks are Leader or Strong (${((a.pct_leader_strong) * 100).toFixed(0)}%) with a median RS percentile of ${(a.median_rs_pctile * 100).toFixed(0)}th. Under ${a.regime_state} (${Math.round(a.deployment_multiplier * 100)}% deployment), ${a.investable_count} meet all entry criteria.`,
  },
]

export function buildStocksCommentary(aggregates: StocksPageAggregates): CommentaryResult {
  const condition = CONDITIONS.find(c => c.test(aggregates))!
  const narrative = condition.generate(aggregates)

  const contextCards = [
    {
      label: 'Investable',
      value: `${aggregates.investable_count} stocks`,
    },
    {
      label: 'Leader/Strong',
      value: `${aggregates.leader_count + aggregates.strong_count}`,
    },
    {
      label: 'Deployment',
      value: `${Math.round(aggregates.deployment_multiplier * 100)}%`,
      deltaPositive: aggregates.deployment_multiplier >= 0.7,
    },
    {
      label: 'Accelerating',
      value: `${aggregates.accel_count}`,
    },
  ]

  return { narrative, contextCards }
}
```

- [ ] **Step 9.4: Run tests to confirm they pass**

```bash
cd frontend && npx vitest run src/lib/commentary/__tests__/stocks.test.ts
```

Expected: PASS — 7 tests

- [ ] **Step 9.5: Commit**

```bash
git add frontend/src/lib/commentary/stocks.ts \
        frontend/src/lib/commentary/__tests__/stocks.test.ts
git commit -m "feat(sprint1): add buildStocksCommentary with full condition test coverage"
```

---

## Task 10: Migration 026 — state_since_date column

**Why:** Sprint 2's days_in_state column in the stocks screener requires `state_since_date DATE` on `atlas_stock_states_daily`. The nightly classification job writes this column alongside the RS state. `getAllStocks()` then reads `CURRENT_DATE - s.state_since_date` to compute days_in_state at query time — no CTE over 500K+ rows. Build the migration in Sprint 1 so EC2 can run it before Sprint 2 begins.

**Files:**
- Create: `migrations/versions/026_add_state_since_date.py`

- [ ] **Step 10.1: Verify migration numbering**

```bash
ls migrations/versions/ | grep "^02[0-9]" | sort | tail -5
```

Expected: last file is `025_strategy_configs_audit.py`. If a `026_*.py` already exists, read its contents and increment to 027.

- [ ] **Step 10.2: Create the Alembic migration**

```python
# migrations/versions/026_add_state_since_date.py
"""add state_since_date to atlas_stock_states_daily

Revision ID: 026
Revises: 025
Create Date: 2026-05-10
"""
from alembic import op
import sqlalchemy as sa

revision = '026'
down_revision = '025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add the column nullable — pre-backfill rows will have NULL
    # The nightly pipeline writes this on each state classification run
    op.execute("""
        ALTER TABLE atlas.atlas_stock_states_daily
        ADD COLUMN IF NOT EXISTS state_since_date DATE;
    """)

    # Backfill: for each instrument, find the earliest date in the current
    # contiguous run of the same rs_state by working backwards from latest.
    # This is a one-time operation on ~500K rows — acceptable at migration time.
    op.execute("""
        WITH ranked AS (
            SELECT
                instrument_id,
                date,
                rs_state,
                LAG(rs_state) OVER (
                    PARTITION BY instrument_id ORDER BY date
                ) AS prev_rs_state
            FROM atlas.atlas_stock_states_daily
        ),
        state_starts AS (
            SELECT instrument_id, date AS start_date, rs_state
            FROM ranked
            WHERE prev_rs_state IS DISTINCT FROM rs_state
        ),
        latest_state AS (
            SELECT DISTINCT ON (s.instrument_id)
                s.instrument_id,
                ss.start_date
            FROM atlas.atlas_stock_states_daily s
            JOIN state_starts ss
                ON ss.instrument_id = s.instrument_id
                AND ss.rs_state = s.rs_state
                AND ss.start_date <= s.date
            ORDER BY s.instrument_id, ss.start_date DESC
        )
        UPDATE atlas.atlas_stock_states_daily dst
        SET state_since_date = ls.start_date
        FROM latest_state ls
        WHERE dst.instrument_id = ls.instrument_id
          AND dst.state_since_date IS NULL;
    """)

    # Index to support: CURRENT_DATE - state_since_date per instrument
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_states_since_date
        ON atlas.atlas_stock_states_daily (instrument_id, state_since_date);
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS atlas.idx_stock_states_since_date;
        ALTER TABLE atlas.atlas_stock_states_daily
        DROP COLUMN IF EXISTS state_since_date;
    """)
```

- [ ] **Step 10.3: Validate the migration file is syntactically correct**

```bash
cd /path/to/atlas-os && python -c "import ast; ast.parse(open('migrations/versions/026_add_state_since_date.py').read()); print('syntax OK')"
```

Expected: `syntax OK`

- [ ] **Step 10.4: Run migration in a dry-run / offline mode to verify Alembic can read it**

```bash
cd /path/to/atlas-os && alembic show 026 2>&1 | head -20
```

Expected: shows migration metadata without error. If the DB connection fails in this environment, that's OK — the syntax check above is sufficient for Sprint 1.

- [ ] **Step 10.5: Commit**

```bash
git add migrations/versions/026_add_state_since_date.py
git commit -m "feat(sprint1): migration 026 — add state_since_date to atlas_stock_states_daily"
```

**Note for EC2 deployment:** Run `alembic upgrade 026` on the compute EC2 before Sprint 2 begins. The backfill SQL in upgrade() handles existing rows. New nightly runs will write `state_since_date` on each state record.

---

## Task 11: URL param validation scaffold

**Why:** The spec (Section 15, Accessibility, and Sprint 1 task list) requires URL allowlist validation for `?period` and `?benchmark` in every Page server component. The pattern is identical across all pages — validate in the Page RSC before passing values to child components. Build a reusable validator in Sprint 1 that Sprint 2+ pages can call.

**Files:**
- Create: `frontend/src/lib/url-params.ts`
- Create: `frontend/src/lib/__tests__/url-params.test.ts`

- [ ] **Step 11.1: Write failing tests**

```typescript
// frontend/src/lib/__tests__/url-params.test.ts
import { describe, it, expect } from 'vitest'
import { validatePeriod, validateBenchmark } from '@/lib/url-params'

describe('validatePeriod', () => {
  it('returns the period when it is in the allowlist', () => {
    expect(validatePeriod('3M')).toBe('3M')
    expect(validatePeriod('1Y')).toBe('1Y')
  })

  it('returns the default when period is not in the allowlist', () => {
    expect(validatePeriod('99M')).toBe('3M')
    expect(validatePeriod(undefined)).toBe('3M')
    expect(validatePeriod('')).toBe('3M')
  })
})

describe('validateBenchmark', () => {
  it('returns the benchmark when it is in the allowlist', () => {
    expect(validateBenchmark('NIFTY50')).toBe('NIFTY50')
    expect(validateBenchmark('GOLD')).toBe('GOLD')
  })

  it('returns the default when benchmark is not in the allowlist', () => {
    expect(validateBenchmark('INVALID')).toBe('NIFTY500')
    expect(validateBenchmark(undefined)).toBe('NIFTY500')
  })
})
```

- [ ] **Step 11.2: Run test to confirm it fails**

```bash
cd frontend && npx vitest run src/lib/__tests__/url-params.test.ts
```

Expected: FAIL — module not found

- [ ] **Step 11.3: Implement url-params.ts**

```typescript
// frontend/src/lib/url-params.ts

export const VALID_PERIODS = ['1M', '3M', '6M', '1Y'] as const
export type Period = typeof VALID_PERIODS[number]
export const DEFAULT_PERIOD: Period = '3M'

export const VALID_BENCHMARKS = [
  'NIFTY50', 'NIFTY500', 'NIFTY100', 'MIDCAP150', 'SMALLCAP250', 'GOLD', 'MSCIWORLD', 'SP500',
] as const
export type Benchmark = typeof VALID_BENCHMARKS[number]
export const DEFAULT_BENCHMARK: Benchmark = 'NIFTY500'

export function validatePeriod(raw: string | undefined | null): Period {
  if (raw && (VALID_PERIODS as readonly string[]).includes(raw)) return raw as Period
  return DEFAULT_PERIOD
}

export function validateBenchmark(raw: string | undefined | null): Benchmark {
  if (raw && (VALID_BENCHMARKS as readonly string[]).includes(raw)) return raw as Benchmark
  return DEFAULT_BENCHMARK
}
```

- [ ] **Step 11.4: Run tests to confirm they pass**

```bash
cd frontend && npx vitest run src/lib/__tests__/url-params.test.ts
```

Expected: PASS — 6 tests

- [ ] **Step 11.5: Commit**

```bash
git add frontend/src/lib/url-params.ts \
        frontend/src/lib/__tests__/url-params.test.ts
git commit -m "feat(sprint1): add url-params validator (period, benchmark allowlists)"
```

---

## Task 12: Full test run and quality gate

**Why:** Before calling Sprint 1 done, run the full test suite to catch any regressions the new modules might have introduced. Then run tsc + eslint to ensure the type system and linter are clean.

- [ ] **Step 12.1: Run all tests**

```bash
cd frontend && npx vitest run 2>&1 | tail -20
```

Expected: all tests pass. If any test fails, fix it before proceeding. Do NOT skip or comment out failing tests.

- [ ] **Step 12.2: Run TypeScript type check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -50
```

Expected: no errors. If errors appear in files that were not modified in Sprint 1, investigate before claiming done.

- [ ] **Step 12.3: Run ESLint on new files**

```bash
cd frontend && npx eslint \
  src/lib/state-segment-utils.ts \
  src/lib/chart-colors.ts \
  src/lib/screener-utils.ts \
  src/lib/url-params.ts \
  src/lib/commentary/stocks.ts \
  src/components/ui/StateValuePair.tsx \
  src/components/ui/MetricTooltip.tsx \
  src/components/ui/CommentaryBlock.tsx \
  --max-warnings 0
```

Expected: no errors or warnings.

- [ ] **Step 12.4: Commit Sprint 1 complete marker**

```bash
git commit --allow-empty -m "chore(sprint1): Sprint 1 design system foundation complete

Deliverables:
- lib/state-segment-utils.ts (extracted buildSegments)
- lib/chart-colors.ts (canonical CHART_COLORS + bubbleColor helpers)
- lib/screener-utils.ts (stateRank, matchesSearch, buildSortKey)
- lib/url-params.ts (validatePeriod, validateBenchmark)
- lib/commentary/stocks.ts (buildStocksCommentary + 7-condition coverage)
- ui/StateValuePair.tsx (chip + scalar layout)
- ui/MetricTooltip.tsx (METRIC_DEFINITIONS lookup)
- ui/CommentaryBlock.tsx (narrative + context cards)
- Bubble chart color fix (stocks/StockBubbleChart.tsx)
- RSPctileBar/PosSizeBar color fix (stock-formatters.tsx)
- Migration 026 (state_since_date DATE on atlas_stock_states_daily)
- Full Vitest + tsc + ESLint passing"
```

---

## Spec Coverage Self-Check

| Spec Requirement | Covered By |
|-----------------|-----------|
| `lib/state-segment-utils.ts` extraction | Task 1 |
| Canonical CHART_COLORS token map | Task 2 |
| Bubble chart color fix (stocks page, Recharts) | Task 3 |
| RSPctileBar/PosSizeBar correct hex | Task 4 |
| StateValuePair (chip + scalar) | Task 5 |
| MetricTooltip (METRIC_DEFINITIONS lookup) | Task 6 |
| CommentaryBlock (narrative + context cards) | Task 7 |
| screener-utils shared filter/sort | Task 8 |
| buildCommentary stocks — full condition tests | Task 9 |
| Migration 026 — state_since_date | Task 10 |
| URL param allowlist validation | Task 11 |
| Full quality gate (vitest + tsc + eslint) | Task 12 |
| Portfolio monitoring bug fix | **NOT in Sprint 1** — the equity curve charts are intentional empty-state stubs (v0 placeholder) and will be wired in Sprint 6 with paper-trader data. No bug to fix. |

**Not in Sprint 1** (gates later sprints): sectors bubble chart D3 color fix, sectors StockBubbleChart uses different state values (Overweight_RS/Underweight_RS) and a separate color scheme — fix in Sprint 3 alongside the RRG work.

---

## Execution Notes for Agentic Workers

1. **Branch first.** `git checkout -b feat/sprint-1-design-system` before touching any files.
2. **One task at a time.** Mark each task in_progress, complete it fully, mark done. Do not batch.
3. **Never skip the "run failing test" step.** A test that never fails might have the wrong assertion — you need to see it fail before it means anything when it passes.
4. **tsc is the type-checker.** After any new TypeScript file, run `npx tsc --noEmit` to catch type errors early.
5. **Do not modify StockScreener.tsx in Sprint 1.** The screener-utils extraction creates the utilities; wiring them into the actual screener is Sprint 2 work. Sprint 1 must not break any existing page.
6. **Migration 026 is backend-only.** Do not add the days_in_state column to the frontend screener query (`getAllStocks()`) in Sprint 1 — that is Sprint 2 Task 1.
