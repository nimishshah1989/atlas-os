'use client'

// frontend/src/components/v6/calls/SixCellCards.tsx
//
// "Six cells worth a click" section for /calls (Page 08).
// Receives pre-split {best: [3], worst: [3]} from getTopSixCells() (C3).
// Each card shows: cell label, direction badge (ActionBadge reuse, I3),
// win rate, avg realized excess, n, open count.
//
// C2: fmtSignedPct for sign-aware percent formatting
// C3: best/worst explicitly split at query layer — no slice guessing
// I3: ActionBadge replaces local dirTag, LinkedCell for cell label

import type { TopSixResult, TopCell } from '@/lib/queries/v6/calls'
import { fmtSignedPct } from '@/lib/format-number'
import { ActionBadge } from '@/components/v6/shared/ActionBadge'
import { LinkedCell } from '@/components/v6/LinkedCell'

interface SixCellCardsProps {
  /** Pre-split {best, worst} from getTopSixCells() */
  topSix: TopSixResult
}

interface CellCardProps {
  cell: TopCell
  /** 'BEST' for top 3, 'WORST' for bottom 3 */
  label: 'BEST' | 'WORST'
}

function CellCard({ cell, label }: CellCardProps) {
  const isBest = label === 'BEST'

  const borderClass = isBest ? 'border-l-signal-pos' : 'border-l-signal-neg'

  const tagClass = isBest
    ? 'bg-signal-pos/12 text-signal-pos border border-signal-pos/30'
    : 'bg-signal-neg/12 text-signal-neg border border-signal-neg/30'

  const realized = cell.avg_realized_excess
  const hitRate = cell.hit_rate

  // C2: sign-aware formatter
  const realizedStr = fmtSignedPct(realized)
  const hitRateStr = hitRate != null ? `${(hitRate * 100).toFixed(1)}%` : '—'

  const realizedClass =
    realized == null
      ? 'text-ink-primary'
      : realized < 0
        ? 'text-signal-neg'
        : 'text-signal-pos'

  const hitRateClass =
    hitRate == null
      ? 'text-ink-primary'
      : hitRate >= 0.5
        ? 'text-signal-pos'
        : 'text-signal-neg'

  // Tier for LinkedCell
  type Tier = 'Large' | 'Mid' | 'Small'
  type Tenure = '1m' | '3m' | '6m' | '12m'
  type Direction = 'POSITIVE' | 'NEGATIVE'

  return (
    <div
      className={`bg-paper border border-paper-rule rounded-[2px] border-l-[3px] ${borderClass} p-5 flex flex-col gap-3`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col">
          {/* I3: LinkedCell for cell label */}
          <span className="font-mono font-semibold text-ink-primary text-[17px] tracking-[0.02em]">
            <LinkedCell
              tier={cell.cap_tier as Tier}
              tenure={cell.tenure as Tenure}
              direction={cell.action as Direction}
              className="font-mono font-semibold text-[17px]"
            >
              {cell.cell_label}
            </LinkedCell>
            {' '}
            {/* I3: ActionBadge replaces local direction tag */}
            <ActionBadge action={cell.action} />
          </span>
          <span className="font-serif text-[13px] text-ink-secondary mt-[2px] leading-snug">
            {cell.cap_tier} · {cell.tenure} tenure · {cell.action_display} signal
          </span>
          <span className="font-mono text-[10px] text-ink-4 mt-[3px] tracking-[0.04em]">
            n={cell.call_count} calls · {cell.in_flight_count} in flight
          </span>
        </div>
        <span
          className={`font-mono text-[10px] font-bold uppercase tracking-[0.14em] px-2.5 py-1 rounded-[2px] whitespace-nowrap ${tagClass}`}
        >
          {label}
        </span>
      </div>

      {/* Metrics row */}
      <div className="grid grid-cols-4 gap-1.5 pt-2 border-t border-paper-rule">
        {[
          { label: 'Win rate', value: hitRateStr, cls: hitRateClass },
          { label: 'Real ex.', value: realizedStr, cls: realizedClass },
          { label: 'Open', value: cell.in_flight_count.toString(), cls: 'text-ink-primary' },
          {
            label: 'Tier',
            value: cell.cap_tier === 'Large' ? 'L' : cell.cap_tier === 'Mid' ? 'M' : 'S',
            cls: 'text-ink-primary',
          },
        ].map((m) => (
          <div key={m.label} className="flex flex-col items-center">
            <span className="text-[8px] font-semibold uppercase tracking-[0.14em] text-ink-4">
              {m.label}
            </span>
            <span className={`font-mono text-[12px] font-semibold mt-0.5 ${m.cls}`}>{m.value}</span>
          </div>
        ))}
      </div>

      {/* Foot */}
      <div className="flex items-center justify-between pt-1.5 border-t border-paper-rule text-[10.5px] text-ink-4">
        <span>
          {cell.in_flight_count} open · {cell.call_count - cell.in_flight_count} closed ·{' '}
          {isBest ? 'highest realized excess cell' : 'lowest realized excess cell'}
        </span>
        <span className="font-mono font-semibold text-accent">Open cell →</span>
      </div>
    </div>
  )
}

export function SixCellCards({ topSix }: SixCellCardsProps) {
  const { best, worst } = topSix

  if (best.length === 0 && worst.length === 0) {
    return (
      <div className="text-center py-8 text-ink-4 text-sm">
        No cell data available
      </div>
    )
  }

  // C3: best/worst split is explicit from query — no slice guessing
  const bestCards = best.map((c): { cell: TopCell; label: 'BEST' | 'WORST' } => ({
    cell: c,
    label: 'BEST',
  }))
  const worstCards = worst.map((c): { cell: TopCell; label: 'BEST' | 'WORST' } => ({
    cell: c,
    label: 'WORST',
  }))

  const allCards = [...bestCards, ...worstCards]

  return (
    <div className="grid grid-cols-3 gap-4">
      {allCards.map(({ cell, label }) => (
        <CellCard key={`${cell.cap_tier}-${cell.tenure}-${cell.action}`} cell={cell} label={label} />
      ))}
    </div>
  )
}
