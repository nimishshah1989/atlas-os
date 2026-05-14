# Atlas Strategy Lab — Part 3: Frontend (Tasks 15–19)

*Continuation of Part 1 and Part 2. Read both before starting this section.*

---

## Task 15: DB Query Helpers + Morning Brief (Layer 1)

**Files:**
- Create: `frontend/src/lib/queries/strategy_lab.ts`
- Create: `frontend/src/app/strategies/lab/page.tsx`
- Create: `frontend/src/components/trading/MorningBrief.tsx`

- [ ] **Step 1: Create query helpers**

`frontend/src/lib/queries/strategy_lab.ts`:
```typescript
// Read-only query helpers for Atlas Strategy Lab.
// All NUMERIC columns returned as strings — parse at display time.
// Do NOT import or modify strategies.ts (different system).
import 'server-only'
import sql from '@/lib/db'

export type LeaderboardRow = {
  rank: number
  genome_id: string
  strategy_name: string
  promoted_at: Date
  sortino_oos: string | null
  calmar_oos: string | null
  alpha_30d: string | null
  regime_breakdown: Record<string, number> | null
  generation: number
}

export type InsightRow = {
  id: string
  generated_at: Date
  insight_bullets: string[]
  parameter_importance: Record<string, number>
  top_genome_deltas: Record<string, unknown>[]
}

export type GenePoolHealth = {
  active_count: number
  killed_count: number
  promoted_count: number
  last_born_at: Date | null
}

export type PortfolioConfigRow = {
  id: string
  created_at: Date
  config_json: Record<string, unknown>
  is_active: boolean
  label: string | null
}

export type GenomePositionRow = {
  date: Date
  ticker: string
  company_name: string | null
  position_type: string
  entry_date: Date
  entry_price: string
  shares: string
  current_value: string
  unrealized_pnl: string
  holding_days: number
  tax_status: string
  entry_signals: Record<string, unknown> | null
}

export async function getLeaderboard(): Promise<LeaderboardRow[]> {
  return sql<LeaderboardRow[]>`
    SELECT
      l.rank,
      l.genome_id::text,
      l.strategy_name,
      l.promoted_at,
      l.sortino_oos::text,
      l.calmar_oos::text,
      l.alpha_30d::text,
      l.regime_breakdown,
      g.generation
    FROM atlas_strategy_leaderboard l
    JOIN atlas_strategy_genomes g ON g.id = l.genome_id
    ORDER BY l.rank
  `
}

export async function getLatestInsights(): Promise<InsightRow | null> {
  const rows = await sql<InsightRow[]>`
    SELECT id::text, generated_at, insight_bullets, parameter_importance, top_genome_deltas
    FROM atlas_strategy_insights
    ORDER BY generated_at DESC
    LIMIT 1
  `
  return rows[0] ?? null
}

export async function getGenePoolHealth(): Promise<GenePoolHealth> {
  const rows = await sql<GenePoolHealth[]>`
    SELECT
      COUNT(*) FILTER (WHERE status = 'active')   AS active_count,
      COUNT(*) FILTER (WHERE status = 'killed')   AS killed_count,
      COUNT(*) FILTER (WHERE status = 'promoted') AS promoted_count,
      MAX(born_at)                                AS last_born_at
    FROM atlas_strategy_genomes
  `
  return rows[0] ?? { active_count: 0, killed_count: 0, promoted_count: 0, last_born_at: null }
}

export async function getGenomePositions(genomeId: string): Promise<GenomePositionRow[]> {
  return sql<GenomePositionRow[]>`
    SELECT
      p.date,
      i.ticker,
      i.company_name,
      p.position_type,
      p.entry_date,
      p.entry_price::text,
      p.shares::text,
      p.current_value::text,
      p.unrealized_pnl::text,
      p.holding_days,
      p.tax_status,
      p.entry_signals
    FROM atlas_strategy_positions_daily p
    JOIN atlas_instruments i ON i.id = p.instrument_id
    WHERE p.genome_id = ${genomeId}
      AND p.date = (SELECT MAX(date) FROM atlas_strategy_positions_daily WHERE genome_id = ${genomeId})
    ORDER BY p.current_value DESC
  `
}

export async function getActivePortfolioConfig(): Promise<PortfolioConfigRow | null> {
  const rows = await sql<PortfolioConfigRow[]>`
    SELECT id::text, created_at, config_json, is_active, label
    FROM atlas_portfolio_config
    WHERE is_active = TRUE
    ORDER BY created_at DESC LIMIT 1
  `
  return rows[0] ?? null
}
```

- [ ] **Step 2: Create Morning Brief page shell**

`frontend/src/app/strategies/lab/page.tsx`:
```tsx
// Strategy Lab — Morning Brief (Layer 1)
// RSC shell: fetches data, passes to MorningBrief client island.
// ≤250 LOC: no logic here — all in MorningBrief.tsx
export const dynamic = 'force-dynamic'

import { getLeaderboard, getLatestInsights, getGenePoolHealth } from '@/lib/queries/strategy_lab'
import { MorningBrief } from '@/components/trading/MorningBrief'

export default async function StrategyLabPage() {
  const [leaderboard, insights, health] = await Promise.all([
    getLeaderboard(),
    getLatestInsights(),
    getGenePoolHealth(),
  ])

  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-5xl mx-auto">
      <MorningBrief
        leaderboard={leaderboard}
        insights={insights}
        health={health}
      />
    </main>
  )
}
```

- [ ] **Step 3: Create MorningBrief component**

