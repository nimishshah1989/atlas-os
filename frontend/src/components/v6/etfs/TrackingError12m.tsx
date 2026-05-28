'use client'

// frontend/src/components/v6/etfs/TrackingError12m.tsx
//
// Tracking error snapshot panel for ETF deep-dive (Page 07a).
// Renders te_60d as a single gauge bar with quality zone classification.
// TE time series deferred (not stored per-day today).
//
// TE quality zones (from mockup + methodology):
//   < 10 bps — excellent (Index ETFs achievable)
//   10–20 bps — good
//   20–40 bps — acceptable (sector ETFs baseline)
//   > 40 bps — poor (high replication error)
//
// NOTE: te_60d column stores value in decimal (e.g. 0.0008 = 8bps) OR
// already in bps. Guard: if value < 1 → multiply by 10000 to get bps.

export interface TrackingError12mProps {
  ticker: string
  te60d: number | null
  category: string | null
}

type TeQuality = 'excellent' | 'good' | 'acceptable' | 'poor'

function classifyTe(bps: number): TeQuality {
  if (bps < 10) return 'excellent'
  if (bps < 20) return 'good'
  if (bps < 40) return 'acceptable'
  return 'poor'
}

const TE_QUALITY_CONFIG: Record<
  TeQuality,
  { label: string; barClass: string; textClass: string; benchmark: string }
> = {
  excellent: {
    label: 'Excellent',
    barClass: 'bg-signal-pos',
    textClass: 'text-signal-pos',
    benchmark: 'Best-in-class · broad-cap index ETFs only',
  },
  good: {
    label: 'Good',
    barClass: 'bg-signal-pos',
    textClass: 'text-signal-pos',
    benchmark: 'Tight replication · top-quartile',
  },
  acceptable: {
    label: 'Acceptable',
    barClass: 'bg-signal-warn',
    textClass: 'text-signal-warn',
    benchmark: 'Sector ETF baseline — structurally higher TE',
  },
  poor: {
    label: 'Poor',
    barClass: 'bg-signal-neg',
    textClass: 'text-signal-neg',
    benchmark: 'High replication error — factor/thematic drift likely',
  },
}

function toBps(v: number): number {
  return v < 1 ? v * 10000 : v
}

function TeGaugeBar({ bps }: { bps: number }) {
  // Max display at 60 bps
  const maxBps = 60
  const pct = Math.min(100, (bps / maxBps) * 100)
  const quality = classifyTe(bps)
  const config = TE_QUALITY_CONFIG[quality]

  return (
    <div>
      <div className="relative w-full h-5 rounded-sm overflow-hidden bg-paper-deep mb-1">
        <div
          className={`absolute top-0 bottom-0 left-0 ${config.barClass} opacity-75 transition-all`}
          style={{ width: `${pct}%` }}
        />
        {/* Zone boundary marks */}
        <div className="absolute top-0 bottom-0 w-px bg-ink-rule" style={{ left: `${(10 / maxBps) * 100}%` }} />
        <div className="absolute top-0 bottom-0 w-px bg-ink-rule" style={{ left: `${(20 / maxBps) * 100}%` }} />
        <div className="absolute top-0 bottom-0 w-px bg-ink-rule" style={{ left: `${(40 / maxBps) * 100}%` }} />
      </div>
      {/* Scale labels */}
      <div className="flex justify-between font-mono text-[8px] text-ink-tertiary px-0">
        <span>0</span>
        <span>10</span>
        <span>20</span>
        <span style={{ marginLeft: '33%' }}>40</span>
        <span>60+ bps</span>
      </div>
    </div>
  )
}

export function TrackingError12m({ ticker, te60d, category }: TrackingError12mProps) {
  if (te60d == null) {
    return (
      <div
        className="bg-paper border border-paper-rule rounded-sm p-4"
        data-testid="tracking-error-panel"
      >
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-2">
          Tracking error · 60d window
        </div>
        <div className="font-sans text-[12px] text-ink-tertiary">
          Tracking error data for <strong className="text-ink-secondary">{ticker}</strong> not yet computed.
          Run the ETF metrics daily pipeline to populate.
        </div>
      </div>
    )
  }

  const bps = toBps(te60d)
  const quality = classifyTe(bps)
  const config = TE_QUALITY_CONFIG[quality]

  return (
    <div
      className="bg-paper border border-paper-rule rounded-sm p-4"
      data-testid="tracking-error-panel"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary font-semibold">
          Tracking error · 60d window
        </div>
        <span
          className={`font-mono text-[10px] px-2 py-0.5 rounded-sm font-semibold ${config.textClass} bg-paper-deep`}
        >
          {config.label}
        </span>
      </div>

      {/* TE value */}
      <div className="flex items-baseline gap-3 mb-3">
        <span className={`font-mono text-3xl font-semibold ${config.textClass}`}>
          {bps.toFixed(0)} bps
        </span>
        <span className="font-sans text-[12px] text-ink-tertiary">
          annualised tracking error · 60-day
        </span>
      </div>

      {/* Gauge */}
      <TeGaugeBar bps={bps} />

      {/* Explanation */}
      <div className="mt-3 font-sans text-[11.5px] text-ink-secondary leading-relaxed">
        <strong className="text-ink-primary">{config.label}.</strong>{' '}
        {config.benchmark}.{' '}
        {category === 'sector' || category === 'smart_beta' ? (
          <>Sector and factor ETFs structurally carry higher TE due to index rebalancing friction.</>
        ) : (
          <>Broad-cap index ETFs with large AUM and tight bid-ask spreads achieve the lowest TE.</>
        )}
      </div>

      <div className="mt-2 font-sans text-[10.5px] text-ink-tertiary">
        60-day annualised window. 12-month TE time series available after te_history ingest.
      </div>
    </div>
  )
}

export default TrackingError12m
