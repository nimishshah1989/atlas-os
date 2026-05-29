// frontend/src/components/v6/landing/RegimeJourney12w.tsx
//
// 12-week regime journey section for the Market Regime landing page (Page 01).
//
// Layout (pixel-matching mockup 01-market-regime.html journey-section):
//   Row 1: Colored regime blocks per week — Risk-On / Elevated / Cautious / Risk-Off
//   Row 2: Small-cap RS z-score metric cells
//   Row 3: Breadth % metric cells (colored by zone)
//   Row 4: India VIX metric cells
//   Row 5: Dispersion metric cells
//   Row 6: Date labels
//
// Server component — receives pre-fetched WeeklyRegimeCell[] from page.tsx.
// No Recharts — CSS grid + colored divs, matching mockup visual exactly.
// All colors use Atlas DS Tailwind tokens (no hardcoded hex).

import type { WeeklyRegimeCell } from '@/lib/queries/v6/landing'

type Props = {
  cells: WeeklyRegimeCell[]
}

// ---------------------------------------------------------------------------
// Sentiment enum — drives Tailwind token classes (no hardcoded hex)
// ---------------------------------------------------------------------------

type Sentiment = 'pos' | 'neg' | 'warn' | 'neutral'

function metricTextClass(s: Sentiment): string {
  switch (s) {
    case 'pos':     return 'text-signal-pos'
    case 'neg':     return 'text-signal-neg'
    case 'warn':    return 'text-signal-warn'
    default:        return 'text-ink-secondary'
  }
}

// ---------------------------------------------------------------------------
// Regime block color — returns Tailwind bg class OR inline style for tinted variants
// We keep the background as inline style because Tailwind JIT won't compile
// dynamic class values. Use token-aligned hex values only (no invented mid-tones).
// ---------------------------------------------------------------------------

type RegimeSentiment = 'risk-on' | 'constructive' | 'cautious' | 'risk-off' | 'neutral'

function regimeSentiment(state: string): RegimeSentiment {
  switch (state) {
    case 'Risk-On':      return 'risk-on'
    case 'Constructive': return 'constructive'
    case 'Elevated':     return 'constructive'
    case 'Cautious':     return 'cautious'
    case 'Risk-Off':     return 'risk-off'
    default:             return 'neutral'
  }
}

// Hex values must match Atlas DS tokens (globals.css @theme) exactly.
// signal-pos: #2F6B43 | signal-warn: #B8860B | signal-neg: #B0492C | paper-rule: #C2B8A8
const REGIME_BG: Record<RegimeSentiment, string> = {
  'risk-on':      '#2F6B43',
  'constructive': 'rgba(47,107,67,0.18)',  // signal-pos/18 tint
  'cautious':     '#B8860B',
  'risk-off':     '#B0492C',
  'neutral':      '#C2B8A8',
}

// Label text: dark regimes (cautious/risk-off) need light text; light regimes need dark
const REGIME_LABEL_CLASS: Record<RegimeSentiment, string> = {
  'risk-on':      'text-signal-pos',
  'constructive': 'text-signal-pos',
  'cautious':     'text-paper',
  'risk-off':     'text-paper',
  'neutral':      'text-ink-secondary',
}

// ---------------------------------------------------------------------------
// Metric sentiment helpers
// ---------------------------------------------------------------------------

function breadthSentiment(val: number | null): Sentiment {
  if (val == null) return 'neutral'
  if (val >= 65) return 'pos'
  if (val >= 50) return 'neutral'
  return 'warn'
}

function vixSentiment(val: number | null): Sentiment {
  if (val == null) return 'neutral'
  if (val >= 20) return 'neg'
  if (val >= 15) return 'warn'
  return 'neutral'
}

// McClellan Oscillator: >+30 strong thrust, <-30 washout, near zero = neutral
function mcclellanSentiment(val: number | null): Sentiment {
  if (val == null) return 'neutral'
  if (val >= 30) return 'pos'
  if (val <= -30) return 'neg'
  if (val >= 0) return 'neutral'
  return 'warn'
}

