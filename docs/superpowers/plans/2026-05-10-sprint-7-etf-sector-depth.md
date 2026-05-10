# Sprint 7: ETF Depth + Sector ETF/Funds Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve ETF screener focus (Broad+Sectoral only), fix intelligence panel RS count inconsistency, add gate tooltips + term explanations to deep dive, add timeframe selector and more metric charts to the ETF deep dive, and add ETF + Funds tabs to the sector deep dive page.

**Architecture:** All changes are in the Next.js frontend. Query changes extend existing postgres.js tagged-template functions. Component changes follow the established RSC + client-component split. Sector funds attribution is computed by a new SQL CTE that joins MF holdings → stocks → sectors, ranking by portfolio weight.

**Tech Stack:** Next.js 14 App Router, postgres.js, TypeScript, Recharts via IndicatorChart, Tailwind CSS.

---

## File Structure

### Modified files
- `frontend/src/lib/queries/etfs.ts` — extend `ETFMetricHistoryRow` type + SQL; add `getAllETFs` WHERE filter; add `getLinkedETFsForSector`
- `frontend/src/app/etfs/page.tsx` — update leaderCount/investableCount labels post-filter
- `frontend/src/components/etfs/ETFScreener.tsx` — remove Thematic chip, add gate letter tooltips
- `frontend/src/components/etfs/ETFIntelligencePanel.tsx` — add ILLIQUID/INSUFFICIENT_HISTORY to RS_STATES
- `frontend/src/components/etfs/ETFGatesPanel.tsx` — add threshold info tooltip to each gate
- `frontend/src/components/etfs/ETFSnapshotTiles.tsx` — add Weinstein/Extension tooltip subtitles
- `frontend/src/components/etfs/ETFDeepDiveHeader.tsx` — add labeled attributes (Tracks:, Sector:)
- `frontend/src/components/etfs/ETFOverviewTab.tsx` — timeframe selector + 3 additional metric charts
- `frontend/src/app/etfs/[ticker]/page.tsx` — accept `range` searchParam, pass to metric history fetch
- `frontend/src/components/sectors/SectorDeepDiveTabs.tsx` — add ETF + Funds tabs
- `frontend/src/app/sectors/[name]/page.tsx` — fetch linked ETF + sector funds; expand tab handling

### New files
- `frontend/src/lib/queries/sector-funds.ts` — `SectorFundRow` type + `getSectorFunds(sectorName)` SQL
- `frontend/src/components/sectors/SectorETFTab.tsx` — ETF card for sector page
- `frontend/src/components/sectors/SectorFundsTab.tsx` — fund ranking table for sector page

---

## Task 1: Extend ETF metric history type + SQL

**Files:**
- Modify: `frontend/src/lib/queries/etfs.ts:48-53` (ETFMetricHistoryRow type)
- Modify: `frontend/src/lib/queries/etfs.ts:178-196` (getETFMetricHistory SQL)

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/lib/queries/__tests__/etfs-metric-history.test.ts
import { describe, it, expect } from 'vitest'

describe('ETFMetricHistoryRow shape', () => {
  it('type has all required fields', () => {
    // Compile-time check — if type is wrong, tsc will fail
    const row: import('../etfs').ETFMetricHistoryRow = {
      date: new Date(),
      rs_pctile_3m: '0.75',
      ret_1m: '0.04',
      ret_3m: '0.12',
      ret_6m: '0.22',
      ema_10_ratio: '1.02',
      ema_20_ratio: '1.01',
      extension_pct: '0.05',
      vol_63: '0.18',
      drawdown: '-0.08',
    }
    expect(row.date).toBeDefined()
    expect(row.ret_6m).toBeDefined()
    expect(row.extension_pct).toBeDefined()
  })
})
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd frontend && npx vitest run src/lib/queries/__tests__/etfs-metric-history.test.ts
```
Expected: FAIL — type mismatch (fields don't exist yet)

- [ ] **Step 3: Update `ETFMetricHistoryRow` type**

In `frontend/src/lib/queries/etfs.ts`, replace lines 48–53:

```typescript
export type ETFMetricHistoryRow = {
  date: Date
  rs_pctile_3m: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ema_10_ratio: string | null
  ema_20_ratio: string | null
  extension_pct: string | null
  vol_63: string | null
  drawdown: string | null
}
```

- [ ] **Step 4: Update `getETFMetricHistory` SQL**

In `frontend/src/lib/queries/etfs.ts`, replace the `getETFMetricHistory` function body (lines 185–196):

```typescript
export async function getETFMetricHistory(
  ticker: string,
  days = 180,
): Promise<ETFMetricHistoryRow[]> {
  if (!Number.isInteger(days) || days < 1 || days > 3650) {
    throw new Error(`days must be an integer between 1 and 3650, got: ${days}`)
  }
  return sql<ETFMetricHistoryRow[]>`
    SELECT
      date,
      rs_pctile_3m::text  AS rs_pctile_3m,
      ret_1m::text        AS ret_1m,
      ret_3m::text        AS ret_3m,
      ret_6m::text        AS ret_6m,
      ema_10_ratio::text  AS ema_10_ratio,
      ema_20_ratio::text  AS ema_20_ratio,
      extension_pct::text AS extension_pct,
      realized_vol_63::text AS vol_63,
      drawdown_ratio_252::text AS drawdown
    FROM atlas.atlas_etf_metrics_daily
    WHERE ticker = ${ticker}
      AND date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY date ASC
  `
}
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd frontend && npx vitest run src/lib/queries/__tests__/etfs-metric-history.test.ts
```
Expected: PASS

- [ ] **Step 6: Run full type check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/queries/etfs.ts frontend/src/lib/queries/__tests__/etfs-metric-history.test.ts
git commit -m "feat(etf): extend ETFMetricHistoryRow with 6M/extension/vol/drawdown/EMA20"
```

---

## Task 2: Filter getAllETFs to Broad+Sectoral + fix intelligence panel RS counts

**Files:**
- Modify: `frontend/src/lib/queries/etfs.ts` — getAllETFs WHERE clause
- Modify: `frontend/src/components/etfs/ETFScreener.tsx` — remove Thematic chip
- Modify: `frontend/src/components/etfs/ETFIntelligencePanel.tsx` — add ILLIQUID/INSUFFICIENT_HISTORY

- [ ] **Step 1: Write test for intelligence panel RS count**

```typescript
// frontend/src/components/etfs/__tests__/ETFIntelligencePanel.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ETFIntelligencePanel } from '../ETFIntelligencePanel'
import type { ETFRow } from '@/lib/queries/etfs'

function makeETF(overrides: Partial<ETFRow>): ETFRow {
  return {
    ticker: 'TEST',
    etf_name: 'Test ETF',
    theme: 'Broad',
    linked_sector: null,
    linked_index: null,
    inception_date: null,
    asset_class: null,
    fund_house: null,
    data_as_of: null,
    ret_1m: null, ret_3m: null, ret_6m: null,
    rs_pctile_3m: null, ema_10_ratio: null, extension_pct: null,
    ret_1w: null, vol_63: null, drawdown: null, days_in_state: null,
    rs_state: null, momentum_state: null, risk_state: null,
    weinstein_gate_pass: null, history_gate_pass: null, liquidity_gate_pass: null,
    is_investable: null, strength_gate: null, direction_gate: null,
    risk_gate: null, sector_gate: null, market_gate: null,
    position_size_pct: null,
    exit_market_riskoff: null, exit_sector_avoid: null, exit_rs_deteriorate: null,
    exit_momentum_collapse: null, exit_stop_loss: null,
    ...overrides,
  }
}

describe('ETFIntelligencePanel', () => {
  it('counts ILLIQUID ETFs in RS distribution bars', () => {
    const etfs = [
      makeETF({ rs_state: 'Leader' }),
      makeETF({ rs_state: 'ILLIQUID' }),
      makeETF({ rs_state: 'INSUFFICIENT_HISTORY' }),
    ]
    render(<ETFIntelligencePanel etfs={etfs} />)
    // ILLIQUID should appear in the distribution, not be silently dropped
    expect(screen.getByText('ILLIQUID')).toBeInTheDocument()
    expect(screen.getByText('Insuf. Hist')).toBeInTheDocument()
  })

  it('shows Leader count = 1 when one Leader ETF exists', () => {
    const etfs = [makeETF({ rs_state: 'Leader' }), makeETF({ rs_state: 'Average' })]
    render(<ETFIntelligencePanel etfs={etfs} />)
    // Find the Leader row — count should be 1
    const leaderRow = screen.getByText('Leader').closest('div')
    expect(leaderRow?.textContent).toContain('1')
  })
})
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd frontend && npx vitest run src/components/etfs/__tests__/ETFIntelligencePanel.test.tsx
```
Expected: FAIL (ILLIQUID not in RS_STATES list)

- [ ] **Step 3: Add Thematic filter to getAllETFs SQL**

