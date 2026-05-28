'use client'

// frontend/src/components/v6/etfs/NavVsMarketPrice.tsx
//
// NAV vs market price — AP arbitrage check panel (Page 07a).
// For now: single snapshot premium_bps value with visual gauge.
// (premium_history_90d time series deferred to migration 109 / iNAV ingest.)
//
// Renders:
//   - Gauge bar showing premium_bps relative to ±50bps range
//   - Zone classification: NAV-fair (±10), Attention (±25), AP-friction (>25)
//   - Explanation text

export interface NavVsMarketPriceProps {
  ticker: string
  premiumBps: number | null
}

function zoneLabel(bps: number): { label: string; className: string; bg: string } {
  const abs = Math.abs(bps)
  if (abs <= 10) {
    return {
      label: 'NAV-fair',
      className: 'text-signal-pos',
      bg: 'bg-signal-pos',
    }
  }
  if (abs <= 25) {
    return {
      label: 'Attention',
      className: 'text-signal-warn',
      bg: 'bg-signal-warn',
    }
  }
  return {
    label: 'AP friction',
    className: 'text-signal-neg',
    bg: 'bg-signal-neg',
  }
}

function GaugeBar({ bps }: { bps: number }) {
  // Map bps to 0..100% of bar (range -50 to +50)
  const clamped = Math.max(-50, Math.min(50, bps))
  // Center is at 50%. Width of fill from center to edge.
  const pctFromCenter = Math.abs(clamped) / 50  // 0..1
  const fillWidth = pctFromCenter * 50           // 0..50% of bar

  const isPositive = clamped >= 0
  const zone = zoneLabel(bps)

  return (
    <div className="relative w-full h-6 rounded-sm overflow-hidden bg-paper-deep">
      {/* Center mark */}
      <div className="absolute left-1/2 top-0 bottom-0 w-px bg-ink-primary z-10 -translate-x-0.5" />

      {/* ±25 bps threshold marks */}
      <div className="absolute top-0 bottom-0 w-px bg-paper-rule z-10" style={{ left: 'calc(50% + 25%)' }} />
      <div className="absolute top-0 bottom-0 w-px bg-paper-rule z-10" style={{ left: 'calc(50% - 25%)' }} />

      {/* Fill from center */}
      <div
        className={`absolute top-0 bottom-0 ${zone.bg} opacity-70 transition-all`}
        style={{
          left: isPositive ? '50%' : `calc(50% - ${fillWidth}%)`,
          width: `${fillWidth}%`,
        }}
      />

      {/* Zone labels */}
      <div className="absolute inset-0 flex items-center">
        <span className="absolute left-1 font-mono text-[8px] text-ink-tertiary">−50</span>
        <span className="absolute right-1 font-mono text-[8px] text-ink-tertiary">+50 bps</span>
        <span className="absolute left-[25%] font-mono text-[8px] text-ink-tertiary -translate-x-1/2">−25</span>
        <span className="absolute right-[25%] font-mono text-[8px] text-ink-tertiary translate-x-1/2">+25</span>
      </div>
    </div>
  )
}

export function NavVsMarketPrice({ ticker, premiumBps }: NavVsMarketPriceProps) {
  if (premiumBps == null) {
    return (
      <div
        className="bg-paper border border-paper-rule rounded-sm p-4"
        data-testid="nav-vs-market-price"
      >
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-2">
          NAV vs market price · AP arbitrage check
        </div>
        <div className="font-sans text-[12px] text-ink-tertiary">
          iNAV data for <strong className="text-ink-secondary">{ticker}</strong> is pending
          (AMFI iNAV ingest — migration 109). Premium/discount check will be available after
          the nightly refresh once ingest is active.
        </div>
      </div>
    )
  }

  const zone = zoneLabel(premiumBps)
  const sign = premiumBps > 0 ? '+' : ''

  return (
    <div
      className="bg-paper border border-paper-rule rounded-sm p-4"
      data-testid="nav-vs-market-price"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary font-semibold">
          NAV vs market price · AP arbitrage check
        </div>
        <span
          className={`font-mono text-[10px] px-2 py-0.5 rounded-sm font-semibold ${zone.className} bg-paper-deep`}
        >
          {zone.label}
        </span>
      </div>

      {/* Current premium */}
      <div className="flex items-baseline gap-3 mb-3">
        <span className={`font-mono text-3xl font-semibold ${zone.className}`}>
          {sign}{premiumBps.toFixed(0)} bps
        </span>
        <span className="font-sans text-[12px] text-ink-tertiary">
          current premium to NAV
        </span>
      </div>

      {/* Gauge */}
      <GaugeBar bps={premiumBps} />

      {/* Explanation */}
      <div className="mt-3 font-sans text-[11.5px] text-ink-secondary leading-relaxed">
        {Math.abs(premiumBps) <= 10 && (
          <>
            <strong className="text-signal-pos">NAV-fair.</strong> Market price tracks NAV within ±10 bps — clean entry zone.
            Authorised participants (APs) are actively arbitraging the spread.
          </>
        )}
        {Math.abs(premiumBps) > 10 && Math.abs(premiumBps) <= 25 && (
          <>
            <strong className="text-signal-warn">Moderate deviation.</strong> {Math.abs(premiumBps).toFixed(0)} bps from NAV — within the
            attention band. Monitor for the next 1–2 sessions before entry.
          </>
        )}
        {Math.abs(premiumBps) > 25 && (
          <>
            <strong className="text-signal-neg">AP friction zone.</strong> Premium &gt; ±25 bps usually signals thin redemption or
            temporary demand spike. Wait for gap compression to &lt;15 bps before entering at
            NAV-fair-value.
          </>
        )}
      </div>

      <div className="mt-2 font-sans text-[10.5px] text-ink-tertiary">
        Snapshot as of latest market close. Time-series history available after iNAV ingest (migration 109).
      </div>
    </div>
  )
}

export default NavVsMarketPrice
