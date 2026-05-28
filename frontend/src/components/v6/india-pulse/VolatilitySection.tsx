// frontend/src/components/v6/india-pulse/VolatilitySection.tsx
//
// Section 4 — Volatility: 3 cards.
// - Spot India VIX
// - 5-year percentile
// - Term structure (VIX - VIX9d)
// Server component.

import type { IndiaPulsePageData } from '@/lib/queries/v6/india_pulse'
import { fmtNum } from './helpers'

type Props = {
  data: Pick<IndiaPulsePageData, 'vix_spot' | 'vix_5y_pct' | 'vix_term_structure'>
}

function vixColor(vix: number | null): string {
  if (vix == null) return 'text-ink-tertiary'
  if (vix > 20) return 'text-signal-neg'
  if (vix > 15) return 'text-signal-warn'
  return 'text-signal-pos'
}

export function VolatilitySection({ data }: Props) {
  const { vix_spot, vix_5y_pct, vix_term_structure } = data

  const pctDisplay = vix_5y_pct != null ? Math.round(vix_5y_pct * 100) : null
  const pbarWidth = pctDisplay ?? 0

  const termColor = vix_term_structure != null && vix_term_structure > 0
    ? 'text-signal-pos'
    : vix_term_structure != null && vix_term_structure < -0.2
    ? 'text-signal-neg'
    : 'text-signal-warn'

  return (
    <div className="grid grid-cols-3 gap-4">
      {/* Card 1 — Spot VIX */}
      <div className="bg-paper border border-paper-rule rounded-sm p-5">
        <div className="text-[10px] uppercase tracking-[0.15em] text-ink-tertiary font-semibold mb-1">
          Spot India VIX
        </div>
        <div className={`font-mono text-[24px] font-medium leading-tight ${vixColor(vix_spot)}`}>
          {fmtNum(vix_spot, 2)}
        </div>
        <div className="text-[12px] text-ink-tertiary mt-2.5 leading-[1.45]">
          {vix_spot != null ? (
            <>
              {vix_spot > 20
                ? <><strong className="text-ink-secondary">Elevated volatility.</strong> VIX above 20 signals heightened investor caution.</>
                : vix_spot > 15
                ? <><strong className="text-ink-secondary">Climbing.</strong> VIX above 15 — options markets hedging activity rising.</>
                : <><strong className="text-ink-secondary">Calm.</strong> VIX below 15 — below historical averages.</>
              }
            </>
          ) : 'Data unavailable.'}
        </div>
        <div className="mt-3 h-7 bg-paper-deep rounded-sm opacity-50 flex items-center justify-center">
          <span className="text-[8px] text-ink-tertiary italic">Pipeline gap — coming with next ingest</span>
        </div>
      </div>

      {/* Card 2 — 5-year percentile */}
      <div className="bg-paper border border-paper-rule rounded-sm p-5">
        <div className="text-[10px] uppercase tracking-[0.15em] text-ink-tertiary font-semibold mb-1">
          5-year percentile
        </div>
        <div className={`font-mono text-[24px] font-medium leading-tight ${
          pctDisplay != null && pctDisplay > 70 ? 'text-signal-neg' :
          pctDisplay != null && pctDisplay > 50 ? 'text-signal-warn' :
          'text-ink-primary'
        }`}>
          {pctDisplay != null ? (
            <>{pctDisplay}<span className="text-[16px] text-ink-tertiary">th</span></>
          ) : '—'}
        </div>
        <div className="text-[12px] text-ink-tertiary mt-2.5 leading-[1.45]">
          {pctDisplay != null
            ? `Higher than ${pctDisplay}% of trading sessions over the last 5 years.`
            : 'Data unavailable.'}
        </div>
        {/* Progress bar */}
        {pctDisplay != null && (
          <div className="mt-3.5">
            <div className="relative bg-paper-deep h-2 w-full rounded-sm overflow-visible">
              <div
                className={`h-full rounded-sm ${pctDisplay > 70 ? 'bg-signal-neg' : pctDisplay > 50 ? 'bg-signal-warn' : 'bg-signal-pos'}`}
                style={{ width: `${Math.min(100, pbarWidth)}%` }}
              />
              {/* 50th marker */}
              <div className="absolute top-[-2px] bottom-[-2px] w-px bg-ink-tertiary" style={{ left: '50%' }} />
              {/* 80th marker */}
              <div className="absolute top-[-2px] bottom-[-2px] w-px bg-signal-neg" style={{ left: '80%' }} />
            </div>
            <div className="flex justify-between text-[9px] text-ink-4 mt-1 font-mono">
              <span>0</span>
              <span>median</span>
              <span>80th</span>
              <span>100</span>
            </div>
          </div>
        )}
      </div>

      {/* Card 3 — Term structure */}
      <div className="bg-paper border border-paper-rule rounded-sm p-5">
        <div className="text-[10px] uppercase tracking-[0.15em] text-ink-tertiary font-semibold mb-1">
          Term structure (VIX − VIX9d)
        </div>
        <div className={`font-mono text-[24px] font-medium leading-tight ${termColor}`}>
          {vix_term_structure != null
            ? (vix_term_structure > 0 ? `+${vix_term_structure.toFixed(2)}` : vix_term_structure.toFixed(2))
            : '—'}
        </div>
        <div className="text-[12px] text-ink-tertiary mt-2.5 leading-[1.45]">
          {vix_term_structure != null ? (
            vix_term_structure > 0
              ? <><strong className="text-ink-secondary">Contango.</strong> Short-dated below long-dated. No immediate panic; risk seen further out.</>
              : vix_term_structure < -0.2
              ? <><strong className="text-ink-secondary">Backwardation.</strong> Short-term fear elevated above long-term. Immediate stress signal.</>
              : <><strong className="text-ink-secondary">Near flat.</strong> Term structure neutral.</>
          ) : 'Data unavailable.'}
        </div>
      </div>
    </div>
  )
}
