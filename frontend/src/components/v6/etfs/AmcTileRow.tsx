'use client'

// frontend/src/components/v6/etfs/AmcTileRow.tsx
//
// 9-AMC tile row sized by monthly turnover (total_adv_cr = ADV × ~20 trading days).
// Each tile: AMC name · ETF count · monthly turnover · action summary.
// Color band on top: BUY-dominant = green, AVOID = red, neutral = teal.
//
// Data: AmcAggregate[] from getAmcAggregates() (pure JS, 34 rows).

import type { AmcAggregate } from '@/lib/queries/v6/etfs'

function fmtAdv(cr: number): string {
  if (cr >= 1_00_000) return `₹${(cr / 1_00_000).toFixed(2)} L cr`
  if (cr >= 1000) return `₹${(cr / 1000).toFixed(2)} K cr`
  return `₹${cr.toFixed(0)} cr`
}

function topBorderColor(amc: AmcAggregate): string {
  if (amc.dominant_action === 'BUY') return 'border-t-signal-pos'
  if (amc.dominant_action === 'AVOID') return 'border-t-signal-neg'
  if (amc.dominant_action === 'WATCH') return 'border-t-signal-warn'
  return 'border-t-teal'
}

function actionLabel(amc: AmcAggregate): { text: string; className: string } {
  if (amc.buy_count > 0 && amc.dominant_action === 'BUY') {
    return { text: `+${amc.buy_count} BUY`, className: 'text-signal-pos' }
  }
  if (amc.avoid_count > 0 && amc.dominant_action === 'AVOID') {
    return { text: `−${amc.avoid_count} AVOID`, className: 'text-signal-neg' }
  }
  if (amc.buy_count > 0) {
    return { text: `+${amc.buy_count} BUY`, className: 'text-signal-pos' }
  }
  return { text: 'neutral', className: 'text-ink-tertiary' }
}

export interface AmcTileRowProps {
  amcs: AmcAggregate[]
}

export function AmcTileRow({ amcs }: AmcTileRowProps) {
  // Show top 9 by AUM proxy
  const display = amcs.slice(0, 9)

  return (
    <div
      className="grid gap-2.5"
      style={{ gridTemplateColumns: `repeat(${Math.min(display.length, 9)}, 1fr)` }}
      data-testid="amc-tile-row"
    >
      {display.map((amc) => {
        const action = actionLabel(amc)
        return (
          <div
            key={amc.fund_house}
            className={`bg-paper border border-paper-rule rounded-sm p-3 text-center border-t-[3px] ${topBorderColor(amc)}`}
            data-testid={`amc-tile-${amc.fund_house}`}
          >
            <div className="font-mono font-bold text-[10px] text-ink-primary tracking-wide mb-1.5">
              {amc.fund_house}
            </div>
            <div className="font-mono text-base font-medium text-ink-primary leading-none">
              {amc.etf_count}
            </div>
            <div className="font-mono text-[10px] text-ink-tertiary mt-0.5">
              {fmtAdv(amc.total_adv_cr)}
            </div>
            <div className="font-sans text-[8.5px] text-ink-tertiary tracking-wide mt-0" title="ADV × ~20 trading days ≈ monthly turnover; actual AUM pending iNAV ingest">
              Monthly turnover
            </div>
            <div className={`font-mono text-[9px] font-semibold mt-1 ${action.className}`}>
              {action.text}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default AmcTileRow