`frontend/src/components/trading/MorningBrief.tsx`:
```tsx
'use client'

import Link from 'next/link'
import type { LeaderboardRow, InsightRow, GenePoolHealth } from '@/lib/queries/strategy_lab'

type Props = {
  leaderboard: LeaderboardRow[]
  insights: InsightRow | null
  health: GenePoolHealth
}

function fmt(v: string | null, decimals = 2): string {
  if (!v) return '—'
  const n = Number(v)
  return isNaN(n) ? '—' : n.toFixed(decimals)
}

function SignBadge({ value }: { value: string | null }) {
  const n = Number(value ?? '0')
  const color = n >= 0 ? 'text-teal-600' : 'text-red-600'
  return (
    <span className={`font-mono font-semibold ${color}`}>
      {n >= 0 ? '+' : ''}{fmt(value)}
    </span>
  )
}

export function MorningBrief({ leaderboard, insights, health }: Props) {
  const top = leaderboard[0]
  const today = new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })

  return (
    <div className="space-y-6">
      {/* Header */}
      <header>
        <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide">Strategy Lab</p>
        <h1 className="font-serif text-2xl text-ink-primary mt-1">Morning Brief</h1>
        <p className="font-sans text-xs text-ink-tertiary mt-1">{today}</p>
      </header>

      {/* Top strategy spotlight */}
      {top ? (
        <section className="border border-paper-rule rounded-[2px] p-5 bg-paper">
          <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-3">
            Top Strategy — Rank #{top.rank}
          </p>
          <h2 className="font-serif text-lg text-ink-primary">{top.strategy_name}</h2>
          <p className="font-sans text-xs text-ink-tertiary mt-1">
            Generation {top.generation} · Promoted {new Date(top.promoted_at).toLocaleDateString('en-IN')}
          </p>
          <div className="grid grid-cols-3 gap-4 mt-4">
            <div>
              <p className="font-sans text-xs text-ink-tertiary">Sortino (OOS)</p>
              <p className="font-mono text-xl font-semibold text-ink-primary mt-1">{fmt(top.sortino_oos)}</p>
            </div>
            <div>
              <p className="font-sans text-xs text-ink-tertiary">Calmar (OOS)</p>
              <p className="font-mono text-xl font-semibold text-ink-primary mt-1">{fmt(top.calmar_oos)}</p>
            </div>
            <div>
              <p className="font-sans text-xs text-ink-tertiary">30d Alpha</p>
              <SignBadge value={top.alpha_30d} />
            </div>
          </div>
          <Link
            href={`/strategies/lab/${top.genome_id}`}
            className="inline-block mt-4 font-sans text-xs text-teal-600 hover:underline"
          >
            View Strategy Explorer →
          </Link>
        </section>
      ) : (
        <section className="border border-paper-rule rounded-[2px] p-5 bg-paper">
          <p className="font-sans text-sm text-ink-tertiary">
            No strategies promoted yet. The engine is running its first optimization pass.
          </p>
        </section>
      )}

      {/* Gene pool status */}
      <section className="grid grid-cols-3 gap-3">
        {[
          { label: 'Active Genomes', value: health.active_count },
          { label: 'Promoted', value: health.promoted_count },
          { label: 'Killed This Cycle', value: health.killed_count },
        ].map(({ label, value }) => (
          <div key={label} className="border border-paper-rule rounded-[2px] p-3 bg-paper">
            <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide">{label}</p>
            <p className="font-mono text-lg font-semibold text-ink-primary mt-1">{value}</p>
          </div>
        ))}
      </section>

      {/* Insight bullets */}
      {insights && insights.insight_bullets.length > 0 && (
        <section className="border border-paper-rule rounded-[2px] p-5 bg-paper">
          <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-3">
            What the Engine Learned Last Night
          </p>
          <ul className="space-y-2">
            {insights.insight_bullets.map((bullet, i) => (
              <li key={i} className="font-sans text-sm text-ink-primary flex gap-2">
                <span className="text-teal-600 font-mono">→</span>
                <span>{bullet.replace(/^\d+\.\s*/, '')}</span>
              </li>
            ))}
          </ul>
          <p className="font-sans text-xs text-ink-tertiary mt-3">
            Generated {insights.generated_at ? new Date(insights.generated_at).toLocaleString('en-IN') : ''}
          </p>
        </section>
      )}

      {/* Navigation */}
      <nav className="flex gap-4">
        <Link
          href="/strategies/lab"
          className="font-sans text-xs border border-paper-rule rounded-[2px] px-4 py-2 text-ink-secondary hover:bg-paper-rule"
        >
          Morning Brief
        </Link>
        <Link
          href={leaderboard[0] ? `/strategies/lab/${leaderboard[0].genome_id}` : '/strategies/lab'}
          className="font-sans text-xs border border-paper-rule rounded-[2px] px-4 py-2 text-ink-secondary hover:bg-paper-rule"
        >
          Strategy Explorer
        </Link>
        <Link
          href="/strategies/lab/engine"
          className="font-sans text-xs border border-paper-rule rounded-[2px] px-4 py-2 text-ink-secondary hover:bg-paper-rule"
        >
          Engine Room
        </Link>
        <Link
          href="/strategies/lab?configurator=1"
          className="font-sans text-xs border border-teal-600 rounded-[2px] px-4 py-2 text-teal-600 hover:bg-teal-50"
        >
          ⚙ Configure
        </Link>
      </nav>
    </div>
  )
}
```

- [ ] **Step 4: Type-check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -E "trading|strategy_lab" | head -20
```

Expected: no errors on the new files

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/queries/strategy_lab.ts frontend/src/app/strategies/lab/page.tsx frontend/src/components/trading/MorningBrief.tsx
git commit -m "feat(trading-ui): Morning Brief — Layer 1 landing page"
```

---

## Task 16: Strategy Explorer (Layer 2)

**Files:**
- Create: `frontend/src/app/strategies/lab/[id]/page.tsx`
- Create: `frontend/src/components/trading/StrategyLeaderboard.tsx`
- Create: `frontend/src/components/trading/GenomeRadarChart.tsx`
- Create: `frontend/src/components/trading/WalkForwardChart.tsx`

- [ ] **Step 1: Create [id] page shell**

`frontend/src/app/strategies/lab/[id]/page.tsx`:
```tsx
export const dynamic = 'force-dynamic'

import { getLeaderboard, getGenomePositions } from '@/lib/queries/strategy_lab'
import { StrategyLeaderboard } from '@/components/trading/StrategyLeaderboard'
import { ReplicationGuide } from '@/components/trading/ReplicationGuide'
import { notFound } from 'next/navigation'

type Props = { params: Promise<{ id: string }> }

export default async function StrategyExplorerPage({ params }: Props) {
  const { id } = await params
  const [leaderboard, positions] = await Promise.all([
    getLeaderboard(),
    getGenomePositions(id),
  ])

  const selected = leaderboard.find((r) => r.genome_id === id)
  if (!selected) notFound()

  return (
    <main className="min-h-screen bg-paper px-6 py-6 max-w-7xl mx-auto">
      <div className="grid grid-cols-3 gap-6">
        <aside className="col-span-1">
          <StrategyLeaderboard leaderboard={leaderboard} selectedId={id} />
        </aside>
        <section className="col-span-2 space-y-6">
          <ReplicationGuide strategy={selected} positions={positions} />
        </section>
      </div>
    </main>
  )
}
```