// Trend slope: 50D EMA % change per day. >0.1 = strong uptrend, <-0.1 = downtrend.
function trendSlopeSentiment(val: number | null): Sentiment {
  if (val == null) return 'neutral'
  if (val >= 0.10) return 'pos'
  if (val <= -0.10) return 'neg'
  return 'neutral'
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function RegimeLegend() {
  // Labels match the live backend state names emitted by
  // atlas/compute/regime.py classify_regime_state (Risk-On / Constructive /
  // Cautious / Risk-Off). The legacy "Elevated" label was the original spec
  // wording — superseded by "Constructive" since the 2026-05 lock.
  const items: Array<{ label: string; sentiment: RegimeSentiment }> = [
    { label: 'Risk-On',      sentiment: 'risk-on' },
    { label: 'Constructive', sentiment: 'constructive' },
    { label: 'Cautious',     sentiment: 'cautious' },
    { label: 'Risk-Off',     sentiment: 'risk-off' },
  ]
  return (
    <div className="flex items-center gap-3 flex-wrap" role="legend" aria-label="Regime colour key">
      {items.map(({ label, sentiment }) => (
        <div
          key={label}
          className={`flex items-center gap-1.5 px-2 py-0.5 rounded-[2px] border text-[11px] font-medium ${REGIME_LABEL_CLASS[sentiment]}`}
          style={{ background: REGIME_BG[sentiment], borderColor: 'rgba(0,0,0,0.12)' }}
        >
          {label}
        </div>
      ))}
    </div>
  )
}

function MetricCell({
  value,
  sentiment,
  label,
}: {
  value: string
  sentiment: Sentiment
  label?: string
}) {
  return (
    <div
      className={`h-7 flex items-center justify-center font-mono text-[11px] bg-paper-deep border border-paper-rule rounded-[1px] ${metricTextClass(sentiment)}`}
      title={label}
    >
      {value}
    </div>
  )
}

function RegimeBlock({ cell }: { cell: WeeklyRegimeCell }) {
  const sent = regimeSentiment(cell.regime_state)
  return (
    <div
      className={`h-9 rounded-[2px] cursor-default transition-all ${cell.is_current ? 'ring-2 ring-ink-primary ring-offset-0' : ''}`}
      style={{ background: REGIME_BG[sent] }}
      title={`Week of ${formatDateLabel(cell.week_end_date)} · ${cell.regime_state}`}
      role="img"
      aria-label={`${cell.regime_state}${cell.is_current ? ' · current' : ''}`}
    />
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDateLabel(dateStr: string): string {
  if (!dateStr) return '—'
  try {
    const d = new Date(dateStr + 'T00:00:00')
    return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }).replace(/ /g, '-')
  } catch {
    return dateStr.slice(5) // fallback: MM-DD
  }
}

function formatBreadth(val: number | null): string {
  if (val == null) return '—'
  return `${val}`
}

function formatVix(val: number | null): string {
  if (val == null) return '—'
  return `${val.toFixed(1)}`
}

function formatMcclellan(val: number | null): string {
  if (val == null) return '—'
  const sign = val >= 0 ? '+' : ''
  return `${sign}${val.toFixed(0)}`
}

function formatTrendSlope(val: number | null): string {
  if (val == null) return '—'
  const sign = val >= 0 ? '+' : ''
  return `${sign}${val.toFixed(2)}`
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function RegimeJourney12w({ cells }: Props) {
  if (cells.length === 0) {
    return (
      <section
        className="py-8 border-b border-paper-rule"
        aria-label="12-week regime journey — no data"
      >
        <div className="max-w-[1400px] mx-auto px-8">
          <div className="h-12 flex items-center justify-center bg-paper-deep border border-paper-rule rounded-[2px]">
            <span className="font-sans text-xs text-ink-tertiary">No regime history data</span>
          </div>
        </div>
      </section>
    )
  }

  const colCount = cells.length

  // CSS grid: 100px label column + N equal columns
  const gridStyle = {
    display: 'grid',
    gridTemplateColumns: `100px repeat(${colCount}, 1fr)`,
    gap: '2px',
    alignItems: 'stretch',
  } as const

  const dateRowStyle = {
    display: 'grid',
    gridTemplateColumns: `100px repeat(${colCount}, 1fr)`,
    gap: '2px',
    marginTop: '6px',
  } as const

  return (
    <section
      className="py-8 border-b border-paper-rule"
      aria-label="Trailing 12 weeks regime journey"
    >
      <div className="max-w-[1400px] mx-auto px-8">
        {/* Header */}
        <div className="flex items-baseline justify-between mb-4">
          <div>
            <h2
              className="font-serif text-[22px] font-normal tracking-[-0.011em] text-ink-primary"
            >
              Trailing 12 weeks · how we got here
            </h2>
            <p className="font-sans text-[13px] text-ink-tertiary mt-1">
              Regime call each week, alongside the four classifier inputs that drove it:
              <span className="font-medium text-ink-secondary"> Breadth, India VIX, McClellan, Trend slope</span>.
            </p>
          </div>
          <RegimeLegend />
        </div>

        {/* Regime bar */}
        <div style={gridStyle} role="row" aria-label="Regime per week">
          <div className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-ink-tertiary flex items-center pr-2">
            Regime
          </div>
          {cells.map(cell => (
            <RegimeBlock key={cell.week_end_date || String(Math.random())} cell={cell} />
          ))}
        </div>

        {/* Spacer */}
        <div className="h-3" />

        {/* Breadth row (pct_above_ema_50 from atlas_market_regime_daily) */}
        <div style={gridStyle} className="mt-1" role="row" aria-label="Breadth % above 50D EMA per week">
          <div className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-ink-tertiary flex items-center pr-2">
            Breadth&nbsp;%
          </div>
          {cells.map(cell => (
            <MetricCell
              key={cell.week_end_date || String(Math.random())}
              value={formatBreadth(cell.breadth_pct)}
              sentiment={breadthSentiment(cell.breadth_pct)}
              label={`Breadth (% above 50D EMA): ${formatBreadth(cell.breadth_pct)}%`}
            />
          ))}
        </div>

        {/* VIX row */}
        <div style={gridStyle} className="mt-1" role="row" aria-label="India VIX per week">
          <div className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-ink-tertiary flex items-center pr-2">
            India VIX
          </div>
          {cells.map(cell => (
            <MetricCell
              key={cell.week_end_date || String(Math.random())}
              value={formatVix(cell.india_vix)}
              sentiment={vixSentiment(cell.india_vix)}
              label={`India VIX: ${formatVix(cell.india_vix)}`}
            />
          ))}
        </div>

        {/* McClellan row (breadth momentum) */}
        <div style={gridStyle} className="mt-1" role="row" aria-label="McClellan Oscillator per week">
          <div className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-ink-tertiary flex items-center pr-2">
            McClellan
          </div>
          {cells.map(cell => (
            <MetricCell
              key={cell.week_end_date || String(Math.random())}
              value={formatMcclellan(cell.mcclellan)}
              sentiment={mcclellanSentiment(cell.mcclellan)}
              label={`McClellan Oscillator: ${formatMcclellan(cell.mcclellan)}`}
            />
          ))}
        </div>

        {/* Trend slope row (Nifty 500 50D EMA slope) */}
        <div style={gridStyle} className="mt-1" role="row" aria-label="Nifty 500 50D EMA slope per week">
          <div className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-ink-tertiary flex items-center pr-2">
            Trend
          </div>
          {cells.map(cell => (
            <MetricCell
              key={cell.week_end_date || String(Math.random())}
              value={formatTrendSlope(cell.trend_slope)}
              sentiment={trendSlopeSentiment(cell.trend_slope)}
              label={`50D EMA slope: ${formatTrendSlope(cell.trend_slope)}%/day`}
            />
          ))}
        </div>

        {/* Date labels row */}
        <div style={dateRowStyle} role="row" aria-label="Week dates">
          <div aria-hidden="true" />
          {cells.map(cell => (
            <div
              key={cell.week_end_date || String(Math.random())}
              className="font-mono text-[9px] text-ink-tertiary text-center tracking-[0.05em]"
            >
              {formatDateLabel(cell.week_end_date)}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
