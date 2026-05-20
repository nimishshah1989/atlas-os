import { TrendingUp, TrendingDown, AlertTriangle, Activity, ChevronRight, Flame, Info } from 'lucide-react'
import { SignalGauge } from './SignalGauge'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { TOOLTIPS } from '@/lib/tooltips'
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

// All four regimes in their natural progression from risk-on to risk-off
const ALL_REGIMES = [
  {
    state: 'Risk-On',
    accentColor: '#22c55e',
    deployPct: 100,
    logic: 'All 4 pillars confirmed: trend up, breadth expanding, momentum positive, participation broad. Full deployment — no reason to hold back.',
  },
  {
    state: 'Constructive',
    accentColor: '#14b8a6',
    deployPct: 80,
    logic: 'Strong on 3 of 4 pillars. Positive trend with breadth support, but momentum or participation not fully confirmed. 80% lets you participate while reserving dry powder.',
  },
  {
    state: 'Cautious',
    accentColor: '#f59e0b',
    deployPct: 60,
    logic: 'Mixed signals — at least 2 of 4 pillars are deteriorating. Breadth narrowing or VIX elevated. 60% preserves capital while staying engaged in leading sectors.',
  },
  {
    state: 'Risk-Off',
    accentColor: '#ef4444',
    deployPct: 40,
    logic: 'Broad deterioration across trend, breadth, and momentum. Capital preservation takes priority. 40% keeps minimal exposure for opportunistic positions only.',
  },
] as const

function RegimeStateStrip({ currentState }: { currentState: string }) {
  return (
    <div className="flex items-center gap-2 mb-5 flex-wrap">
      {ALL_REGIMES.map((r) => {
        const isCurrent = r.state === currentState
        return (
          <div key={r.state} className="flex items-center gap-1.5 group relative">
            <div
              className={
                'inline-flex items-center gap-2 px-3 py-1.5 rounded-[3px] border transition-all ' +
                (isCurrent
                  ? 'border-current shadow-sm'
                  : 'border-paper-rule bg-paper-rule/10 opacity-45')
              }
              style={isCurrent ? { borderColor: r.accentColor, backgroundColor: `${r.accentColor}12` } : {}}
            >
              <span
                className="font-sans text-[11px] font-semibold"
                style={{ color: isCurrent ? r.accentColor : '#8C8278' }}
              >
                {r.state}
              </span>
              <span
                className="font-mono text-[10px] tabular-nums"
                style={{ color: isCurrent ? r.accentColor : '#8C8278', opacity: 0.8 }}
              >
                {r.deployPct}%
              </span>
            </div>
            {!isCurrent && (
              <div className="hidden group-hover:block absolute left-0 top-full mt-1.5 z-50 w-64 px-3 py-2.5 bg-paper border border-paper-rule rounded-sm shadow-md font-sans text-[11px] text-ink-secondary leading-relaxed pointer-events-none">
                <span className="font-semibold text-ink-primary block mb-1">{r.state} — {r.deployPct}% deployed</span>
                {r.logic}
              </div>
            )}
          </div>
        )
      })}
      <span
        className="ml-1 inline-flex items-center text-ink-tertiary cursor-help"
        title="Deployment % = the recommended fraction of your equity allocation to deploy in equities. Derived from which of the 4 pillars (Trend, Breadth, Momentum, Participation) are confirmed. Each confirmed pillar shifts the multiplier. Hover each regime for the specific logic."
      >
        <Info className="w-3 h-3" />
      </span>
    </div>
  )
}

export function RegimeHeadline({ regime }: Props) {
  const vix        = regime.india_vix ? parseFloat(regime.india_vix).toFixed(1) : null
  const deployment = parseFloat(regime.deployment_multiplier)
  const deployPct  = Math.round(deployment * 100)
  const tintClass  = getRegimeTintClass(regime.regime_state)
  const accentClass = getRegimeAccentClass(regime.regime_state)
  const description = getRegimeDescription(regime)
  const action      = getRegimeAction(regime.regime_state, deployment)
  const scores      = getCategoryScores(regime)

  // Handle dislocation state from DB (may be an enum like DISLOCATION_SUSPENDED)
  const rawDislocationState: string | null = (regime as unknown as Record<string, string | null>).dislocation_state ?? null
  const dislocationLabel = rawDislocationState
    ? rawDislocationState
        .toLowerCase()
        .replace(/_/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase())
    : null

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
          <h1
            className={`font-serif text-5xl font-semibold leading-none tracking-tight ${accentClass}`}
            data-validator-id={`regime.regime_state:${regime.date instanceof Date ? regime.date.toISOString().split('T')[0] : String(regime.date)}`}
          >
            {regime.regime_state}
          </h1>
          {regime.dislocation_active && (
            <span
              className="self-center inline-flex items-center gap-1.5 px-2 py-0.5 text-[11px] font-sans font-medium text-signal-neg border border-signal-neg/40 rounded-[2px] bg-signal-neg/5"
              title={dislocationLabel ? `Dislocation state: ${dislocationLabel}. This means breadth has collapsed beyond normal regime thresholds — risk of cascade declines is elevated. Deployment multiplier is reduced automatically.` : 'Market breadth has collapsed beyond normal regime thresholds. Elevated risk — deployment reduced.'}
            >
              {dislocationLabel ?? 'Dislocation active'}
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

      {/* Row 3 — all regime state pills (current highlighted, others dimmed) */}
      <div className="ml-11">
        <RegimeStateStrip currentState={regime.regime_state} />
      </div>

      {/* Row 4 — four signal gauges (one per category) */}
      <div className="ml-11 mb-5">
        <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-2">
          4-State Classifier — Signal Inputs
        </div>
      <div className="flex items-center gap-8 flex-wrap">
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
      </div>

      {/* Row 5 — action + key stats */}
      <div className="ml-11 flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-sm font-sans text-ink-secondary">
          <ChevronRight className="w-3.5 h-3.5 text-ink-tertiary flex-shrink-0" />
          <span className="font-medium">{action}</span>
        </div>
        <div className="flex items-center gap-5 font-mono text-xs tabular-nums text-ink-tertiary">
          {vix && (
            <span
              className="inline-flex items-center gap-1"
              data-validator-id={`regime.india_vix:${regime.date instanceof Date ? regime.date.toISOString().split('T')[0] : String(regime.date)}`}
              data-validator-raw={regime.india_vix ?? ''}
            >
              VIX{' '}
              <span className={`font-medium ${parseFloat(vix) > 25 ? 'text-signal-neg' : parseFloat(vix) > 18 ? 'text-signal-warn' : 'text-ink-primary'}`}>
                {vix}
              </span>
              <InfoTooltip content={TOOLTIPS.india_vix} />
            </span>
          )}
          <span
            data-validator-id={`regime.deployment_multiplier:${regime.date instanceof Date ? regime.date.toISOString().split('T')[0] : String(regime.date)}`}
            data-validator-raw={regime.deployment_multiplier}
          >
            Deploy{' '}
            <span className="font-medium text-ink-primary">{deployPct}%</span>
          </span>
        </div>
      </div>
    </div>
  )
}