In `frontend/src/lib/queries/etfs.ts` in `getAllETFs()`, change the WHERE clause from:
```sql
    WHERE u.effective_to IS NULL
```
to:
```sql
    WHERE u.effective_to IS NULL
      AND u.theme IN ('Broad', 'Sectoral')
```

Apply the same change to `getETFByTicker()` — leave it unchanged (deep dive must still work for any ticker, so keep the existing WHERE `u.ticker = ${ticker}`).

- [ ] **Step 4: Update ETFIntelligencePanel RS_STATES to include ILLIQUID**

In `frontend/src/components/etfs/ETFIntelligencePanel.tsx`, replace:

```typescript
const RS_STATES  = ['Leader', 'Strong', 'Consolidating', 'Emerging', 'Average', 'Weak', 'Laggard']
```

with:

```typescript
const RS_STATES: { key: string; label: string }[] = [
  { key: 'Leader',               label: 'Leader' },
  { key: 'Strong',               label: 'Strong' },
  { key: 'Consolidating',        label: 'Consolidating' },
  { key: 'Emerging',             label: 'Emerging' },
  { key: 'Average',              label: 'Average' },
  { key: 'Weak',                 label: 'Weak' },
  { key: 'Laggard',              label: 'Laggard' },
  { key: 'ILLIQUID',             label: 'ILLIQUID' },
  { key: 'INSUFFICIENT_HISTORY', label: 'Insuf. Hist' },
]
```

Update the `rsCounts` initialization and the loop:

```typescript
const rsCounts = Object.fromEntries(RS_STATES.map(s => [s.key, 0])) as Record<string, number>
for (const etf of etfs) {
  if (etf.rs_state && rsCounts[etf.rs_state] !== undefined) rsCounts[etf.rs_state]++
}
```

Update `leaderStrong`:
```typescript
const leaderStrong = (rsCounts['Leader'] ?? 0) + (rsCounts['Strong'] ?? 0)
```

Update the render loop (replace the `.map(s => ...)` call):
```typescript
{RS_STATES.map(s => (
  <DistBar key={s.key} label={s.label} count={rsCounts[s.key] ?? 0} total={n} color={rsStateColor(s.key)} />
))}
```

- [ ] **Step 5: Remove Thematic chip from ETFScreener**

In `frontend/src/components/etfs/ETFScreener.tsx`, replace `CHIPS`:

```typescript
const CHIPS: { key: FilterChip; label: string }[] = [
  { key: 'all',        label: 'All' },
  { key: 'broad',      label: 'Broad' },
  { key: 'sectoral',   label: 'Sectoral' },
  { key: 'investable', label: 'Investable' },
]
```

Also remove `'thematic'` from the `FilterChip` type:
```typescript
type FilterChip = 'all' | 'broad' | 'sectoral' | 'investable'
```

Remove the thematic filter branch from the `filtered` useMemo (find and delete the `case 'thematic': ...` line).

- [ ] **Step 6: Run test to verify it passes**

```bash
cd frontend && npx vitest run src/components/etfs/__tests__/ETFIntelligencePanel.test.tsx
```
Expected: PASS

- [ ] **Step 7: Run full test suite**

```bash
cd frontend && npx vitest run
```
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/queries/etfs.ts \
        frontend/src/components/etfs/ETFIntelligencePanel.tsx \
        frontend/src/components/etfs/ETFScreener.tsx \
        frontend/src/components/etfs/__tests__/ETFIntelligencePanel.test.tsx
git commit -m "feat(etf): filter screener to Broad+Sectoral; fix intelligence panel ILLIQUID coverage"
```

---

## Task 3: Gate letter tooltips in ETF screener GateBadge

**Files:**
- Modify: `frontend/src/components/etfs/ETFScreener.tsx` — GateBadge tooltips

- [ ] **Step 1: Write test**

```typescript
// frontend/src/components/etfs/__tests__/ETFScreener.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ETFScreener } from '../ETFScreener'
import type { ETFRow } from '@/lib/queries/etfs'

const ETF: ETFRow = {
  ticker: 'NIFTYBEES', etf_name: 'Nippon India ETF Nifty BeES', theme: 'Broad',
  linked_sector: null, linked_index: 'NIFTY50', inception_date: null,
  asset_class: 'Equity', fund_house: 'Nippon', data_as_of: '2026-05-09',
  ret_1m: '0.03', ret_3m: '0.11', ret_6m: '0.19', rs_pctile_3m: '0.72',
  ema_10_ratio: '1.01', extension_pct: '0.04', ret_1w: '0.005',
  vol_63: '0.14', drawdown: '-0.05', days_in_state: 45,
  rs_state: 'Strong', momentum_state: 'Improving', risk_state: 'Normal',
  weinstein_gate_pass: true, history_gate_pass: true, liquidity_gate_pass: true,
  is_investable: true, strength_gate: true, direction_gate: true,
  risk_gate: true, sector_gate: true, market_gate: true,
  position_size_pct: '0.08',
  exit_market_riskoff: false, exit_sector_avoid: false, exit_rs_deteriorate: false,
  exit_momentum_collapse: false, exit_stop_loss: false,
}