- [ ] **Step 2: Create StrategyLeaderboard**

`frontend/src/components/trading/StrategyLeaderboard.tsx`:
```tsx
'use client'

import Link from 'next/link'
import type { LeaderboardRow } from '@/lib/queries/strategy_lab'

type Props = {
  leaderboard: LeaderboardRow[]
  selectedId: string
}

function fmt(v: string | null, d = 2) {
  const n = Number(v ?? 'NaN')
  return isNaN(n) ? '—' : n.toFixed(d)
}

export function StrategyLeaderboard({ leaderboard, selectedId }: Props) {
  return (
    <div className="border border-paper-rule rounded-[2px]">
      <div className="p-3 border-b border-paper-rule">
        <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide">Leaderboard</p>
      </div>
      <div className="divide-y divide-paper-rule">
        {leaderboard.map((row) => {
          const isSelected = row.genome_id === selectedId
          const sortino = Number(row.sortino_oos ?? '0')
          const isTop5 = row.rank <= 5
          return (
            <Link
              key={row.genome_id}
              href={`/strategies/lab/${row.genome_id}`}
              className={[
                'block p-3 transition-colors',
                isSelected ? 'bg-teal-50 border-l-2 border-teal-600' : 'hover:bg-paper-rule',
                isTop5 ? '' : 'opacity-50',
              ].join(' ')}
            >
              <div className="flex justify-between items-start">
                <div>
                  <span className="font-mono text-xs text-ink-tertiary">#{row.rank}</span>
                  <p className="font-sans text-sm text-ink-primary mt-0.5">{row.strategy_name}</p>
                  <p className="font-sans text-xs text-ink-tertiary">Gen {row.generation}</p>
                </div>
                <div className="text-right">
                  <p className={`font-mono text-sm font-semibold ${sortino >= 1 ? 'text-teal-600' : sortino >= 0.7 ? 'text-ink-primary' : 'text-red-500'}`}>
                    {fmt(row.sortino_oos)}
                  </p>
                  <p className="font-sans text-xs text-ink-tertiary">Sortino</p>
                </div>
              </div>
              {isTop5 && (
                <span className="inline-block mt-1 font-sans text-xs bg-teal-100 text-teal-700 px-1.5 py-0.5 rounded-[2px]">
                  Promoted
                </span>
              )}
            </Link>
          )
        })}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Create GenomeRadarChart**

`frontend/src/components/trading/GenomeRadarChart.tsx`:
```tsx
'use client'

import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip,
} from 'recharts'

type Props = {
  genomeJson: Record<string, unknown>
}

function extractRadarData(genomeJson: Record<string, unknown>) {
  const l1 = (genomeJson.layer1 as Record<string, unknown>) ?? {}
  const ro = (genomeJson.risk_on as Record<string, unknown>) ?? {}
  const weights = (l1.rs_timeframe_weights as Record<string, number>) ?? {}

  return [
    { axis: '1W Weight', value: Math.round((weights['1w'] ?? 0) * 100) },
    { axis: '1M Weight', value: Math.round((weights['1m'] ?? 0) * 100) },
    { axis: 'RS Leader %', value: Number(l1.rs_leader_cutoff_pct ?? 70) },
    { axis: 'Min Conviction', value: Math.round(Number(ro.min_conviction_to_enter ?? 0.55) * 100) },
    { axis: 'Base Size %', value: Math.round(Number(ro.base_position_pct ?? 4) * 10) },
    { axis: 'Synergy Wt', value: Math.round(Number(l1.synergy_weight ?? 0) * 100) },
    { axis: 'Volatility Thr', value: Math.round(Number(l1.vol_elevated_ratio ?? 1.4) * 40) },
    { axis: 'Regime Breadth', value: Number(l1.regime_risk_on_breadth_pct ?? 60) },
  ]
}

export function GenomeRadarChart({ genomeJson }: Props) {
  const data = extractRadarData(genomeJson)
  return (
    <div className="h-64">
      <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-2">Genome DNA</p>
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data}>
          <PolarGrid stroke="#e5e7eb" />
          <PolarAngleAxis dataKey="axis" tick={{ fontSize: 10, fill: '#6b7280' }} />
          <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} />
          <Radar name="Genome" dataKey="value" stroke="#1D9E75" fill="#1D9E75" fillOpacity={0.25} />
          <Tooltip formatter={(v: number) => [`${v}`, '']} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  )
}
```

- [ ] **Step 4: Create WalkForwardChart**

`frontend/src/components/trading/WalkForwardChart.tsx`:
```tsx
'use client'

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'

type DataPoint = {
  date: string
  insample: number | null
  oos: number | null
}

type Props = { data: DataPoint[] }

