'use client'
// frontend/src/components/v6/RegimeHero.tsx
//
// Hero card for the /regime page — deployment_multiplier is the star number.
//
// Layout (from spec):
//   Row 1: Regime label (large) + Deployment multiplier (hero)
//   Row 2: Days in current regime + 5d flip probability
//   Row 3: Deterministic one-line interpretation
//   Row 4: 12-week colored journey strip

import { CHART_COLORS } from '@/lib/chart-colors'
import type { RegimeDetail, RegimeJourneyPoint } from '@/lib/queries/v6/regime'

type Props = {
  detail: RegimeDetail
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function regimeColor(state: string): string {
  switch (state) {
    case 'Risk-On':      return CHART_COLORS.riskOn
    case 'Constructive': return CHART_COLORS.constructive
    case 'Cautious':     return CHART_COLORS.cautious
    case 'Risk-Off':     return CHART_COLORS.riskOff
    default:             return CHART_COLORS.inkTertiary
  }
}

function regimeTailwindBg(state: string): string {
  switch (state) {
    case 'Risk-On':      return 'bg-[#2F6B43]'
    case 'Constructive': return 'bg-[#1D9E75]'
    case 'Cautious':     return 'bg-[#B8860B]'
    case 'Risk-Off':     return 'bg-[#B0492C]'
    default:             return 'bg-ink-tertiary'
  }
}

function deploymentNarrative(state: string, multiplier: string | null): string {
  const pct = multiplier != null ? `${Math.round(Number(multiplier) * 100)}%` : null
  const pctStr = pct ?? 'an adjusted'
  switch (state) {
    case 'Risk-On':
      return `Full deployment at ${pctStr}. Quality-momentum cells fire strongest; add Stage 2a/2b breakouts.`
    case 'Constructive':
      return `${pctStr} deployment. Constructive — prefer leading sectors; trim laggards.`
    case 'Cautious':
      return `Mid-cap conviction underweighted at ${pctStr}. Reduce fresh entries; hold high-quality positions.`
    case 'Risk-Off':
      return `Defensive posture at ${pctStr}. Avoid new positions; preserve capital. Wait for breadth recovery.`
    default:
      return `Deployment at ${pctStr}. Monitor regime inputs for directional clarity.`
  }
}

function formatMultiplier(multiplier: string | null): string {
  if (multiplier == null) return '—'
  return `${Number(multiplier).toFixed(1)}×`
}

function formatFlipProb(prob: string | null): string {
  if (prob == null) return '—'
  return `${(Number(prob) * 100).toFixed(1)}%`
}

// ---------------------------------------------------------------------------
// Journey strip
// ---------------------------------------------------------------------------

function JourneyStrip({ journey }: { journey: RegimeJourneyPoint[] }) {
  if (journey.length === 0) {
    return (
      <div
        className="h-8 bg-paper-rule/30 rounded-[2px] flex items-center justify-center"
        role="img"
        aria-label="12-week regime journey strip — no data"
      >
        <span className="font-sans text-[10px] text-ink-tertiary">No journey data</span>
      </div>
    )
  }

  return (
    <div
      className="flex w-full h-8 rounded-[2px] overflow-hidden gap-px"
      role="img"
      aria-label={`12-week regime journey: ${journey.length} trading days shown`}
    >
      {journey.map((pt, i) => (
        <div
          key={pt.date}
          className="flex-1 h-full cursor-default"
          style={{ backgroundColor: regimeColor(pt.regime_state) }}
          title={`${pt.date}: ${pt.regime_state}`}
          aria-label={i === journey.length - 1 ? `Latest: ${pt.date} ${pt.regime_state}` : undefined}
        />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Stat cell
// ---------------------------------------------------------------------------

function StatCell({
  label,
  value,
  hero = false,
  color,
}: {
  label: string
  value: string
  hero?: boolean
  color?: string
}) {
  return (
    <div>
      <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
        {label}
      </div>
      <div
        className={
          hero
            ? 'font-mono tabular-nums font-semibold leading-none'
            : 'font-mono tabular-nums font-medium text-ink-primary leading-none'
        }
        style={
          hero
            ? { fontSize: '2.25rem', color: color ?? 'var(--color-ink-primary)' }
            : { fontSize: '1.25rem' }
        }
      >
        {value}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

export function RegimeHero({ detail }: Props) {
  const {
    regime_state,
    deployment_multiplier,
    days_in_regime,
    flip_probability_5d,
    journey,
  } = detail

  const heroColor = regimeColor(regime_state)
  const multiplierDisplay = formatMultiplier(deployment_multiplier)
  const flipDisplay = formatFlipProb(flip_probability_5d)
  const narrative = deploymentNarrative(regime_state, deployment_multiplier)
  const dayLabel = days_in_regime === 1 ? 'day' : 'days'
  const stateBg = regimeTailwindBg(regime_state)

  return (
    <section
      className="border border-paper-rule rounded-[2px] bg-paper overflow-hidden"
      aria-label={`Market regime: ${regime_state}`}
    >
      {/* Top accent bar */}
      <div className={`h-1 w-full ${stateBg}`} aria-hidden="true" />

      <div className="px-5 py-4">
        {/* Row 1: Regime label + Deployment hero */}
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
              Market Regime
            </div>
            <h1
              className="font-serif font-semibold leading-none"
              style={{ fontSize: '2rem', color: heroColor }}
            >
              {regime_state}
            </h1>
          </div>

          <div className="text-right" aria-label={`Deployment multiplier: ${multiplierDisplay}`}>
            <StatCell
              label="Deployment"
              value={multiplierDisplay}
              hero
              color={heroColor}
            />
          </div>
        </div>

        {/* Row 2: Days in regime + flip probability */}
        <div className="grid grid-cols-2 gap-4 mb-4">
          <StatCell
            label={`Day${days_in_regime !== 1 ? 's' : ''} in current regime`}
            value={days_in_regime > 0 ? String(days_in_regime) : '—'}
          />
          <StatCell
            label="5d flip probability"
            value={flipDisplay}
          />
        </div>

        {/* Row 3: Narrative */}
        <p
          className="font-sans text-sm text-ink-secondary leading-relaxed mb-4 max-w-[640px]"
          aria-label="Regime interpretation"
        >
          {narrative}
        </p>

        {/* Row 4: Journey strip */}
        <div>
          <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-2">
            12-week regime journey
          </div>
          <JourneyStrip journey={journey} />
          <div className="flex items-center gap-4 mt-2" aria-label="Journey strip legend">
            {(['Risk-On', 'Constructive', 'Cautious', 'Risk-Off'] as const).map(s => (
              <div key={s} className="flex items-center gap-1.5">
                <div
                  className="w-3 h-3 rounded-[1px] flex-shrink-0"
                  style={{ backgroundColor: regimeColor(s) }}
                  aria-hidden="true"
                />
                <span className="font-sans text-[10px] text-ink-tertiary">{s}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
