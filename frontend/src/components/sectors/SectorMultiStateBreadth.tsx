'use client'
// allow-large: 4 state-dimension breadth charts each with legend — cohesive unit
import type { StockRow } from '@/lib/queries/sector-deep-dive'

type StateDef = { label: string; color: string; bull: boolean }

const MOMENTUM_STATES: StateDef[] = [
  { label: 'Accelerating', color: '#16a34a', bull: true },
  { label: 'Improving',    color: '#22c55e', bull: true },
  { label: 'Flat',         color: '#94a3b8', bull: false },
  { label: 'Deteriorating',color: '#f59e0b', bull: false },
  { label: 'Collapsing',   color: '#ef4444', bull: false },
]

const RISK_STATES: StateDef[] = [
  { label: 'Low',          color: '#16a34a', bull: true },
  { label: 'Normal',       color: '#1D9E75', bull: true },
  { label: 'Elevated',     color: '#f59e0b', bull: false },
  { label: 'High',         color: '#ef4444', bull: false },
  { label: 'Below Trend',  color: '#7c2d12', bull: false },
]

const VOLUME_STATES: StateDef[] = [
  { label: 'Accumulation',      color: '#16a34a', bull: true },
  { label: 'Steady-Buying',     color: '#22c55e', bull: true },
  { label: 'Neutral',           color: '#94a3b8', bull: false },
  { label: 'Distribution',      color: '#f59e0b', bull: false },
  { label: 'Heavy Distribution',color: '#ef4444', bull: false },
]

function BreadthBar({
  title,
  states,
  field,
  stocks,
}: {
  title: string
  states: StateDef[]
  field: 'momentum_state' | 'risk_state' | 'volume_state'
  stocks: StockRow[]
}) {
  const total = stocks.length
  if (total === 0) return null

  const counts = states.map(s => ({
    ...s,
    count: stocks.filter(st => st[field] === s.label).length,
  })).filter(x => x.count > 0)

  const bullCount = counts.filter(x => x.bull).reduce((a, b) => a + b.count, 0)
  const bullPct = Math.round((bullCount / total) * 100)

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <span className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">{title}</span>
        <span
          className="font-mono text-[10px] font-semibold"
          style={{ color: bullPct >= 60 ? '#16a34a' : bullPct >= 40 ? '#f59e0b' : '#ef4444' }}
        >
          {bullPct}% constructive
        </span>
      </div>
      <div className="flex h-2.5 rounded-sm overflow-hidden gap-px">
        {counts.map(({ label, color, count }) => (
          <div
            key={label}
            style={{ width: `${(count / total) * 100}%`, background: color }}
            title={`${label}: ${count} stocks (${Math.round((count / total) * 100)}%)`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        {counts.map(({ label, color, count }) => (
          <span key={label} className="inline-flex items-center gap-1 font-sans text-[9px] text-ink-tertiary">
            <span className="inline-block w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: color }} />
            {label}
            <span className="font-mono">{count}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

export function SectorMultiStateBreadth({ stocks }: { stocks: StockRow[] }) {
  if (stocks.length === 0) return null

  const hasMomentum = stocks.some(s => s.momentum_state != null)
  const hasRisk     = stocks.some(s => s.risk_state != null)
  const hasVolume   = stocks.some(s => s.volume_state != null)

  if (!hasMomentum && !hasRisk && !hasVolume) return null

  return (
    <div className="space-y-3 pt-3 border-t border-paper-rule">
      <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">
        Multi-Dimension State Breadth — {stocks.length} stocks
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {hasMomentum && (
          <BreadthBar title="Momentum" states={MOMENTUM_STATES} field="momentum_state" stocks={stocks} />
        )}
        {hasRisk && (
          <BreadthBar title="Risk" states={RISK_STATES} field="risk_state" stocks={stocks} />
        )}
        {hasVolume && (
          <BreadthBar title="Volume" states={VOLUME_STATES} field="volume_state" stocks={stocks} />
        )}
      </div>
    </div>
  )
}
