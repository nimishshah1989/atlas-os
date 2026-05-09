import { TrendingUp, TrendingDown, AlertTriangle, Activity, ChevronRight, Flame } from 'lucide-react'
import { SignalGauge } from './SignalGauge'
import {
  getRegimeTintClass,
  getRegimeAccentClass,
  getRegimeDescription,
  getRegimeAction,
  getCategoryScores,
} from '@/lib/regime-narrative'
import type { MarketRegimeRow } from '@/lib/queries/regime'

type Props = {
  regime: MarketRegimeRow
}

function RegimeIcon({ state, className }: { state: string; className?: string }) {
  const cls = className ?? 'w-8 h-8'
  if (state === 'Risk-On')      return <TrendingUp className={cls} strokeWidth={2} />
  if (state === 'Constructive') return <Flame className={cls} strokeWidth={2} />
  if (state === 'Risk-Off')     return <TrendingDown className={cls} strokeWidth={2} />
  if (state === 'Cautious')     return <AlertTriangle className={cls} strokeWidth={2} />
  return <Activity className={cls} strokeWidth={2} />
}

const CATEGORY_LABELS = [
  { key: 'trend',         label: 'Trend' },
  { key: 'breadth',       label: 'Breadth' },
  { key: 'momentum',      label: 'Momentum' },
  { key: 'participation', label: 'Participation' },
] as const

export function RegimeHeadline({ regime }: Props) {
  const vix        = regime.india_vix ? parseFloat(regime.india_vix).toFixed(1) : null
  const deployment = parseFloat(regime.deployment_multiplier)
  const deployPct  = Math.round(deployment * 100)
  const tintClass  = getRegimeTintClass(regime.regime_state)
  const accentClass = getRegimeAccentClass(regime.regime_state)
  const description = getRegimeDescription(regime)
  const action      = getRegimeAction(regime.regime_state, deployment)
  const scores      = getCategoryScores(regime)

  const dataAsOf = regime.date instanceof Date
    ? regime.date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
    : String(regime.date)

  return (
    <div className={`px-6 pt-7 pb-6 border-b ${tintClass}`}>
      {/* Row 1 — state name + dislocation + date */}
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-3">
          <RegimeIcon
            state={regime.regime_state}
            className={`w-8 h-8 flex-shrink-0 ${accentClass}`}
          />
          <h1 className={`font-serif text-5xl font-semibold leading-none tracking-tight ${accentClass}`}>
            {regime.regime_state}
          </h1>
          {regime.dislocation_active && (
            <span className="self-center inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-sans font-medium text-signal-neg border border-signal-neg/40 rounded-[2px] bg-signal-neg/5">
              Dislocation active
              {regime.dislocation_started && (
                <span className="text-signal-neg/60 font-normal">
                  since {new Date(regime.dislocation_started).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}
                </span>
              )}
            </span>
          )}
        </div>
        <span className="font-sans text-xs text-ink-tertiary pt-1">Data as of {dataAsOf}</span>
      </div>

      {/* Row 2 — data-driven description */}
      <p className="font-sans text-sm text-ink-secondary ml-11 mb-5 max-w-3xl leading-relaxed">
        {description}
      </p>

      {/* Row 3 — four signal gauges (one per category) */}
      <div className="ml-11 flex items-center gap-8 mb-5 flex-wrap">
        {CATEGORY_LABELS.map(({ key, label }) => (
          <div key={key} className="flex items-center gap-2.5">
            <span className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wider w-[88px]">
              {label}
            </span>
            <SignalGauge
              bullish={scores[key].bullish}
              total={scores[key].total}
            />
          </div>
        ))}
      </div>

      {/* Row 4 — action + key stats */}
      <div className="ml-11 flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-sm font-sans text-ink-secondary">
          <ChevronRight className="w-3.5 h-3.5 text-ink-tertiary flex-shrink-0" />
          <span className="font-medium">{action}</span>
        </div>
        <div className="flex items-center gap-5 font-mono text-xs tabular-nums text-ink-tertiary">
          {vix && (
            <span>
              VIX{' '}
              <span className={`font-medium ${parseFloat(vix) > 25 ? 'text-signal-neg' : parseFloat(vix) > 18 ? 'text-signal-warn' : 'text-ink-primary'}`}>
                {vix}
              </span>
            </span>
          )}
          <span>
            Deploy{' '}
            <span className="font-medium text-ink-primary">{deployPct}%</span>
          </span>
        </div>
      </div>
    </div>
  )
}
