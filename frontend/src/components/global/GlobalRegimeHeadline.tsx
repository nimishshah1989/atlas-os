'use client'
import { TrendingUp, TrendingDown, AlertTriangle, Activity, ChevronRight, Info } from 'lucide-react'
import { SignalGauge } from '@/components/regime/SignalGauge'
import type { GlobalRegimeRow, CountryRow } from '@/lib/queries/global'

type Props = {
  regime: GlobalRegimeRow
  countries: CountryRow[]
}

const f = (s: string | null | undefined): number => (s == null ? 0 : parseFloat(s))

function getAccentColor(state: string | null): string {
  if (state === 'Strong')  return '#22c55e'
  if (state === 'Healthy') return '#14b8a6'
  if (state === 'Caution') return '#f59e0b'
  if (state === 'Weak')    return '#ef4444'
  return '#94a3b8'
}

function getAccentClass(state: string | null): string {
  if (state === 'Strong')  return 'text-signal-pos'
  if (state === 'Healthy') return 'text-teal-500'
  if (state === 'Caution') return 'text-amber-500'
  if (state === 'Weak')    return 'text-signal-neg'
  return 'text-ink-tertiary'
}

function getTintClass(state: string | null): string {
  if (state === 'Strong')  return 'bg-signal-pos/5 border-signal-pos/20'
  if (state === 'Healthy') return 'bg-teal-500/5 border-teal-500/20'
  if (state === 'Caution') return 'bg-amber-500/5 border-amber-500/20'
  if (state === 'Weak')    return 'bg-signal-neg/5 border-signal-neg/20'
  return 'bg-paper border-paper-rule'
}

function RegimeIcon({ state, className }: { state: string | null; className?: string }) {
  const cls = className ?? 'w-8 h-8'
  if (state === 'Strong')  return <TrendingUp className={cls} strokeWidth={2} />
  if (state === 'Healthy') return <Activity className={cls} strokeWidth={2} />
  if (state === 'Caution') return <AlertTriangle className={cls} strokeWidth={2} />
  if (state === 'Weak')    return <TrendingDown className={cls} strokeWidth={2} />
  return <Activity className={cls} strokeWidth={2} />
}

const ALL_REGIMES = [
  {
    state: 'Strong',
    accentColor: '#22c55e',
    deployPct: 100,
    logic: 'All 4 pillars confirmed: VT benchmark in uptrend, majority of countries above key MAs, momentum positive, participation broad. Full deployment.',
  },
  {
    state: 'Healthy',
    accentColor: '#14b8a6',
    deployPct: 75,
    logic: '3 of 4 pillars positive. Global trend intact with breadth support, but momentum or participation not fully confirmed. 75% lets you participate while maintaining dry powder.',
  },
  {
    state: 'Caution',
    accentColor: '#f59e0b',
    deployPct: 50,
    logic: 'Mixed signals — at least 2 of 4 pillars are deteriorating. Country breadth narrowing or vol elevated. 50% preserves capital while staying engaged in strongest regions.',
  },
  {
    state: 'Weak',
    accentColor: '#ef4444',
    deployPct: 25,
    logic: 'Broad deterioration across global trend, breadth, and momentum. Capital preservation takes priority. 25% keeps minimal exposure for opportunistic positions only.',
  },
] as const

function RegimeStateStrip({ currentState }: { currentState: string | null }) {
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
        title="Deployment % = recommended fraction of global equity allocation. Derived from which of the 4 pillars (Trend, Breadth, Momentum, Participation) are confirmed. Hover each regime for the specific logic."
      >
        <Info className="w-3 h-3" />
      </span>
    </div>
  )
}

function computePillars(regime: GlobalRegimeRow, countries: CountryRow[]) {
  const ema50Slope  = f(regime.benchmark_ema_50_slope)
  const ema200Slope = f(regime.benchmark_ema_200_slope)

  // Trend: 4 signals
  const trend = [
    regime.benchmark_above_ema_50 === true,
    regime.benchmark_above_ema_200 === true,
    ema50Slope > 0,
    ema200Slope > 0,
  ]

  // Breadth: 3 signals from pct data + Q distribution
  const pct50  = f(regime.pct_countries_above_50dma)
  const pct200 = f(regime.pct_countries_above_200dma)
  const total  = countries.length || 1
  const q1q2Count = countries.filter((c) => (c.q_3m_vt ?? 99) <= 2).length
  const breadth = [
    pct50  > 0.5,
    pct200 > 0.5,
    q1q2Count / total > 0.4,
  ]

  // Momentum: 3 signals from country data
  const bullishCountries = countries.filter((c) => (c.rs_consensus_bullish ?? 0) > 10).length
  const dmCountries = countries.filter((c) => c.is_developed_market)
  const emCountries = countries.filter((c) => !c.is_developed_market)
  const dmAvgQ = dmCountries.length > 0
    ? dmCountries.reduce((s, c) => s + (c.q_3m_vt ?? 3), 0) / dmCountries.length
    : 3
  const emAvgQ = emCountries.length > 0
    ? emCountries.reduce((s, c) => s + (c.q_3m_vt ?? 3), 0) / emCountries.length
    : 3
  const momentum = [
    bullishCountries / total > 0.5,
    dmAvgQ < 3,
    emAvgQ < 3,
  ]

  // Participation: 2 signals
  const aboveMACount = countries.filter((c) => c.above_30w_ma === true).length
  const maDenominator = countries.filter((c) => c.above_30w_ma !== null).length || 1
  const participation = [
    q1q2Count / total > 0.35,
    aboveMACount / maDenominator > 0.5,
  ]

  const count = (arr: boolean[]) => arr.filter(Boolean).length
  return {
    trend:         { bullish: count(trend),         total: trend.length },
    breadth:       { bullish: count(breadth),        total: breadth.length },
    momentum:      { bullish: count(momentum),       total: momentum.length },
    participation: { bullish: count(participation),  total: participation.length },
  }
}