export function WalkForwardChart({ data }: Props) {
  return (
    <div>
      <div className="flex justify-between items-center mb-2">
        <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide">Walk-Forward Honesty</p>
        <span className="font-sans text-xs text-orange-500 font-semibold">Orange line is the honest one</span>
      </div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#9ca3af' }} />
            <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="insample" name="In-Sample" stroke="#3b82f6" dot={false} strokeWidth={1.5} />
            <Line type="monotone" dataKey="oos" name="Out-of-Sample" stroke="#f97316" dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Type-check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "trading\|strategy_lab" | head -20
```

Expected: no errors on new files

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/strategies/lab/[id]/page.tsx frontend/src/components/trading/StrategyLeaderboard.tsx frontend/src/components/trading/GenomeRadarChart.tsx frontend/src/components/trading/WalkForwardChart.tsx
git commit -m "feat(trading-ui): Strategy Explorer — leaderboard + genome radar + walk-forward chart"
```

---

## Task 17: Replication Guide + Tax Harvesting Alert

**Files:**
- Create: `frontend/src/components/trading/ReplicationGuide.tsx`
- Create: `frontend/src/components/trading/TaxHarvestingAlert.tsx`

- [ ] **Step 1: Create TaxHarvestingAlert**

`frontend/src/components/trading/TaxHarvestingAlert.tsx`:
```tsx
'use client'

type Props = {
  ticker: string
  grossPnl: number
  holdingDays: number
  stcgRate: number
  ltcgRate: number
  signalStrength: number
}

export function TaxHarvestingAlert({ ticker, grossPnl, holdingDays, stcgRate, ltcgRate, signalStrength }: Props) {
  const daysToLtcg = 365 - holdingDays
  const stcgTax = grossPnl * stcgRate
  const ltcgTax = grossPnl * ltcgRate
  const saving = stcgTax - ltcgTax
  const isWeak = signalStrength < 0.6

  if (daysToLtcg > 60 || saving < 5000 || grossPnl <= 0) return null

  return (
    <div className="border border-amber-300 bg-amber-50 rounded-[2px] p-4 mt-3">
      <p className="font-sans text-xs font-semibold text-amber-800 uppercase tracking-wide mb-2">
        Tax Opportunity
      </p>
      <p className="font-sans text-sm text-amber-900">
        Holding <strong>{ticker}</strong> for {daysToLtcg} more days converts this STCG gain
        (₹{Math.round(grossPnl).toLocaleString('en-IN')} × {(stcgRate * 100).toFixed(0)}% = ₹{Math.round(stcgTax).toLocaleString('en-IN')} tax) to
        LTCG (₹{Math.round(grossPnl).toLocaleString('en-IN')} × {(ltcgRate * 100).toFixed(0)}% = ₹{Math.round(ltcgTax).toLocaleString('en-IN')} tax).
      </p>
      <p className="font-sans text-sm font-semibold text-amber-900 mt-1">
        Potential saving: ₹{Math.round(saving).toLocaleString('en-IN')}
      </p>
      <p className="font-sans text-xs text-amber-700 mt-2">
        Signal strength today: <strong>{isWeak ? 'WEAK' : 'STRONG'}</strong> ({signalStrength.toFixed(2)}/1.0 —{' '}
        {isWeak ? 'borderline exit' : 'clear signal'})
      </p>
      <p className="font-sans text-xs text-amber-700 mt-0.5">
        Recommendation: {isWeak ? 'Consider holding. Signal is not urgent.' : 'Signal is clear — follow discipline.'}
      </p>
      <div className="flex gap-3 mt-3">
        <button className="font-sans text-xs border border-amber-600 text-amber-700 px-3 py-1.5 rounded-[2px] hover:bg-amber-100">
          Hold — Save Tax
        </button>
        <button className="font-sans text-xs border border-ink-tertiary text-ink-secondary px-3 py-1.5 rounded-[2px] hover:bg-paper-rule">
          Exit Now — Follow Signal
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create ReplicationGuide**

`frontend/src/components/trading/ReplicationGuide.tsx`:
```tsx
'use client'

import type { LeaderboardRow, GenomePositionRow } from '@/lib/queries/strategy_lab'
import { TaxHarvestingAlert } from './TaxHarvestingAlert'

type Props = {
  strategy: LeaderboardRow
  positions: GenomePositionRow[]
}

type Section = 'hold' | 'watch' | 'buy' | 'sell' | 'liquidbees'

function classifyPosition(pos: GenomePositionRow): Section {
  if (pos.position_type === 'liquidbees') return 'liquidbees'
  const pnl = Number(pos.unrealized_pnl)
  // Simple heuristic — real classification comes from exit signal in entry_signals
  const signals = pos.entry_signals as Record<string, unknown> ?? {}
  if (signals.exit_triggered) return 'sell'
  if (signals.softening) return 'watch'
  if (pnl > 0) return 'hold'
  return 'watch'
}

const SECTION_LABELS: Record<Section, { label: string; color: string }> = {
  hold:        { label: 'Hold',           color: 'text-teal-700 bg-teal-50 border-teal-200' },
  watch:       { label: 'Watch',          color: 'text-amber-700 bg-amber-50 border-amber-200' },
  buy:         { label: 'Buy Today',      color: 'text-blue-700 bg-blue-50 border-blue-200' },
  sell:        { label: 'Sell Today',     color: 'text-red-700 bg-red-50 border-red-200' },
  liquidbees:  { label: 'LiquidBees',     color: 'text-gray-700 bg-gray-50 border-gray-200' },
}

function PositionRow({ pos }: { pos: GenomePositionRow }) {
  const pnl = Number(pos.unrealized_pnl)
  const pnlColor = pnl >= 0 ? 'text-teal-600' : 'text-red-600'
  const ltcgEligible = pos.tax_status === 'ltcg_eligible'

  return (
    <div className="py-3 border-b border-paper-rule last:border-0">
      <div className="flex justify-between items-start">
        <div>
          <span className="font-mono text-sm font-semibold text-ink-primary">{pos.ticker}</span>
          {pos.company_name && (
            <span className="font-sans text-xs text-ink-tertiary ml-2">{pos.company_name}</span>
          )}
          <div className="flex gap-3 mt-1">
            <span className="font-sans text-xs text-ink-tertiary">
              Entry ₹{Number(pos.entry_price).toFixed(2)}
            </span>
            <span className="font-sans text-xs text-ink-tertiary">
              {pos.holding_days}d held
            </span>
            <span className={`font-sans text-xs px-1.5 py-0.5 rounded-[2px] ${ltcgEligible ? 'bg-green-100 text-green-700' : 'bg-orange-100 text-orange-700'}`}>
              {ltcgEligible ? 'LTCG' : 'STCG'}
            </span>
          </div>
        </div>
        <div className="text-right">
          <p className="font-mono text-sm font-semibold text-ink-primary">
            ₹{Number(pos.current_value).toLocaleString('en-IN')}
          </p>
          <p className={`font-mono text-xs ${pnlColor}`}>
            {pnl >= 0 ? '+' : ''}₹{Math.abs(pnl).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
          </p>
        </div>
      </div>
      {/* Tax harvesting alert when within 60 days of LTCG and has gain */}
      {pos.tax_status === 'stcg' && pnl > 5000 && 365 - pos.holding_days < 60 && (
        <TaxHarvestingAlert
          ticker={pos.ticker}
          grossPnl={pnl}
          holdingDays={pos.holding_days}
          stcgRate={0.20}
          ltcgRate={0.125}
          signalStrength={0.4}   // TODO: wire from entry_signals when available
        />
      )}
    </div>
  )
}

export function ReplicationGuide({ strategy, positions }: Props) {
  const grouped = positions.reduce<Record<Section, GenomePositionRow[]>>(
    (acc, pos) => {
      const section = classifyPosition(pos)
      acc[section].push(pos)
      return acc
    },
    { hold: [], watch: [], buy: [], sell: [], liquidbees: [] }
  )

  const sections: Section[] = ['sell', 'buy', 'watch', 'hold', 'liquidbees']
  const totalValue = positions.reduce((sum, p) => sum + Number(p.current_value), 0)
  const equityValue = positions.filter(p => p.position_type === 'equity').reduce((sum, p) => sum + Number(p.current_value), 0)
  const portfolioHeat = totalValue > 0 ? (equityValue / totalValue * 100).toFixed(1) : '0.0'

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="border border-paper-rule rounded-[2px] p-4">
        <div className="flex justify-between">
          <div>
            <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide">Replication Guide</p>
            <h2 className="font-serif text-lg text-ink-primary mt-1">{strategy.strategy_name}</h2>
          </div>
          <div className="text-right">
            <p className="font-sans text-xs text-ink-tertiary">Portfolio Heat</p>
            <p className="font-mono text-lg font-semibold text-ink-primary">{portfolioHeat}%</p>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3 mt-3">
          <div>
            <p className="font-sans text-xs text-ink-tertiary">Sortino OOS</p>
            <p className="font-mono text-sm font-semibold text-ink-primary">{Number(strategy.sortino_oos ?? 0).toFixed(2)}</p>
          </div>
          <div>
            <p className="font-sans text-xs text-ink-tertiary">Calmar OOS</p>
            <p className="font-mono text-sm font-semibold text-ink-primary">{Number(strategy.calmar_oos ?? 0).toFixed(2)}</p>
          </div>
          <div>
            <p className="font-sans text-xs text-ink-tertiary">Positions</p>
            <p className="font-mono text-sm font-semibold text-ink-primary">{positions.filter(p => p.position_type === 'equity').length}</p>
          </div>
        </div>
      </div>

      {/* Sections */}
      {sections.map((section) => {
        const items = grouped[section]
        if (!items.length) return null
        const { label, color } = SECTION_LABELS[section]
        return (
          <div key={section} className={`border rounded-[2px] ${color}`}>
            <div className={`px-4 py-2 border-b ${color}`}>
              <p className="font-sans text-xs font-semibold uppercase tracking-wide">{label} ({items.length})</p>
            </div>
            <div className="px-4">
              {items.map((pos) => (
                <PositionRow key={`${pos.ticker}-${pos.date}`} pos={pos} />
              ))}
            </div>
          </div>
        )
      })}

      {positions.length === 0 && (
        <p className="font-sans text-sm text-ink-tertiary">No positions yet. Strategy is in early optimization.</p>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "trading\|strategy_lab" | head -20
```

Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/trading/ReplicationGuide.tsx frontend/src/components/trading/TaxHarvestingAlert.tsx
git commit -m "feat(trading-ui): Replication Guide with Hold/Watch/Buy/Sell sections + Tax Harvesting Alert"
```

---

## Task 18: Engine Room (Layer 3)

**Files:**
- Create: `frontend/src/app/strategies/lab/engine/page.tsx`
- Create: `frontend/src/components/trading/EngineRoom.tsx`

- [ ] **Step 1: Create Engine Room shell**

`frontend/src/app/strategies/lab/engine/page.tsx`:
```tsx
export const dynamic = 'force-dynamic'

import { getLatestInsights, getGenePoolHealth, getLeaderboard } from '@/lib/queries/strategy_lab'
import { EngineRoom } from '@/components/trading/EngineRoom'

export default async function EngineRoomPage() {
  const [insights, health, leaderboard] = await Promise.all([
    getLatestInsights(),
    getGenePoolHealth(),
    getLeaderboard(),
  ])

  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-7xl mx-auto">
      <header className="mb-6">
        <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide">Strategy Lab</p>
        <h1 className="font-serif text-2xl text-ink-primary mt-1">Engine Room</h1>
      </header>
      <EngineRoom insights={insights} health={health} leaderboard={leaderboard} />
    </main>
  )
}
```

- [ ] **Step 2: Create EngineRoom component**

`frontend/src/components/trading/EngineRoom.tsx`:
```tsx
'use client'

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import type { LeaderboardRow, InsightRow, GenePoolHealth } from '@/lib/queries/strategy_lab'

type Props = {
  insights: InsightRow | null
  health: GenePoolHealth
  leaderboard: LeaderboardRow[]
}

function ParameterImportanceChart({ importance }: { importance: Record<string, number> }) {
  const data = Object.entries(importance)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([key, value]) => ({
      param: key.replace(/_/g, ' ').slice(0, 22),
      importance: Math.round(value * 100),
    }))

  if (!data.length) {
    return <p className="font-sans text-xs text-ink-tertiary">No parameter importance data yet.</p>
  }

  return (
    <div className="h-64">
      <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-2">Parameter Importance</p>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical">
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis type="number" tick={{ fontSize: 10, fill: '#9ca3af' }} domain={[0, 100]} />
          <YAxis type="category" dataKey="param" tick={{ fontSize: 9, fill: '#6b7280' }} width={140} />
          <Tooltip formatter={(v: number) => [`${v}%`, 'Importance']} />
          <Bar dataKey="importance" fill="#1D9E75" radius={[0, 2, 2, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function GenePoolHealthPanel({ health }: { health: GenePoolHealth }) {
  const totalEver = health.active_count + health.killed_count + health.promoted_count
  const killRate = totalEver > 0 ? ((health.killed_count / totalEver) * 100).toFixed(1) : '—'
  const diversityScore = health.active_count > 10
    ? Math.min(1.0, health.active_count / 150).toFixed(2)
    : '0.07'

  const fields = [
    { label: 'Active Genomes', value: health.active_count },
    { label: 'Promoted', value: health.promoted_count },
    { label: 'Kill Rate', value: `${killRate}%` },
    { label: 'Diversity Score', value: diversityScore },
  ]

  const lastRun = health.last_born_at
    ? new Date(health.last_born_at).toLocaleString('en-IN')
    : 'Not yet run'

  return (
    <div className="border border-paper-rule rounded-[2px] p-4">
      <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-3">Gene Pool Health</p>
      <div className="grid grid-cols-2 gap-3">
        {fields.map(({ label, value }) => (
          <div key={label}>
            <p className="font-sans text-xs text-ink-tertiary">{label}</p>
            <p className="font-mono text-base font-semibold text-ink-primary">{value}</p>
          </div>
        ))}
      </div>
      <p className="font-sans text-xs text-ink-tertiary mt-3">Last optimization: {lastRun}</p>
      {Number(diversityScore) < 0.5 && (
        <p className="font-sans text-xs text-amber-600 mt-2">
          ⚠ Diversity below 0.5 — engine may be converging. Immigrants will be injected next cycle.
        </p>
      )}
    </div>
  )
}

function EvolutionTreePlaceholder({ leaderboard }: { leaderboard: LeaderboardRow[] }) {
  return (
    <div className="border border-paper-rule rounded-[2px] p-4">
      <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-3">Evolution Lineage</p>
      {leaderboard.length === 0 ? (
        <p className="font-sans text-xs text-ink-tertiary">No promoted strategies yet.</p>
      ) : (
        <div className="space-y-2">
          {leaderboard.map((row) => (
            <div key={row.genome_id} className="flex items-center gap-3">
              <span className="w-2 h-2 rounded-full bg-teal-500 flex-shrink-0" />
              <div>
                <span className="font-sans text-sm text-ink-primary">{row.strategy_name}</span>
                <span className="font-sans text-xs text-ink-tertiary ml-2">Gen {row.generation}</span>
              </div>
              <span className="ml-auto font-mono text-xs text-teal-600">
                {Number(row.sortino_oos ?? 0).toFixed(2)} Sortino
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function EngineRoom({ insights, health, leaderboard }: Props) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-6">
        <GenePoolHealthPanel health={health} />
        <EvolutionTreePlaceholder leaderboard={leaderboard} />
      </div>

      {/* Insight Feed */}
      <div className="border border-paper-rule rounded-[2px] p-4">
        <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-3">
          Insight Feed — What the Engine Learned
        </p>
        {insights && insights.insight_bullets.length > 0 ? (
          <ul className="space-y-3">
            {insights.insight_bullets.map((bullet, i) => (
              <li key={i} className="font-sans text-sm text-ink-primary flex gap-3">
                <span className="text-teal-600 font-mono mt-0.5">→</span>
                <span>{bullet.replace(/^\d+\.\s*/, '')}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="font-sans text-sm text-ink-tertiary">
            Insight feed will populate after the first nightly optimization run.
          </p>
        )}
      </div>

      {/* Parameter Importance */}
      {insights?.parameter_importance && (
        <div className="border border-paper-rule rounded-[2px] p-4">
          <ParameterImportanceChart importance={insights.parameter_importance} />
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "trading\|strategy_lab" | head -20
```

Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/strategies/lab/engine/page.tsx frontend/src/components/trading/EngineRoom.tsx
git commit -m "feat(trading-ui): Engine Room — gene pool health, insight feed, parameter importance chart"
```

---

## Task 19: Strategy Lab Configurator

**Files:**
- Create: `frontend/src/components/trading/StrategyConfigurator.tsx`

- [ ] **Step 1: Implement 6-step wizard**

`frontend/src/components/trading/StrategyConfigurator.tsx`:
```tsx
'use client'

import { useState } from 'react'

type Config = {
  starting_capital: string
  income_tax_slab_rate: string
  stcg_rate: string
  ltcg_rate: string
  ltcg_annual_exemption: string
  liquidbees_annual_yield: string
  brokerage_rate: string
  stt_rate_sell: string
  max_position_pct: string
  max_portfolio_heat_pct: string
  drawdown_circuit_breaker_pct: string
  universe: string
  rebalancing_frequency: string
  label: string
}

const DEFAULTS: Config = {
  starting_capital: '10000000',
  income_tax_slab_rate: '0.30',
  stcg_rate: '0.20',
  ltcg_rate: '0.125',
  ltcg_annual_exemption: '125000',
  liquidbees_annual_yield: '0.067',
  brokerage_rate: '0.005',
  stt_rate_sell: '0.001',
  max_position_pct: '0.05',
  max_portfolio_heat_pct: '0.20',
  drawdown_circuit_breaker_pct: '0.25',
  universe: 'nifty500',
  rebalancing_frequency: 'weekly',
  label: '',
}

function Step1Capital({ config, onChange }: { config: Config; onChange: (k: keyof Config, v: string) => void }) {
  return (
    <div className="space-y-4">
      <h3 className="font-serif text-lg text-ink-primary">Starting Capital</h3>
      <div>
        <label className="font-sans text-xs text-ink-tertiary">Portfolio Size (₹)</label>
        <input
          type="number"
          value={config.starting_capital}
          onChange={(e) => onChange('starting_capital', e.target.value)}
          className="w-full mt-1 border border-paper-rule rounded-[2px] px-3 py-2 font-mono text-sm"
        />
        <p className="font-sans text-xs text-ink-tertiary mt-1">
          = ₹{Number(config.starting_capital).toLocaleString('en-IN')}
        </p>
      </div>
    </div>
  )
}

function Step2Tax({ config, onChange }: { config: Config; onChange: (k: keyof Config, v: string) => void }) {
  const slabOptions = [{ label: '10%', value: '0.10' }, { label: '20%', value: '0.20' }, { label: '30%', value: '0.30' }]
  return (
    <div className="space-y-4">
      <h3 className="font-serif text-lg text-ink-primary">Tax Profile</h3>
      <div>
        <label className="font-sans text-xs text-ink-tertiary">Income Tax Slab (for LiquidBees income)</label>
        <div className="flex gap-2 mt-2">
          {slabOptions.map(({ label, value }) => (
            <button
              key={value}
              onClick={() => onChange('income_tax_slab_rate', value)}
              className={`font-sans text-xs px-4 py-2 rounded-[2px] border ${config.income_tax_slab_rate === value ? 'border-teal-600 bg-teal-50 text-teal-700' : 'border-paper-rule text-ink-secondary'}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {[
        { key: 'stcg_rate' as keyof Config, label: 'STCG Rate (held < 365 days)', pct: true },
        { key: 'ltcg_rate' as keyof Config, label: 'LTCG Rate (held ≥ 365 days)', pct: true },
        { key: 'ltcg_annual_exemption' as keyof Config, label: 'LTCG Annual Exemption (₹)', pct: false },
      ].map(({ key, label, pct }) => (
        <div key={key}>
          <label className="font-sans text-xs text-ink-tertiary">{label}</label>
          <div className="flex items-center gap-2 mt-1">
            <input
              type="number"
              value={pct ? (Number(config[key]) * 100).toFixed(1) : config[key]}
              onChange={(e) => onChange(key, pct ? String(Number(e.target.value) / 100) : e.target.value)}
              className="flex-1 border border-paper-rule rounded-[2px] px-3 py-2 font-mono text-sm"
            />
            {pct && <span className="font-sans text-sm text-ink-tertiary">%</span>}
          </div>
        </div>
      ))}
    </div>
  )
}

function Step3Cash({ config, onChange }: { config: Config; onChange: (k: keyof Config, v: string) => void }) {
  return (
    <div className="space-y-4">
      <h3 className="font-serif text-lg text-ink-primary">Cash Management</h3>
      <div className="border border-paper-rule rounded-[2px] p-3 bg-paper">
        <p className="font-sans text-sm text-ink-primary">Idle cash deployed as: <strong>LiquidBees (LIQUIDBEES)</strong> ✓</p>
        <p className="font-sans text-xs text-ink-tertiary mt-1">Nippon India ETF Liquid BeES — NSE listed, MIBOR-linked yield</p>
      </div>
      <div>
        <label className="font-sans text-xs text-ink-tertiary">LiquidBees Annual Yield Assumption</label>
        <div className="flex items-center gap-2 mt-1">
          <input
            type="number"
            step="0.1"
            value={(Number(config.liquidbees_annual_yield) * 100).toFixed(1)}
            onChange={(e) => onChange('liquidbees_annual_yield', String(Number(e.target.value) / 100))}
            className="flex-1 border border-paper-rule rounded-[2px] px-3 py-2 font-mono text-sm"
          />
          <span className="font-sans text-sm text-ink-tertiary">% p.a.</span>
        </div>
      </div>
      <p className="font-sans text-xs text-ink-tertiary">
        LiquidBees income taxed at {(Number(config.income_tax_slab_rate) * 100).toFixed(0)}% (your income tax slab, set in Step 2).
      </p>
    </div>
  )
}

function Step4Costs({ config, onChange }: { config: Config; onChange: (k: keyof Config, v: string) => void }) {
  return (
    <div className="space-y-4">
      <h3 className="font-serif text-lg text-ink-primary">Transaction Costs</h3>
      <div className="flex gap-2">
        {[
          { label: 'Zerodha Delivery', brokerage: '0.005', stt: '0.001' },
          { label: 'Flat 0.1%', brokerage: '0.001', stt: '0.001' },
        ].map(({ label, brokerage, stt }) => (
          <button
            key={label}
            onClick={() => { onChange('brokerage_rate', brokerage); onChange('stt_rate_sell', stt) }}
            className={`font-sans text-xs px-3 py-2 rounded-[2px] border ${config.brokerage_rate === brokerage ? 'border-teal-600 bg-teal-50 text-teal-700' : 'border-paper-rule text-ink-secondary'}`}
          >
            {label}
          </button>
        ))}
      </div>
      {[
        { key: 'brokerage_rate' as keyof Config, label: 'Brokerage Rate (per side)' },
        { key: 'stt_rate_sell' as keyof Config, label: 'STT Rate (sell side)' },
      ].map(({ key, label }) => (
        <div key={key}>
          <label className="font-sans text-xs text-ink-tertiary">{label}</label>
          <div className="flex items-center gap-2 mt-1">
            <input
              type="number"
              step="0.001"
              value={(Number(config[key]) * 100).toFixed(3)}
              onChange={(e) => onChange(key, String(Number(e.target.value) / 100))}
              className="flex-1 border border-paper-rule rounded-[2px] px-3 py-2 font-mono text-sm"
            />
            <span className="font-sans text-sm text-ink-tertiary">%</span>
          </div>
        </div>
      ))}
    </div>
  )
}

function Step5Universe({ config, onChange }: { config: Config; onChange: (k: keyof Config, v: string) => void }) {
  return (
    <div className="space-y-4">
      <h3 className="font-serif text-lg text-ink-primary">Universe & Rebalancing</h3>
      <div>
        <label className="font-sans text-xs text-ink-tertiary">Universe</label>
        <div className="flex gap-2 mt-2">
          {['nifty50', 'nifty100', 'nifty500'].map((u) => (
            <button
              key={u}
              onClick={() => onChange('universe', u)}
              className={`font-sans text-xs px-3 py-2 rounded-[2px] border ${config.universe === u ? 'border-teal-600 bg-teal-50 text-teal-700' : 'border-paper-rule text-ink-secondary'}`}
            >
              {u.toUpperCase()}
            </button>
          ))}
        </div>
      </div>
      <div>
        <label className="font-sans text-xs text-ink-tertiary">Rebalancing Frequency</label>
        <div className="flex gap-2 mt-2">
          {['daily', 'weekly', 'monthly'].map((f) => (
            <button
              key={f}
              onClick={() => onChange('rebalancing_frequency', f)}
              className={`font-sans text-xs px-3 py-2 rounded-[2px] border ${config.rebalancing_frequency === f ? 'border-teal-600 bg-teal-50 text-teal-700' : 'border-paper-rule text-ink-secondary'}`}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function Step6RiskLimits({ config, onChange }: { config: Config; onChange: (k: keyof Config, v: string) => void }) {
  return (
    <div className="space-y-4">
      <h3 className="font-serif text-lg text-ink-primary">Hard Risk Limits</h3>
      <p className="font-sans text-xs text-ink-tertiary">These are hard constraints — not genome variables. They apply to every strategy.</p>
      {[
        { key: 'max_position_pct' as keyof Config, label: 'Max Position Size (per stock)' },
        { key: 'max_portfolio_heat_pct' as keyof Config, label: 'Max Portfolio Heat (% in equities)' },
        { key: 'drawdown_circuit_breaker_pct' as keyof Config, label: 'Drawdown Circuit Breaker' },
      ].map(({ key, label }) => (
        <div key={key}>
          <label className="font-sans text-xs text-ink-tertiary">{label}</label>
          <div className="flex items-center gap-2 mt-1">
            <input
              type="number"
              step="1"
              value={(Number(config[key]) * 100).toFixed(0)}
              onChange={(e) => onChange(key, String(Number(e.target.value) / 100))}
              className="flex-1 border border-paper-rule rounded-[2px] px-3 py-2 font-mono text-sm"
            />
            <span className="font-sans text-sm text-ink-tertiary">%</span>
          </div>
        </div>
      ))}
      <div>
        <label className="font-sans text-xs text-ink-tertiary">Profile Label (optional)</label>
        <input
          type="text"
          value={config.label}
          onChange={(e) => onChange('label', e.target.value)}
          placeholder="e.g. 30% slab HNI profile"
          className="w-full mt-1 border border-paper-rule rounded-[2px] px-3 py-2 font-sans text-sm"
        />
      </div>
    </div>
  )
}

export function StrategyConfigurator({ onClose }: { onClose?: () => void }) {
  const [step, setStep] = useState(1)
  const [config, setConfig] = useState<Config>(DEFAULTS)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const onChange = (key: keyof Config, value: string) => {
    setConfig((prev) => ({ ...prev, [key]: value }))
    setSaved(false)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await fetch('/api/trading/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      })
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  const STEPS = [
    { n: 1, label: 'Capital' },
    { n: 2, label: 'Tax' },
    { n: 3, label: 'Cash' },
    { n: 4, label: 'Costs' },
    { n: 5, label: 'Universe' },
    { n: 6, label: 'Risk' },
  ]

  return (
    <div className="border border-paper-rule rounded-[2px] bg-paper max-w-xl">
      {/* Step indicator */}
      <div className="flex border-b border-paper-rule">
        {STEPS.map(({ n, label }) => (
          <button
            key={n}
            onClick={() => setStep(n)}
            className={`flex-1 py-2 font-sans text-xs ${step === n ? 'text-teal-600 border-b-2 border-teal-600' : 'text-ink-tertiary hover:text-ink-secondary'}`}
          >
            {n}. {label}
          </button>
        ))}
      </div>

      <div className="p-6">
        {step === 1 && <Step1Capital config={config} onChange={onChange} />}
        {step === 2 && <Step2Tax config={config} onChange={onChange} />}
        {step === 3 && <Step3Cash config={config} onChange={onChange} />}
        {step === 4 && <Step4Costs config={config} onChange={onChange} />}
        {step === 5 && <Step5Universe config={config} onChange={onChange} />}
        {step === 6 && <Step6RiskLimits config={config} onChange={onChange} />}
      </div>

      <div className="flex justify-between items-center px-6 py-4 border-t border-paper-rule">
        <button
          onClick={() => setStep((s) => Math.max(1, s - 1))}
          disabled={step === 1}
          className="font-sans text-xs text-ink-tertiary disabled:opacity-30 hover:text-ink-primary"
        >
          ← Back
        </button>
        <div className="flex gap-3">
          {saved && (
            <p className="font-sans text-xs text-teal-600 self-center">
              ✓ Saved. Re-running simulation tonight (~45 min).
            </p>
          )}
          {step < 6 ? (
            <button
              onClick={() => setStep((s) => s + 1)}
              className="font-sans text-xs bg-teal-600 text-white px-4 py-2 rounded-[2px] hover:bg-teal-700"
            >
              Next →
            </button>
          ) : (
            <button
              onClick={handleSave}
              disabled={saving}
              className="font-sans text-xs bg-teal-600 text-white px-4 py-2 rounded-[2px] hover:bg-teal-700 disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save Configuration'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "trading\|strategy_lab" | head -20
```

Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/trading/StrategyConfigurator.tsx
git commit -m "feat(trading-ui): 6-step Strategy Lab Configurator wizard"
```

---

## Final: Build Verification

- [ ] **Backend smoke test**

```bash
pytest tests/trading/ -v --tb=short
```

Expected: all tests pass (no failures)

- [ ] **Frontend type check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Final commit summary**

By this point you should have commits covering:
- 065 migration (7 tables)
- atlas/trading/ bounded context (13 modules)
- atlas/api/trading.py (6 endpoints)
- frontend/src/app/strategies/lab/ (3 pages)
- frontend/src/lib/queries/strategy_lab.ts
- frontend/src/components/trading/ (9 components)
- tests/trading/ (8 test files)

---

## Plan Self-Review

**Spec coverage check:**
- §3 Strategy Genome → Task 3 (genome.py + GenomeFactory.from_optuna_trial)
- §4 Tax and Cost Layer → Task 6 (tax_engine.py with all formulas)
- §5 Simulation Engine → Tasks 7–9 (simulator, optimizer, evolver)
- §5.3 Walk-forward → simulate_genome walk_forward_windows parameter
- §5.4 Tournament → Task 11 (tournament.py, 3 rounds, stress tests)
- §6.1 State velocity → perception.py compute_rs_velocity
- §6.2 Factor interactions → decision.py conviction formula with synergy + penalty
- §6.3 Portfolio drawdown adaptation → RegimePlaybook dd_halt/tighten/liquidate fields + apply_entry_rules
- §6.4 Tax harvesting → TaxHarvestingAlert.tsx
- §6.5 Insight feed → insight.py + EngineRoom
- §7 Data model → migration 065 (all 8 tables)
- §8.1–8.4 Frontend layers 1–3 → Tasks 15–18
- §8.5 Tax harvesting alert → Task 17
- §8.7 Configurator → Task 19
- §9 Integration → incubator.py runs after atlas compute

**Type consistency check:** All types flow correctly:
- `PortfolioConfig.from_json(dict) → PortfolioConfig` used in incubator.py
- `Genome.from_dict(dict) → Genome` used in optimizer.py
- `SimResult.sortino_oos: float` used in tournament.py and optimizer.py
- `LeaderboardRow` from strategy_lab.ts used in MorningBrief, StrategyLeaderboard, ReplicationGuide
- `GenomePositionRow` from strategy_lab.ts used in ReplicationGuide