describe('ETFScreener GateBadge tooltips', () => {
  it('renders gate badges with title attributes', () => {
    render(<ETFScreener etfs={[ETF]} />)
    const hBadge = screen.getByTitle(/History gate/i)
    expect(hBadge).toBeInTheDocument()
    const wBadge = screen.getByTitle(/Weinstein/i)
    expect(wBadge).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd frontend && npx vitest run src/components/etfs/__tests__/ETFScreener.test.tsx
```
Expected: FAIL — no title attributes on gate badges

- [ ] **Step 3: Update GateBadge in ETFScreener.tsx**

In `frontend/src/components/etfs/ETFScreener.tsx`, replace the `GateBadge` function:

```typescript
const GATE_DEFS: { label: string; title: string; key: keyof ETFRow }[] = [
  { label: 'H',  title: 'History gate — ETF has ≥52 weeks of price history',                   key: 'history_gate_pass' },
  { label: 'L',  title: 'Liquidity gate — average daily volume above minimum threshold',        key: 'liquidity_gate_pass' },
  { label: 'W',  title: 'Weinstein gate — price above 30-week (150-day) moving average',        key: 'weinstein_gate_pass' },
  { label: 'S',  title: 'Strength gate — RS state is Leader or Strong (top 30th percentile)',  key: 'strength_gate' },
  { label: 'D',  title: 'Direction gate — momentum is Accelerating or Improving',               key: 'direction_gate' },
  { label: 'Ri', title: 'Risk gate — extension <40% above 200-day MA and volatility normal',   key: 'risk_gate' },
]

function GateBadge({ row }: { row: ETFRow }) {
  const passing = GATE_DEFS.filter(g => row[g.key] === true).length
  return (
    <div className="flex items-center gap-0.5">
      <span className={`font-mono text-[10px] mr-0.5 ${passing >= 5 ? 'text-signal-pos' : passing >= 4 ? 'text-signal-warn' : 'text-ink-tertiary'}`}>
        {passing}/6
      </span>
      {GATE_DEFS.map(g => {
        const pass = row[g.key]
        return (
          <span
            key={g.label}
            title={g.title}
            className={`inline-block font-mono text-[9px] font-semibold px-0.5 rounded cursor-help ${
              pass === true  ? 'text-signal-pos bg-signal-pos/10' :
              pass === false ? 'text-signal-neg/60 bg-signal-neg/5' :
                               'text-ink-tertiary/40'
            }`}
          >
            {g.label}
          </span>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend && npx vitest run src/components/etfs/__tests__/ETFScreener.test.tsx
```
Expected: PASS

- [ ] **Step 5: Run full test suite + type check**

```bash
cd frontend && npx vitest run && npx tsc --noEmit
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/etfs/ETFScreener.tsx \
        frontend/src/components/etfs/__tests__/ETFScreener.test.tsx
git commit -m "feat(etf): add title tooltips to gate badges in screener"
```

---

## Task 4: Enhanced ETFGatesPanel — threshold info tooltips

**Files:**
- Modify: `frontend/src/components/etfs/ETFGatesPanel.tsx`

- [ ] **Step 1: Write test**

```typescript
// frontend/src/components/etfs/__tests__/ETFGatesPanel.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ETFGatesPanel } from '../ETFGatesPanel'
import type { ETFRow } from '@/lib/queries/etfs'

const ETF_BASE: ETFRow = {
  ticker: 'TEST', etf_name: 'Test', theme: 'Broad',
  linked_sector: null, linked_index: null, inception_date: null,
  asset_class: null, fund_house: null, data_as_of: null,
  ret_1m: null, ret_3m: null, ret_6m: null, rs_pctile_3m: null,
  ema_10_ratio: null, extension_pct: null, ret_1w: null,
  vol_63: null, drawdown: null, days_in_state: null,
  rs_state: 'Leader', momentum_state: 'Accelerating', risk_state: 'Low',
  weinstein_gate_pass: true, history_gate_pass: true, liquidity_gate_pass: true,
  is_investable: true, strength_gate: true, direction_gate: true,
  risk_gate: true, sector_gate: true, market_gate: true,
  position_size_pct: '0.08',
  exit_market_riskoff: false, exit_sector_avoid: false, exit_rs_deteriorate: false,
  exit_momentum_collapse: false, exit_stop_loss: false,
}

describe('ETFGatesPanel', () => {
  it('renders threshold info text for Strength gate', () => {
    render(<ETFGatesPanel etf={ETF_BASE} />)
    // Should contain threshold explanation — RS percentile mention
    expect(screen.getByText(/top 30th percentile/i)).toBeInTheDocument()
  })

  it('renders threshold info text for Weinstein gate', () => {
    render(<ETFGatesPanel etf={ETF_BASE} />)
    expect(screen.getByText(/150-day/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd frontend && npx vitest run src/components/etfs/__tests__/ETFGatesPanel.test.tsx
```
Expected: FAIL — those strings don't exist yet

- [ ] **Step 3: Replace GATES array in ETFGatesPanel.tsx with threshold info**

In `frontend/src/components/etfs/ETFGatesPanel.tsx`, replace the entire file:

```typescript
import { CheckCircle2, XCircle } from 'lucide-react'
import type { ETFRow } from '@/lib/queries/etfs'

type Gate = {
  key: keyof Pick<ETFRow, 'strength_gate' | 'direction_gate' | 'risk_gate' | 'sector_gate' | 'market_gate'>
  label: string
  description: string
  threshold: string
}

const GATES: Gate[] = [
  {
    key: 'strength_gate',
    label: 'Strength',
    description: 'RS state is Leader or Strong — ETF outperforming peers.',
    threshold: 'Pass when RS 3M percentile ≥ 70th (top 30th percentile of universe). Leader = ≥85th.',
  },
  {
    key: 'direction_gate',
    label: 'Direction',
    description: 'Momentum is Accelerating or Improving — RS trend is rising.',
    threshold: 'Pass when EMA10/EMA20 ratio > 1.0 and improving week-over-week.',
  },
  {
    key: 'risk_gate',
    label: 'Risk',
    description: 'Risk state is Low or Normal — extension and volatility within bounds.',
    threshold: 'Fail when price is >40% above 200-day MA (over-extended) or realized vol > 1.5× benchmark.',
  },
  {
    key: 'sector_gate',
    label: 'Sector',
    description: 'Linked sector is not in Avoid state.',
    threshold: 'Fail when the sector this ETF tracks has sector_state = Avoid (bottom-up deterioration).',
  },
  {
    key: 'market_gate',
    label: 'Market',
    description: 'Market regime is not in Risk-off — broad market supports new positions.',
    threshold: 'Fail when NIFTY50 regime_state is Risk-Off or Dislocation. Blocks all new entries.',
  },
]

function GateRow({
  label,
  description,
  threshold,
  pass,
}: {
  label: string
  description: string
  threshold: string
  pass: boolean | null
}) {
  const Icon = pass ? CheckCircle2 : XCircle
  const iconClass = pass == null
    ? 'text-ink-tertiary'
    : pass ? 'text-signal-pos' : 'text-signal-neg'

  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-paper-rule last:border-0">
      <Icon className={`w-4 h-4 mt-0.5 flex-shrink-0 ${iconClass}`} />
      <div className="flex-1 min-w-0">
        <div className="font-sans text-xs font-semibold text-ink-primary">{label}</div>
        <div className="font-sans text-[11px] text-ink-tertiary leading-snug mt-0.5">{description}</div>
        <div className="font-sans text-[10px] text-ink-tertiary/70 leading-snug mt-1 italic">{threshold}</div>
      </div>
      <div className="ml-auto font-sans text-xs font-semibold shrink-0">
        <span className={pass == null ? 'text-ink-tertiary' : pass ? 'text-signal-pos' : 'text-signal-neg'}>
          {pass == null ? '—' : pass ? 'Pass' : 'Fail'}
        </span>
      </div>
    </div>
  )
}

export function ETFGatesPanel({ etf }: { etf: ETFRow }) {
  const passCount = GATES.filter(g => etf[g.key] === true).length

  return (
    <div className="border border-paper-rule rounded-sm bg-paper">
      <div className="px-4 py-3 border-b border-paper-rule flex items-center justify-between">
        <div>
          <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
            Decision Gates
          </div>
          <div className="font-sans text-[10px] text-ink-tertiary/60 mt-0.5">
            All 5 must pass for investable status
          </div>
        </div>
        <div className="font-sans text-xs text-ink-secondary">
          <span className={passCount >= 5 ? 'text-signal-pos font-semibold' : passCount >= 3 ? 'text-signal-warn font-semibold' : 'text-signal-neg font-semibold'}>
            {passCount}
          </span>
          <span className="text-ink-tertiary">/5 passing</span>
        </div>
      </div>
      <div className="px-4">
        {GATES.map(g => (
          <GateRow
            key={g.key}
            label={g.label}
            description={g.description}
            threshold={g.threshold}
            pass={etf[g.key] ?? null}
          />
        ))}
      </div>
      {etf.is_investable && (
        <div className="px-4 py-2.5 border-t border-paper-rule bg-signal-pos/5">
          <span className="font-sans text-xs font-semibold text-signal-pos">
            ● All gates passed — Investable
          </span>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend && npx vitest run src/components/etfs/__tests__/ETFGatesPanel.test.tsx
```
Expected: PASS

- [ ] **Step 5: Run full test suite**

```bash
cd frontend && npx vitest run && npx tsc --noEmit
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/etfs/ETFGatesPanel.tsx \
        frontend/src/components/etfs/__tests__/ETFGatesPanel.test.tsx
git commit -m "feat(etf): add threshold explanations to decision gates panel"
```

---

## Task 5: ETF deep dive — timeframe selector (3M / 6M / 1Y)

**Files:**
- Modify: `frontend/src/app/etfs/[ticker]/page.tsx` — read `range` searchParam
- Modify: `frontend/src/components/etfs/ETFOverviewTab.tsx` — add period selector UI + pass period down

- [ ] **Step 1: Update ETF deep dive page to read range param**

Replace `frontend/src/app/etfs/[ticker]/page.tsx` entirely:

```typescript
export const dynamic = 'force-dynamic'

import { notFound } from 'next/navigation'
import {
  getETFByTicker,
  getETFMetricHistory,
  getETFStateHistory,
  getETFHoldings,
} from '@/lib/queries/etfs'
import { rangeToDays, type TimeRange } from '@/lib/time-range'
import { ETFDeepDiveHeader } from '@/components/etfs/ETFDeepDiveHeader'
import { ETFSnapshotTiles } from '@/components/etfs/ETFSnapshotTiles'
import { ETFDeepDiveTabs } from '@/components/etfs/ETFDeepDiveTabs'

type Params = Promise<{ ticker: string }>
type SearchParams = Promise<{ tab?: string; range?: string }>

export default async function ETFPage({
  params,
  searchParams,
}: {
  params: Params
  searchParams: SearchParams
}) {
  const { ticker } = await params
  const { tab = 'overview', range = '6M' } = await searchParams
  const decoded = decodeURIComponent(ticker)

  const VALID_RANGES: TimeRange[] = ['1M', '3M', '6M', '1Y']
  const historyRange: TimeRange = VALID_RANGES.includes(range as TimeRange)
    ? (range as TimeRange)
    : '6M'
  const days = rangeToDays(historyRange)

  const [etf, metricHistory, stateHistory, holdings] = await Promise.all([
    getETFByTicker(decoded),
    getETFMetricHistory(decoded, days),
    getETFStateHistory(decoded, days),
    getETFHoldings(decoded, 20),
  ])

  if (!etf) notFound()

  return (
    <div className="max-w-[1400px] mx-auto">
      <ETFDeepDiveHeader etf={etf} />
      <ETFSnapshotTiles etf={etf} />
      <ETFDeepDiveTabs
        etf={etf}
        metricHistory={metricHistory}
        stateHistory={stateHistory}
        holdings={holdings}
        range={historyRange}
      />
    </div>
  )
}
```

- [ ] **Step 2: Check ETFDeepDiveTabs to see current props**

```bash
cat -n frontend/src/components/etfs/ETFDeepDiveTabs.tsx
```

- [ ] **Step 3: Update ETFDeepDiveTabs to accept and pass range**

In `frontend/src/components/etfs/ETFDeepDiveTabs.tsx`, add `range: TimeRange` to the props interface and pass it to `ETFOverviewTab`:

```typescript
'use client'
import { useState } from 'react'
import type { ETFRow, ETFMetricHistoryRow, ETFStateHistoryRow, ETFHoldingRow } from '@/lib/queries/etfs'
import type { TimeRange } from '@/lib/time-range'
import { ETFOverviewTab } from './ETFOverviewTab'
import { ETFStateHistoryTab } from './ETFStateHistoryTab'
import { ETFHoldingsTab } from './ETFHoldingsTab'

type Tab = 'overview' | 'history' | 'holdings'

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview',  label: 'Overview' },
  { id: 'history',   label: 'State History' },
  { id: 'holdings',  label: 'Holdings' },
]

export function ETFDeepDiveTabs({
  etf,
  metricHistory,
  stateHistory,
  holdings,
  range,
}: {
  etf: ETFRow
  metricHistory: ETFMetricHistoryRow[]
  stateHistory: ETFStateHistoryRow[]
  holdings: ETFHoldingRow[]
  range: TimeRange
}) {
  const [activeTab, setActiveTab] = useState<Tab>('overview')

  return (
    <div>
      <div className="border-b border-paper-rule px-6">
        <div className="flex gap-1">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`relative px-4 py-3 font-sans text-sm transition-colors ${
                activeTab === tab.id
                  ? 'text-ink-primary font-semibold'
                  : 'text-ink-tertiary hover:text-ink-secondary'
              }`}
            >
              {tab.label}
              {activeTab === tab.id && (
                <span className="absolute left-0 right-0 -bottom-px h-0.5 bg-teal" />
              )}
            </button>
          ))}
        </div>
      </div>

      {activeTab === 'overview' && (
        <ETFOverviewTab etf={etf} metricHistory={metricHistory} range={range} />
      )}
      {activeTab === 'history' && (
        <ETFStateHistoryTab stateHistory={stateHistory} />
      )}
      {activeTab === 'holdings' && (
        <ETFHoldingsTab holdings={holdings} />
      )}
    </div>
  )
}
```

- [ ] **Step 4: Add range prop to ETFOverviewTab**

In `frontend/src/components/etfs/ETFOverviewTab.tsx`, update the function signature from:
```typescript
export function ETFOverviewTab({
  etf,
  metricHistory,
}: {
  etf: ETFRow
  metricHistory: ETFMetricHistoryRow[]
})
```
to:
```typescript
import Link from 'next/link'
import { usePathname } from 'next/navigation'
// ... existing imports ...
import type { TimeRange } from '@/lib/time-range'

export function ETFOverviewTab({
  etf,
  metricHistory,
  range,
}: {
  etf: ETFRow
  metricHistory: ETFMetricHistoryRow[]
  range: TimeRange
})
```

Add the period selector UI at the top of the returned JSX (before the Weinstein/momentum grid). Since this needs to link to URL params and ETFOverviewTab is a server component, the range selector must be rendered as `<Link>` elements pointing to `?range=3M` etc. Add this block at the top of the returned div content:

```typescript
// Add after the opening <div className="px-6 py-6 space-y-6">:
{/* Range selector */}
<div className="flex items-center justify-between">
  <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
    Metric History
  </div>
  <div className="flex items-center gap-0.5 border border-paper-rule rounded-sm overflow-hidden">
    {(['3M', '6M', '1Y'] as TimeRange[]).map(r => (
      <Link
        key={r}
        href={`?range=${r}`}
        className={`px-2.5 py-0.5 font-sans text-[11px] font-medium transition-colors ${
          range === r
            ? 'bg-teal text-white'
            : 'text-ink-secondary hover:bg-paper-rule/30'
        }`}
      >
        {r}
      </Link>
    ))}
  </div>
</div>
```

- [ ] **Step 5: Run type check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

- [ ] **Step 6: Run full test suite**

```bash
cd frontend && npx vitest run
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/etfs/\[ticker\]/page.tsx \
        frontend/src/components/etfs/ETFDeepDiveTabs.tsx \
        frontend/src/components/etfs/ETFOverviewTab.tsx
git commit -m "feat(etf): add 3M/6M/1Y timeframe selector to deep dive overview"
```

---

## Task 6: More metric charts in ETFOverviewTab (Extension, Vol, Drawdown, 6M Return)

**Files:**
- Modify: `frontend/src/components/etfs/ETFOverviewTab.tsx` — 4 additional chart blocks

- [ ] **Step 1: Add 4 new chart data arrays in ETFOverviewTab**

In `frontend/src/components/etfs/ETFOverviewTab.tsx`, after the existing `emaData` array, add:

```typescript
  const ret1mData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.ret_1m != null ? parseFloat(r.ret_1m) : null,
  }))

  const ret6mData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.ret_6m != null ? parseFloat(r.ret_6m) : null,
  }))

  const extensionData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.extension_pct != null ? parseFloat(r.extension_pct) : null,
  }))

  const volData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.vol_63 != null ? parseFloat(r.vol_63) : null,
  }))

  const drawdownData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.drawdown != null ? parseFloat(r.drawdown) : null,
  }))
