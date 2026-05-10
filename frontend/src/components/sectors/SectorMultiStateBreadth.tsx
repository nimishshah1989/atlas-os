'use client'
// allow-large: 4 state-dimension breadth charts each with legend — cohesive unit
import type { StockRow } from '@/lib/queries/sector-deep-dive'
import { Info } from 'lucide-react'

type StateDef = { label: string; color: string; bull: boolean; tip: string }

const MOMENTUM_STATES: StateDef[] = [
  { label: 'Accelerating', color: '#16a34a', bull: true,  tip: 'RS rising fast — stock gaining ground vs index at an accelerating rate. Strongest momentum signal.' },
  { label: 'Improving',    color: '#22c55e', bull: true,  tip: 'RS rising steadily — stock gaining vs index, momentum positive but not yet accelerating.' },
  { label: 'Flat',         color: '#94a3b8', bull: false, tip: 'RS stable — no meaningful change in relative strength over the past few weeks.' },
  { label: 'Deteriorating',color: '#f59e0b', bull: false, tip: 'RS falling — stock losing ground vs index. Early warning; watch for trend change.' },
  { label: 'Collapsing',   color: '#ef4444', bull: false, tip: 'RS falling sharply — stock in rapid underperformance vs index. Avoid or exit.' },
]

const RISK_STATES: StateDef[] = [
  { label: 'Low',         color: '#16a34a', bull: true,  tip: 'Stock not extended; price near or below key moving averages with low volatility. Safe to add.' },
  { label: 'Normal',      color: '#1D9E75', bull: true,  tip: 'Normal positioning — stock above trend but not overextended. Standard risk-reward.' },
  { label: 'Elevated',    color: '#f59e0b', bull: false, tip: 'Stock extended above moving averages or volatility rising. Higher drawdown risk if market turns.' },
  { label: 'High',        color: '#ef4444', bull: false, tip: 'Significantly overextended or high volatility. Wait for a pullback before adding.' },
  { label: 'Below Trend', color: '#7c2d12', bull: false, tip: 'Stock below key trend lines — in a downtrend. Capital destruction mode; avoid new positions.' },
]

const VOLUME_STATES: StateDef[] = [
  { label: 'Accumulation',      color: '#16a34a', bull: true,  tip: 'Volume skewing heavily to up-days — institutional buying. Strong sign of underlying demand.' },
  { label: 'Steady-Buying',     color: '#22c55e', bull: true,  tip: 'Consistent buying pressure — volume positive but not at accumulation intensity.' },
  { label: 'Neutral',           color: '#94a3b8', bull: false, tip: 'Volume roughly balanced between up-days and down-days. No clear institutional direction.' },
  { label: 'Distribution',      color: '#f59e0b', bull: false, tip: 'Volume skewing to down-days — institutional selling. Caution warranted.' },
  { label: 'Heavy Distribution',color: '#ef4444', bull: false, tip: 'Elevated volume on down-days — aggressive institutional selling. Exit or reduce positions.' },
]

function BreadthBar({
  title,
  titleTip,
  states,
  field,
  stocks,
}: {
  title: string
  titleTip: string
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
        <span className="flex items-center gap-1 font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">
          {title}
          <span title={titleTip}>
            <Info className="w-2.5 h-2.5 opacity-60 cursor-help" />
          </span>
        </span>
        <span
          className="font-mono text-[10px] font-semibold"
          style={{ color: bullPct >= 60 ? '#16a34a' : bullPct >= 40 ? '#f59e0b' : '#ef4444' }}
          title={`${bullPct}% of stocks have constructive ${title.toLowerCase()} states. Above 60% = broad strength. Below 40% = broad weakness.`}
        >
          {bullPct}% constructive
        </span>
      </div>
      <div className="flex h-2.5 rounded-sm overflow-hidden gap-px">
        {counts.map(({ label, color, count, tip }) => (
          <div
            key={label}
            style={{ width: `${(count / total) * 100}%`, background: color }}
            title={`${label}: ${count} stocks (${Math.round((count / total) * 100)}%) — ${tip}`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        {counts.map(({ label, color, count, tip }) => (
          <span key={label} className="inline-flex items-center gap-1 font-sans text-[9px] text-ink-tertiary" title={tip}>
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
          <BreadthBar
            title="Momentum"
            titleTip="Distribution of RS momentum states across sector stocks. Momentum = direction of change in each stock's relative strength vs Nifty 500. High 'constructive' % means most stocks are gaining ground vs market — a leading indicator of sector strength."
            states={MOMENTUM_STATES}
            field="momentum_state"
            stocks={stocks}
          />
        )}
        {hasRisk && (
          <BreadthBar
            title="Risk"
            titleTip="Distribution of risk states across sector stocks. Risk = combination of extension above moving averages, historical volatility, and recent drawdown. High 'constructive' % means stocks are well-positioned without overextension — lower risk of sudden correction."
            states={RISK_STATES}
            field="risk_state"
            stocks={stocks}
          />
        )}
        {hasVolume && (
          <BreadthBar
            title="Volume"
            titleTip="Distribution of volume states across sector stocks. Volume state = balance of buying vs selling pressure based on up-day vs down-day volume. High 'constructive' % means institutional money is flowing in — Accumulation and Steady-Buying states confirm underlying demand."
            states={VOLUME_STATES}
            field="volume_state"
            stocks={stocks}
          />
        )}
      </div>
    </div>
  )
}