function buildDescription(regime: GlobalRegimeRow, countries: CountryRow[]): string {
  const pct50  = f(regime.pct_countries_above_50dma)
  const pct200 = f(regime.pct_countries_above_200dma)
  const vol    = f(regime.realized_vol_5d)
  const volMed = f(regime.vol_252_median)
  const total  = countries.length

  const vtTrend = regime.benchmark_above_ema_50 ? 'above' : 'below'
  const pct50Str  = `${Math.round(pct50 * 100)}%`
  const pct200Str = `${Math.round(pct200 * 100)}%`
  const volNote = vol > volMed * 1.3
    ? ` Realized vol (${(vol * 100).toFixed(1)}%) is elevated vs 252-day median (${(volMed * 100).toFixed(1)}%).`
    : ` Volatility is contained at ${(vol * 100).toFixed(1)}%.`

  return (
    `VT (World ETF) is ${vtTrend} its 50-day EMA. ` +
    `${pct50Str} of ${total} country ETFs are above their 50-day MA and ${pct200Str} above the 200-day.` +
    volNote
  )
}

function buildAction(state: string | null, deployPct: number): string {
  if (state === 'Strong')  return `Stay fully deployed at ${deployPct}%. Add global leaders. Trim defensive hedges.`
  if (state === 'Healthy') return `Deploy at ${deployPct}%. Focus on DM leaders and EM momentum plays.`
  if (state === 'Caution') return `Deploy at ${deployPct}%. Concentrate in highest-conviction countries. Reduce laggards.`
  if (state === 'Weak')    return `Hold at ${deployPct}%. Raise cash. Prioritize capital preservation.`
  return `Maintain ${deployPct}% deployment. Wait for clearer direction before adding positions.`
}

const CATEGORY_LABELS = [
  { key: 'trend',         label: 'Trend' },
  { key: 'breadth',       label: 'Breadth' },
  { key: 'momentum',      label: 'Momentum' },
  { key: 'participation', label: 'Participation' },
] as const

export function GlobalRegimeHeadline({ regime, countries }: Props) {
  const scores      = computePillars(regime, countries)
  const description = buildDescription(regime, countries)
  const tintClass   = getTintClass(regime.regime_state)
  const accentClass = getAccentClass(regime.regime_state)
  const accentColor = getAccentColor(regime.regime_state)

  const deployPct = (() => {
    if (regime.regime_state === 'Strong')  return 100
    if (regime.regime_state === 'Healthy') return 75
    if (regime.regime_state === 'Caution') return 50
    if (regime.regime_state === 'Weak')    return 25
    return 0
  })()

  const action = buildAction(regime.regime_state, deployPct)

  const vol    = f(regime.realized_vol_5d)
  const volMed = f(regime.vol_252_median)

  const dataAsOf = regime.date
    ? new Date(regime.date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
    : '—'

  return (
    <div className={`px-6 pt-7 pb-6 border-b ${tintClass}`}>
      {/* Row 1 — state name + date */}
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-3">
          <RegimeIcon
            state={regime.regime_state}
            className={`w-8 h-8 flex-shrink-0 ${accentClass}`}
          />
          <h1
            className={`font-serif text-5xl font-semibold leading-none tracking-tight ${accentClass}`}
          >
            {regime.regime_state ?? '—'}
          </h1>
          {regime.dislocation_flag && (
            <span className="self-center inline-flex items-center gap-1.5 px-2 py-0.5 text-[11px] font-sans font-medium text-signal-neg border border-signal-neg/40 rounded-[2px] bg-signal-neg/5">
              Dislocation active
            </span>
          )}
        </div>
        <span className="font-sans text-xs text-ink-tertiary pt-1">Data as of {dataAsOf}</span>
      </div>

      {/* Row 2 — data-driven description */}
      <p className="font-sans text-sm text-ink-secondary ml-11 mb-5 max-w-3xl leading-relaxed">
        {description}
      </p>

      {/* Row 3 — all regime state pills */}
      <div className="ml-11">
        <RegimeStateStrip currentState={regime.regime_state} />
      </div>

      {/* Row 4 — four signal gauges */}
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

      {/* Row 5 — action + key stats */}
      <div className="ml-11 flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-sm font-sans text-ink-secondary">
          <ChevronRight className="w-3.5 h-3.5 text-ink-tertiary flex-shrink-0" />
          <span className="font-medium">{action}</span>
        </div>
        <div className="flex items-center gap-5 font-mono text-xs tabular-nums text-ink-tertiary">
          {vol > 0 && (
            <span>
              Vol 5d{' '}
              <span
                className={`font-medium ${vol > volMed * 1.3 ? 'text-signal-neg' : vol > volMed * 1.1 ? 'text-amber-500' : 'text-ink-primary'}`}
                style={{ color: vol > volMed * 1.3 ? undefined : vol > volMed * 1.1 ? undefined : accentColor }}
              >
                {(vol * 100).toFixed(1)}%
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