```

- [ ] **Step 2: Add 4 chart blocks after the EMA chart block**

After the closing `</div>` of the EMA 10 Ratio chart block (the last `<div className="grid...">`), add:

```typescript
            {/* 1M Return */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
              <IndicatorChart
                title="1-Month Return"
                description="Rolling 1-month price return. Short-term price momentum."
                currentValue={pctStr(latest?.ret_1m)}
                isBullish={latest?.ret_1m != null ? parseFloat(latest.ret_1m) >= 0 : null}
                data={ret1mData}
                refLine={0}
                refLabel="0"
                variant="area"
                yFormat="pct"
              />
              <Commentary title={`1M Return · ${pctStr(latest?.ret_1m)}`}>
                <p>{latest?.ret_1m != null
                  ? parseFloat(latest.ret_1m) >= 0.03
                    ? 'Strong 1-month performance. Momentum is working.'
                    : parseFloat(latest.ret_1m) >= 0
                      ? 'Marginally positive in the last month.'
                      : 'Negative 1-month return. Short-term price pressure.'
                  : 'Insufficient data.'
                }</p>
              </Commentary>
            </div>

            {/* 6M Return */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
              <IndicatorChart
                title="6-Month Return"
                description="Rolling 6-month price return. Medium-term trend confirmation."
                currentValue={pctStr(latest?.ret_6m)}
                isBullish={latest?.ret_6m != null ? parseFloat(latest.ret_6m) >= 0 : null}
                data={ret6mData}
                refLine={0}
                refLabel="0"
                variant="area"
                yFormat="pct"
              />
              <Commentary title={`6M Return · ${pctStr(latest?.ret_6m)}`}>
                <p>{latest?.ret_6m != null
                  ? parseFloat(latest.ret_6m) >= 0.15
                    ? 'Strong 6-month return. Sustained uptrend.'
                    : parseFloat(latest.ret_6m) >= 0
                      ? 'Positive 6-month return. Trend intact.'
                      : 'Negative 6-month return. Medium-term weakness.'
                  : 'Insufficient data.'
                }</p>
              </Commentary>
            </div>

            {/* Extension vs 200-day MA */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
              <IndicatorChart
                title="Extension vs 200-Day MA"
                description="How far the ETF price is above (+) or below (−) its 200-day moving average. Values above +40% indicate over-extension and elevated reversal risk."
                currentValue={rawPct(latest?.extension_pct) + '%'}
                isBullish={latest?.extension_pct != null
                  ? parseFloat(latest.extension_pct) > 0 && parseFloat(latest.extension_pct) < 0.4
                  : null
                }
                data={extensionData}
                refLine={0.4}
                refLabel="+40% risk zone"
                variant="area"
                yFormat="pct"
              />
              <Commentary title={`Extension · ${rawPct(latest?.extension_pct)}%`}>
                <p>{latest?.extension_pct != null
                  ? parseFloat(latest.extension_pct) >= 0.4
                    ? 'Over-extended above 200-day MA. Risk gate may fail. Consider reducing size.'
                    : parseFloat(latest.extension_pct) >= 0
                      ? 'Within normal extension range. No elevated reversion risk.'
                      : 'Trading below 200-day MA. Stage 3/4 caution — Weinstein gate likely failing.'
                  : 'No extension data.'
                }</p>
                <p className="text-ink-tertiary/70 text-[10px] mt-1">
                  Extension = (Price − 200-day MA) ÷ 200-day MA. The 200-day MA is the primary trend line in Weinstein Stage Analysis.
                </p>
              </Commentary>
            </div>

            {/* Realised Volatility */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
              <IndicatorChart
                title="Realised Volatility (63D)"
                description="Annualised realised volatility over the last 63 trading days (~3 months). High volatility increases position sizing risk."
                currentValue={rawPct(latest?.vol_63) + '%'}
                isBullish={latest?.vol_63 != null ? parseFloat(latest.vol_63) < 0.20 : null}
                data={volData}
                refLine={0.20}
                refLabel="20% normal"
                variant="line"
                yFormat="pct"
              />
              <Commentary title={`Vol 63D · ${rawPct(latest?.vol_63)}%`}>
                <p>{latest?.vol_63 != null
                  ? parseFloat(latest.vol_63) > 0.30
                    ? 'Elevated volatility. Reduce position size or wait for vol to compress.'
                    : parseFloat(latest.vol_63) > 0.20
                      ? 'Above-average volatility. Factor into position sizing.'
                      : 'Low volatility. ETF suitable for full-size positions.'
                  : 'No volatility data.'
                }</p>
              </Commentary>
            </div>

            {/* Drawdown */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
              <IndicatorChart
                title="Drawdown from 52-Week High"
                description="Current price vs peak price over the last 252 trading days. A drawdown below −20% indicates significant technical damage."
                currentValue={pctStr(latest?.drawdown)}
                isBullish={latest?.drawdown != null ? parseFloat(latest.drawdown) > -0.10 : null}
                data={drawdownData}
                refLine={-0.20}
                refLabel="−20% damage zone"
                variant="area"
                yFormat="pct"
              />
              <Commentary title={`Drawdown · ${pctStr(latest?.drawdown)}`}>
                <p>{latest?.drawdown != null
                  ? parseFloat(latest.drawdown) < -0.20
                    ? 'Significant drawdown. Technical damage present. Wait for base formation.'
                    : parseFloat(latest.drawdown) < -0.10
                      ? 'Moderate drawdown. Monitor for recovery above key moving averages.'
                      : 'Shallow drawdown. ETF in good technical health.'
                  : 'No drawdown data.'
                }</p>
              </Commentary>
            </div>
```

- [ ] **Step 3: Run type check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

- [ ] **Step 4: Run full test suite**

```bash
cd frontend && npx vitest run
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/etfs/ETFOverviewTab.tsx
git commit -m "feat(etf): add 1M/6M return, extension, volatility, drawdown charts to deep dive"
```

---

## Task 7: Term explanations — Weinstein/Extension tooltips, labeled attributes in header

**Files:**
- Modify: `frontend/src/components/etfs/ETFSnapshotTiles.tsx` — subtitle text for Weinstein + Extension
- Modify: `frontend/src/components/etfs/ETFDeepDiveHeader.tsx` — labeled "Tracks:" and "Sector:" text

- [ ] **Step 1: Update ETFSnapshotTiles to add subtitle/title to Weinstein and Extension**

In `frontend/src/components/etfs/ETFSnapshotTiles.tsx`, update the `Tile` component to accept an optional `subtitle` prop:

```typescript
function Tile({ label, value, color, subtitle }: { label: string; value: string; color?: string; subtitle?: string }) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3 border-r border-paper-rule last:border-0">
      <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
        {label}
      </div>
      <div className={`font-mono text-sm font-semibold tabular-nums ${color ?? 'text-ink-primary'}`}>
        {value}
      </div>
      {subtitle && (
        <div className="font-sans text-[9px] text-ink-tertiary/60 leading-tight">{subtitle}</div>
      )}
    </div>
  )
}
```

Then update the Weinstein and Extension tiles to include subtitles:

```typescript
      <Tile
        label="Weinstein"
        value={etf.weinstein_gate_pass == null ? '—' : etf.weinstein_gate_pass ? 'Pass ✓' : 'Fail ✗'}
        color={etf.weinstein_gate_pass == null ? 'text-ink-tertiary' : etf.weinstein_gate_pass ? 'text-signal-pos' : 'text-signal-neg'}
        subtitle="Price above 30-week MA (Stage 2 uptrend)"
      />
      <Tile
        label="Extension"
        value={extPct}
        color={extColor}
        subtitle="% above/below 200-day MA"
      />
```

- [ ] **Step 2: Update ETFDeepDiveHeader to label attributes**

In `frontend/src/components/etfs/ETFDeepDiveHeader.tsx`, replace the unlabeled linked_sector and linked_index spans:

```typescript
            {etf.linked_sector && (
              <span className="font-sans text-xs text-ink-tertiary">
                <span className="text-[10px] font-semibold uppercase tracking-wider mr-0.5">Sector:</span>
                {etf.linked_sector}
              </span>
            )}
            {etf.linked_index && (
              <span className="font-sans text-xs text-ink-tertiary bg-paper-rule/30 px-1.5 py-0.5 rounded">
                <span className="text-[10px] font-semibold uppercase tracking-wider mr-0.5">Tracks:</span>
                {etf.linked_index}
              </span>
            )}
```

Also wrap `StateTuple3` with a label:

```typescript
            <div className="flex items-center gap-1">
              <span className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">States:</span>
              <StateTuple3
                rs={etf.rs_state}
                mom={etf.momentum_state}
                risk={etf.risk_state}
              />
            </div>
```

- [ ] **Step 3: Run type check + tests**

```bash
cd frontend && npx tsc --noEmit && npx vitest run
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/etfs/ETFSnapshotTiles.tsx \
        frontend/src/components/etfs/ETFDeepDiveHeader.tsx
git commit -m "feat(etf): add Weinstein/Extension explanations and labeled header attributes"
```

---

## Task 8: Add getLinkedETFsForSector query

**Files:**
- Modify: `frontend/src/lib/queries/etfs.ts` — add `getLinkedETFsForSector`

- [ ] **Step 1: Add `getLinkedETFsForSector` at the end of etfs.ts**

```typescript
export async function getLinkedETFsForSector(sectorName: string): Promise<ETFRow[]> {
  return sql<ETFRow[]>`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_etf_metrics_daily
    )
    SELECT
      u.ticker,
      u.etf_name,
      u.theme,
      u.linked_sector,
      u.linked_index,
      u.inception_date::text        AS inception_date,
      u.asset_class,
      u.fund_house,
      l.d::text                     AS data_as_of,
      m.ret_1m::text                AS ret_1m,
      m.ret_3m::text                AS ret_3m,
      m.ret_6m::text                AS ret_6m,
      m.rs_pctile_3m::text          AS rs_pctile_3m,
      m.ema_10_ratio::text          AS ema_10_ratio,
      m.extension_pct::text         AS extension_pct,
      m.ret_1w::text                AS ret_1w,
      m.realized_vol_63::text       AS vol_63,
      m.drawdown_ratio_252::text    AS drawdown,
      (CURRENT_DATE - s.state_since_date)::int AS days_in_state,
      s.rs_state,
      s.momentum_state,
      s.risk_state,
      s.weinstein_gate_pass,
      s.history_gate_pass,
      s.liquidity_gate_pass,
      d.is_investable,
      d.strength_gate,
      d.direction_gate,
      d.risk_gate,
      d.sector_gate,
      d.market_gate,
      d.position_size_pct::text     AS position_size_pct,
      d.exit_market_riskoff,
      d.exit_sector_avoid,
      d.exit_rs_deteriorate,
      d.exit_momentum_collapse,
      d.exit_stop_loss
    FROM atlas.atlas_universe_etfs u
    JOIN latest l ON TRUE
    LEFT JOIN atlas.atlas_etf_metrics_daily m
      ON m.ticker = u.ticker AND m.date = l.d
    LEFT JOIN atlas.atlas_etf_states_daily s
      ON s.ticker = u.ticker AND s.date = l.d
    LEFT JOIN atlas.atlas_etf_decisions_daily d
      ON d.ticker = u.ticker AND d.date = l.d
    WHERE u.linked_sector = ${sectorName}
      AND u.effective_to IS NULL
    ORDER BY m.rs_pctile_3m DESC NULLS LAST
  `
}
```

- [ ] **Step 2: Run type check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/queries/etfs.ts
git commit -m "feat(sector): add getLinkedETFsForSector query"
```

---

## Task 9: Sector fund attribution query

**Files:**
- Create: `frontend/src/lib/queries/sector-funds.ts`

- [ ] **Step 1: Create the file with type and query**

```typescript
// frontend/src/lib/queries/sector-funds.ts
import 'server-only'
import sql from '@/lib/db'

export type SectorFundRow = {
  mstar_id: string
  scheme_name: string
  amc: string
  category_name: string
  broad_category: string
  sector_weight_pct: string | null
  sector_rank: number
  data_as_of: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  rs_pctile_3m: string | null
  realized_vol_63: string | null
  drawdown_ratio_252: string | null
  nav_state: string | null
  composition_state: string | null
  holdings_state: string | null
  recommendation: string | null
  performance_gate: boolean | null
  sectors_gate: boolean | null
  stocks_gate: boolean | null
  market_gate: boolean | null
  entry_trigger: boolean | null
  exit_trigger: boolean | null
}

export async function getSectorFunds(
  sectorName: string,
  limit = 30,
): Promise<SectorFundRow[]> {
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new Error(`limit must be between 1 and 100, got: ${limit}`)
  }
  return sql<SectorFundRow[]>`
    WITH latest_holdings AS (
      SELECT mstar_id, MAX(as_of_date) AS as_of_date
      FROM public.de_mf_holdings
      GROUP BY mstar_id
    ),
    sector_weights AS (
      SELECT
        h.mstar_id,
        COALESCE(u.sector, 'Unknown') AS sector,
        SUM(h.weight_pct)             AS sector_weight_pct
      FROM public.de_mf_holdings h
      JOIN latest_holdings lh ON h.mstar_id = lh.mstar_id AND h.as_of_date = lh.as_of_date
      LEFT JOIN atlas.atlas_universe_stocks u
        ON u.instrument_id = h.instrument_id AND u.effective_to IS NULL
      WHERE u.sector IS NOT NULL
      GROUP BY h.mstar_id, u.sector
    ),
    ranked_sectors AS (
      SELECT
        mstar_id,
        sector,
        sector_weight_pct,
        RANK() OVER (PARTITION BY mstar_id ORDER BY sector_weight_pct DESC) AS sector_rank
      FROM sector_weights
    ),
    qualifying AS (
      SELECT mstar_id, sector_weight_pct::text AS sector_weight_pct, sector_rank::int AS sector_rank
      FROM ranked_sectors
      WHERE sector = ${sectorName} AND sector_rank <= 3
    )
    SELECT
      uf.mstar_id,
      uf.scheme_name,
      uf.amc,
      uf.category_name,
      uf.broad_category,
      q.sector_weight_pct,
      q.sector_rank,
      (SELECT MAX(nav_date)::text FROM atlas.atlas_fund_metrics_daily) AS data_as_of,
      fm.ret_1m::text           AS ret_1m,
      fm.ret_3m::text           AS ret_3m,
      fm.ret_6m::text           AS ret_6m,
      fm.ret_12m::text          AS ret_12m,
      fm.rs_pctile_3m::text     AS rs_pctile_3m,
      fm.realized_vol_63::text  AS realized_vol_63,
      fm.drawdown_ratio_252::text AS drawdown_ratio_252,
      fs.nav_state,
      fs.composition_state,
      fs.holdings_state,
      fd.recommendation,
      fd.performance_gate,
      fd.sectors_gate,
      fd.stocks_gate,
      fd.market_gate,
      fd.entry_trigger,
      fd.exit_trigger
    FROM qualifying q
    JOIN atlas.atlas_universe_funds uf ON uf.mstar_id = q.mstar_id
    LEFT JOIN atlas.atlas_fund_metrics_daily fm
      ON fm.mstar_id = uf.mstar_id
      AND fm.nav_date = (SELECT MAX(nav_date) FROM atlas.atlas_fund_metrics_daily)
    LEFT JOIN atlas.atlas_fund_states_daily fs
      ON fs.mstar_id = uf.mstar_id
      AND fs.date = (SELECT MAX(date) FROM atlas.atlas_fund_states_daily)
    LEFT JOIN atlas.atlas_fund_decisions_daily fd
      ON fd.mstar_id = uf.mstar_id
      AND fd.date = (SELECT MAX(date) FROM atlas.atlas_fund_decisions_daily)
    ORDER BY q.sector_weight_pct DESC NULLS LAST, fm.rs_pctile_3m DESC NULLS LAST
    LIMIT ${limit}
  `
}
```

- [ ] **Step 2: Run type check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/queries/sector-funds.ts
git commit -m "feat(sector): add getSectorFunds sector attribution query"
```

---

## Task 10: SectorETFTab component

**Files:**
- Create: `frontend/src/components/sectors/SectorETFTab.tsx`

- [ ] **Step 1: Write test**

```typescript
// frontend/src/components/sectors/__tests__/SectorETFTab.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SectorETFTab } from '../SectorETFTab'
import type { ETFRow } from '@/lib/queries/etfs'

const ETF: ETFRow = {
  ticker: 'BANKBEES', etf_name: 'Nippon India ETF Bank BeES', theme: 'Sectoral',
  linked_sector: 'Financials', linked_index: 'NIFTY BANK', inception_date: null,
  asset_class: 'Equity', fund_house: 'Nippon', data_as_of: '2026-05-09',
  ret_1m: '0.04', ret_3m: '0.10', ret_6m: null, rs_pctile_3m: '0.68',
  ema_10_ratio: '1.01', extension_pct: '0.03', ret_1w: '0.01',
  vol_63: '0.19', drawdown: '-0.06', days_in_state: 30,
  rs_state: 'Strong', momentum_state: 'Improving', risk_state: 'Normal',
  weinstein_gate_pass: true, history_gate_pass: true, liquidity_gate_pass: true,
  is_investable: true, strength_gate: true, direction_gate: true,
  risk_gate: true, sector_gate: true, market_gate: true,
  position_size_pct: '0.07',
  exit_market_riskoff: false, exit_sector_avoid: false, exit_rs_deteriorate: false,
  exit_momentum_collapse: false, exit_stop_loss: false,
}

describe('SectorETFTab', () => {
  it('renders the ETF ticker and link to deep dive', () => {
    render(<SectorETFTab etfs={[ETF]} sectorName="Financials" />)
    expect(screen.getByText('BANKBEES')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /bankbees/i })
    expect(link).toHaveAttribute('href', '/etfs/BANKBEES')
  })

  it('renders empty state when no ETFs', () => {
    render(<SectorETFTab etfs={[]} sectorName="Financials" />)
    expect(screen.getByText(/No ETF linked/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd frontend && npx vitest run src/components/sectors/__tests__/SectorETFTab.test.tsx
```
Expected: FAIL — component doesn't exist

- [ ] **Step 3: Create SectorETFTab.tsx**

```typescript
// frontend/src/components/sectors/SectorETFTab.tsx
import Link from 'next/link'
import type { ETFRow } from '@/lib/queries/etfs'
import { RSStateChip, MomentumChip, RiskChip, pct, pctColor } from '@/lib/stock-formatters'
import { ETFGatesPanel } from '@/components/etfs/ETFGatesPanel'

function pctVal(v: string | null, digits = 1): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`
}

function MetricTile({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3 border-r border-paper-rule last:border-0">
      <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">{label}</div>
      <div className={`font-mono text-sm font-semibold ${color ?? 'text-ink-primary'}`}>{value}</div>
    </div>
  )
}

function ETFCard({ etf }: { etf: ETFRow }) {
  const rsPctile = etf.rs_pctile_3m != null
    ? `${(parseFloat(etf.rs_pctile_3m) * 100).toFixed(0)}th`
    : '—'
  const rsPctileColor = etf.rs_pctile_3m != null
    ? parseFloat(etf.rs_pctile_3m) >= 0.7 ? 'text-signal-pos'
      : parseFloat(etf.rs_pctile_3m) >= 0.4 ? 'text-signal-warn'
      : 'text-signal-neg'
    : 'text-ink-tertiary'

  return (
    <div className="border border-paper-rule rounded-sm bg-paper">
      {/* Header */}
      <div className="px-5 py-4 border-b border-paper-rule flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link
              href={`/etfs/${etf.ticker}`}
              className="font-serif text-2xl font-semibold text-ink-primary hover:text-teal transition-colors"
            >
              {etf.ticker}
            </Link>
            <span className="font-sans text-[10px] font-semibold bg-signal-pos/10 text-signal-pos px-1.5 py-0.5 rounded">
              {etf.theme}
            </span>
          </div>
          <div className="font-sans text-xs text-ink-secondary">{etf.etf_name}</div>
          {etf.linked_index && (
            <div className="font-sans text-[11px] text-ink-tertiary mt-0.5">
              Tracks: {etf.linked_index}
            </div>
          )}
        </div>
        <div className="shrink-0">
          {etf.is_investable ? (
            <span className="font-sans text-xs font-semibold text-signal-pos bg-signal-pos/10 px-2.5 py-1 rounded">
              ● Investable
            </span>
          ) : (
            <span className="font-sans text-xs font-semibold text-ink-tertiary bg-paper-rule/30 px-2.5 py-1 rounded">
              Not Investable
            </span>
          )}
        </div>
      </div>

      {/* Metrics strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 border-b border-paper-rule">
        <MetricTile label="RS Pctile" value={rsPctile} color={rsPctileColor} />
        <MetricTile label="1M Return" value={pctVal(etf.ret_1m)} color={pctColor(etf.ret_1m)} />
        <MetricTile label="3M Return" value={pctVal(etf.ret_3m)} color={pctColor(etf.ret_3m)} />
        <MetricTile label="6M Return" value={pctVal(etf.ret_6m)} color={pctColor(etf.ret_6m)} />
        <MetricTile
          label="Weinstein"
          value={etf.weinstein_gate_pass == null ? '—' : etf.weinstein_gate_pass ? 'Pass ✓' : 'Fail ✗'}
          color={etf.weinstein_gate_pass ? 'text-signal-pos' : 'text-signal-neg'}
        />
        <MetricTile
          label="Extension"
          value={etf.extension_pct != null ? `${(parseFloat(etf.extension_pct) * 100).toFixed(1)}%` : '—'}
        />
      </div>

      {/* States + gates */}
      <div className="p-5 grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-3">
            State Assessment
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <span className="font-sans text-[11px] text-ink-tertiary w-20">RS State</span>
              <RSStateChip value={etf.rs_state} />
            </div>
            <div className="flex items-center gap-3">
              <span className="font-sans text-[11px] text-ink-tertiary w-20">Momentum</span>
              <MomentumChip value={etf.momentum_state} />
            </div>
            <div className="flex items-center gap-3">
              <span className="font-sans text-[11px] text-ink-tertiary w-20">Risk</span>
              <RiskChip value={etf.risk_state} />
            </div>
          </div>
          <div className="mt-4">
            <Link
              href={`/etfs/${etf.ticker}`}
              className="inline-flex items-center gap-1.5 font-sans text-xs text-teal hover:underline"
            >
              Full deep dive →
            </Link>
          </div>
        </div>
        <ETFGatesPanel etf={etf} />
      </div>
    </div>
  )
}

export function SectorETFTab({
  etfs,
  sectorName,
}: {
  etfs: ETFRow[]
  sectorName: string
}) {
  if (etfs.length === 0) {
    return (
      <div className="px-6 py-10 text-center">
        <p className="font-sans text-sm text-ink-tertiary">
          No ETF linked to the {sectorName} sector in the universe.
        </p>
      </div>
    )
  }

  return (
    <div className="px-6 py-6 space-y-4">
      <div className="font-sans text-xs text-ink-tertiary">
        {etfs.length === 1
          ? `1 ETF tracks the ${sectorName} sector.`
          : `${etfs.length} ETFs track the ${sectorName} sector.`
        }
      </div>
      {etfs.map(etf => (
        <ETFCard key={etf.ticker} etf={etf} />
      ))}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend && npx vitest run src/components/sectors/__tests__/SectorETFTab.test.tsx
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/sectors/SectorETFTab.tsx \
        frontend/src/components/sectors/__tests__/SectorETFTab.test.tsx
git commit -m "feat(sector): add SectorETFTab component"
```

---

## Task 11: SectorFundsTab component

**Files:**
- Create: `frontend/src/components/sectors/SectorFundsTab.tsx`

- [ ] **Step 1: Write test**

```typescript
// frontend/src/components/sectors/__tests__/SectorFundsTab.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SectorFundsTab } from '../SectorFundsTab'
import type { SectorFundRow } from '@/lib/queries/sector-funds'

const FUND: SectorFundRow = {
  mstar_id: 'F00001G6N5',
  scheme_name: 'Mirae Asset Banking & Financial Services Fund',
  amc: 'Mirae Asset',
  category_name: 'Sectoral/Thematic',
  broad_category: 'Equity',
  sector_weight_pct: '32.5',
  sector_rank: 1,
  data_as_of: '2026-05-09',
  ret_1m: '0.04', ret_3m: '0.11', ret_6m: '0.17', ret_12m: '0.22',
  rs_pctile_3m: '0.74', realized_vol_63: '0.20', drawdown_ratio_252: '-0.08',
  nav_state: 'Uptrend', composition_state: 'Aligned', holdings_state: 'Strong',
  recommendation: 'Recommended',
  performance_gate: true, sectors_gate: true, stocks_gate: true, market_gate: true,
  entry_trigger: false, exit_trigger: false,
}

describe('SectorFundsTab', () => {
  it('renders fund scheme name with link to deep dive', () => {
    render(<SectorFundsTab funds={[FUND]} sectorName="Financials" />)
    expect(screen.getByText(/Mirae Asset Banking/i)).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /Mirae Asset Banking/i })
    expect(link).toHaveAttribute('href', '/funds/F00001G6N5')
  })

  it('renders sector weight', () => {
    render(<SectorFundsTab funds={[FUND]} sectorName="Financials" />)
    expect(screen.getByText(/32.5%/)).toBeInTheDocument()
  })

  it('renders empty state when no funds', () => {
    render(<SectorFundsTab funds={[]} sectorName="Financials" />)
    expect(screen.getByText(/No mutual funds/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd frontend && npx vitest run src/components/sectors/__tests__/SectorFundsTab.test.tsx
```
Expected: FAIL — component doesn't exist

- [ ] **Step 3: Create SectorFundsTab.tsx**

```typescript
// frontend/src/components/sectors/SectorFundsTab.tsx
import Link from 'next/link'
import type { SectorFundRow } from '@/lib/queries/sector-funds'
import { NavStateChip, RecommendationChip } from '@/lib/fund-formatters'

function pct(v: string | null, digits = 1): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`
}

function weight(v: string | null): string {
  if (v == null) return '—'
  return `${parseFloat(v).toFixed(1)}%`
}

function GateDot({ pass }: { pass: boolean | null }) {
  if (pass === null) return <span className="font-mono text-[10px] text-ink-tertiary">?</span>
  return (
    <span className={`font-mono text-xs font-semibold ${pass ? 'text-signal-pos' : 'text-signal-neg'}`}>
      {pass ? '✓' : '✗'}
    </span>
  )
}

export function SectorFundsTab({
  funds,
  sectorName,
}: {
  funds: SectorFundRow[]
  sectorName: string
}) {
  if (funds.length === 0) {
    return (
      <div className="px-6 py-10 text-center">
        <p className="font-sans text-sm text-ink-tertiary">
          No mutual funds with {sectorName} in their top 3 sector allocations.
        </p>
      </div>
    )
  }

  return (
    <div className="px-6 py-6 space-y-4">
      <div className="font-sans text-xs text-ink-tertiary">
        {funds.length} fund{funds.length !== 1 ? 's' : ''} with {sectorName} as a top-3 sector holding — ranked by sector allocation weight.
      </div>

      <div className="overflow-x-auto">
        <table className="w-full font-sans text-xs border-collapse">
          <thead>
            <tr className="border-b border-paper-rule bg-paper">
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">#</th>
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">Fund</th>
              <th className="px-3 py-2 text-right font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]" title={`% of portfolio allocated to ${sectorName}`}>
                {sectorName} Wt
              </th>
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">Rating</th>
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">NAV State</th>
              <th className="px-3 py-2 text-right font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">RS Pctile</th>
              <th className="px-3 py-2 text-right font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">1M</th>
              <th className="px-3 py-2 text-right font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">3M</th>
              <th className="px-3 py-2 text-right font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">12M</th>
              <th className="px-3 py-2 text-center font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]" title="Quality gates: Performance / Sectors / Holdings / Market">
                Gates P/S/H/M
              </th>
            </tr>
          </thead>
          <tbody>
            {funds.map((f, i) => (
              <tr
                key={f.mstar_id}
                className="border-b border-paper-rule/50 hover:bg-paper-rule/10 transition-colors"
              >
                <td className="px-3 py-2.5 font-mono text-ink-tertiary">{i + 1}</td>
                <td className="px-3 py-2.5">
                  <Link
                    href={`/funds/${f.mstar_id}`}
                    className="font-semibold text-ink-primary hover:text-teal transition-colors block"
                  >
                    {f.scheme_name}
                  </Link>
                  <div className="text-[10px] text-ink-tertiary">{f.amc} · {f.category_name}</div>
                </td>
                <td className="px-3 py-2.5 text-right font-mono font-semibold text-teal">
                  {weight(f.sector_weight_pct)}
                </td>
                <td className="px-3 py-2.5">
                  <RecommendationChip value={f.recommendation} />
                </td>
                <td className="px-3 py-2.5">
                  <NavStateChip value={f.nav_state} />
                </td>
                <td className="px-3 py-2.5 text-right font-mono">
                  {f.rs_pctile_3m != null ? `${(parseFloat(f.rs_pctile_3m) * 100).toFixed(0)}` : '—'}
                </td>
                <td className={`px-3 py-2.5 text-right font-mono ${f.ret_1m != null && parseFloat(f.ret_1m) >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
                  {pct(f.ret_1m)}
                </td>
                <td className={`px-3 py-2.5 text-right font-mono ${f.ret_3m != null && parseFloat(f.ret_3m) >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
                  {pct(f.ret_3m)}
                </td>
                <td className={`px-3 py-2.5 text-right font-mono ${f.ret_12m != null && parseFloat(f.ret_12m) >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
                  {pct(f.ret_12m)}
                </td>
                <td className="px-3 py-2.5">
                  <div className="flex items-center justify-center gap-1.5">
                    <GateDot pass={f.performance_gate} />
                    <GateDot pass={f.sectors_gate} />
                    <GateDot pass={f.stocks_gate} />
                    <GateDot pass={f.market_gate} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend && npx vitest run src/components/sectors/__tests__/SectorFundsTab.test.tsx
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/sectors/SectorFundsTab.tsx \
        frontend/src/components/sectors/__tests__/SectorFundsTab.test.tsx
git commit -m "feat(sector): add SectorFundsTab component"
```

---

## Task 12: Update SectorDeepDiveTabs with ETF + Funds tabs

**Files:**
- Modify: `frontend/src/components/sectors/SectorDeepDiveTabs.tsx`

- [ ] **Step 1: Replace SectorDeepDiveTabs.tsx**

```typescript
// frontend/src/components/sectors/SectorDeepDiveTabs.tsx
'use client'
import Link from 'next/link'
import type { TimeRange } from '@/lib/time-range'

type Tab = 'overview' | 'stocks' | 'etf' | 'funds'

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'stocks',   label: 'Stocks' },
  { id: 'etf',      label: 'ETF' },
  { id: 'funds',    label: 'Funds' },
]

export function SectorDeepDiveTabs({
  sectorName,
  activeTab,
  range,
}: {
  sectorName: string
  activeTab: Tab
  range: TimeRange
}) {
  return (
    <div className="sticky top-[150px] bg-paper border-b border-paper-rule z-20">
      <div className="px-6">
        <div className="flex gap-1" role="tablist" aria-label="Sector deep dive tabs">
          {TABS.map(tab => {
            const isActive = tab.id === activeTab
            const params = new URLSearchParams()
            if (tab.id !== 'overview') params.set('tab', tab.id)
            params.set('range', range)
            const href = `/sectors/${encodeURIComponent(sectorName)}${params.toString() ? `?${params.toString()}` : ''}`
            return (
              <Link
                key={tab.id}
                href={href}
                role="tab"
                aria-selected={isActive}
                className={`relative px-4 py-3 font-sans text-sm transition-colors ${
                  isActive
                    ? 'text-ink-primary font-semibold'
                    : 'text-ink-tertiary hover:text-ink-secondary'
                }`}
              >
                {tab.label}
                {isActive && (
                  <span className="absolute left-0 right-0 -bottom-px h-0.5 bg-teal" aria-hidden="true" />
                )}
              </Link>
            )
          })}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Run type check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/sectors/SectorDeepDiveTabs.tsx
git commit -m "feat(sector): add ETF and Funds tabs to sector deep dive navigation"
```

---

## Task 13: Update sector/[name]/page.tsx to fetch and render ETF + Funds tabs

**Files:**
- Modify: `frontend/src/app/sectors/[name]/page.tsx`

- [ ] **Step 1: Replace the page file**

```typescript
// frontend/src/app/sectors/[name]/page.tsx
import { notFound } from 'next/navigation'
import { Suspense } from 'react'
import {
  getSectorSnapshotByName,
  getStocksInSector,
} from '@/lib/queries/sector-deep-dive'
import {
  getBreadthWaterfallData,
  getSectorMetricHistory,
  getSectorStateHistory,
} from '@/lib/queries/sectors'
import { getLinkedETFsForSector } from '@/lib/queries/etfs'
import { getSectorFunds } from '@/lib/queries/sector-funds'
import { rangeToDays, type TimeRange } from '@/lib/time-range'
import { getSectorDecision } from '@/lib/sectors-decision'
import { getCurrentRegime } from '@/lib/queries/regime'
import { SectorDeepDiveHeader } from '@/components/sectors/SectorDeepDiveHeader'
import { SectorDeepDiveTabs } from '@/components/sectors/SectorDeepDiveTabs'
import { SectorOverviewTab } from '@/components/sectors/SectorOverviewTab'
import { SectorStocksTab } from '@/components/sectors/SectorStocksTab'
import { SectorETFTab } from '@/components/sectors/SectorETFTab'
import { SectorFundsTab } from '@/components/sectors/SectorFundsTab'

type SearchParams = Promise<{ range?: string; tab?: string }>
type Params = Promise<{ name: string }>

export default async function SectorDeepDivePage({
  params,
  searchParams,
}: {
  params: Params
  searchParams: SearchParams
}) {
  const { name: rawName } = await params
  const { range = '6M', tab = 'overview' } = await searchParams

  const sectorName = decodeURIComponent(rawName)
  const VALID_RANGES: TimeRange[] = ['1W', '1M', '3M', '6M', '1Y']
  const historyRange: TimeRange = VALID_RANGES.includes(range as TimeRange)
    ? (range as TimeRange)
    : '6M'
  const days = rangeToDays(historyRange)
  const activeTab = (['overview', 'stocks', 'etf', 'funds'] as const).includes(tab as 'overview' | 'stocks' | 'etf' | 'funds')
    ? (tab as 'overview' | 'stocks' | 'etf' | 'funds')
    : 'overview'

  const [snapshot, metricHistory, stateHistory, stocks, regime, breadthData, linkedETFs, sectorFunds] = await Promise.all([
    getSectorSnapshotByName(sectorName),
    getSectorMetricHistory(sectorName, days).catch(() => [] as Awaited<ReturnType<typeof getSectorMetricHistory>>),
    getSectorStateHistory(days).catch(() => [] as Awaited<ReturnType<typeof getSectorStateHistory>>),
    getStocksInSector(sectorName).catch(() => [] as Awaited<ReturnType<typeof getStocksInSector>>),
    getCurrentRegime(),
    getBreadthWaterfallData(sectorName, 1095).catch(() => [] as Awaited<ReturnType<typeof getBreadthWaterfallData>>),
    getLinkedETFsForSector(sectorName).catch(() => []),
    getSectorFunds(sectorName).catch(() => []),
  ])

  if (!snapshot) {
    notFound()
  }

  const decision = getSectorDecision(
    snapshot.sector_state,
    snapshot.bottomup_rs_state,
    snapshot.bottomup_momentum_state,
  )
  const sectorWithDecision = { ...snapshot, decision }
  const sectorStateHistoryForThis = stateHistory.filter(h => h.sector_name === sectorName)

  return (
    <div className="max-w-[1400px] mx-auto">
      <SectorDeepDiveHeader
        snapshot={sectorWithDecision}
        range={historyRange}
      />
      <Suspense fallback={null}>
        <SectorDeepDiveTabs
          sectorName={sectorName}
          activeTab={activeTab}
          range={historyRange}
        />
      </Suspense>

      {activeTab === 'overview' && (
        <SectorOverviewTab
          snapshot={sectorWithDecision}
          metricHistory={metricHistory}
          stateHistory={sectorStateHistoryForThis}
          range={historyRange}
          regime={regime}
          breadthData={breadthData}
        />
      )}
      {activeTab === 'stocks' && (
        <SectorStocksTab
          sectorName={sectorName}
          stocks={stocks}
          range={historyRange}
          regime={regime}
        />
      )}
      {activeTab === 'etf' && (
        <SectorETFTab etfs={linkedETFs} sectorName={sectorName} />
      )}
      {activeTab === 'funds' && (
        <SectorFundsTab funds={sectorFunds} sectorName={sectorName} />
      )}
    </div>
  )
}
```

- [ ] **Step 2: Run type check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

- [ ] **Step 3: Run full test suite**

```bash
cd frontend && npx vitest run
```
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/sectors/\[name\]/page.tsx
git commit -m "feat(sector): wire ETF and Funds tabs into sector deep dive page"
```

---

## Task 14: Build, test, deploy

- [ ] **Step 1: Run full build**

```bash
cd frontend && npm run build 2>&1 | tail -30
```
Expected: build completes with no errors

- [ ] **Step 2: Run full test suite one final time**

```bash
cd frontend && npx vitest run
```
Expected: all pass

- [ ] **Step 3: Deploy to prod**

```bash
rsync -az --delete \
  --exclude='.next/cache' \
  -e "ssh -i ~/.ssh/jsl-wealth-key.pem" \
  /Users/nimishshah/Documents/GitHub/atlas-os/frontend/.next/ \
  ubuntu@13.202.162.196:/home/ubuntu/atlas-frontend/.next/

ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.202.162.196 \
  "pm2 restart atlas-frontend && sleep 3 && curl -s -o /dev/null -w '%{http_code}' http://localhost:3001/"
```
Expected: `200`

---

## Self-Review

### 1. Spec coverage check

| Requirement | Task |
|---|---|
| c) Intelligence band "0 leaders" inconsistency | Task 2 — add ILLIQUID/INSUFFICIENT_HISTORY + filter to Broad+Sectoral |
| d) Gate tooltips in ETF screener | Task 3 — title attributes on H/L/W/S/D/Ri |
| e) Gate deep dive with threshold info | Task 4 — threshold text in ETFGatesPanel |
| f) More timeframes in ETF deep dive | Task 5 — 3M/6M/1Y selector |
| f) More metric charts | Task 6 — Extension, Vol, Drawdown, 1M, 6M charts |
| g) Weinstein/Extension explanations | Task 7 — subtitle on tiles + labeled header |
| g) Labeled attributes in header | Task 7 — "Tracks:", "Sector:", "States:" labels |
| h) Sector page ETF tab | Tasks 8, 10, 12, 13 |
| h) Sector page Funds tab with attribution | Tasks 9, 11, 12, 13 |
| i) ETF page focus on Broad+Sectoral | Task 2 — SQL WHERE filter + chip removal |

### 2. Placeholder scan
No placeholders found. Every chart block includes complete code.

### 3. Type consistency
- `ETFMetricHistoryRow` expanded in Task 1; all chart references in Task 6 use `r.ret_1m`, `r.ret_6m`, `r.extension_pct`, `r.vol_63`, `r.drawdown` — all match the new type exactly.
- `SectorFundRow` defined in Task 9; all column references in `SectorFundsTab` (Task 11) match the type.
- `ETFRow` passed to `SectorETFTab` — same type as `getLinkedETFsForSector` returns.
- `range: TimeRange` added to `ETFDeepDiveTabs` props (Task 5) and `ETFOverviewTab` props (Task 5) consistently.
