'use client'

// frontend/src/components/v6/calls/CellTrajectories.tsx
//
// Per-cell realized-excess trajectory strip for /calls (Page 08).
// Shows top 6 cells by avg realized_excess_pct.
// Each row: cell label, diverging bar (negative left / positive right), endpoint value.
//
// C2: fmtSignedPct for sign-aware formatting
// I3: DriftWarnChip for WATCH state (reused component)
// I4: Diverging bar — negative bars extend left, positive right. No clamping to 0.

import type { TopCell } from '@/lib/queries/v6/calls'
import { fmtSignedPct } from '@/lib/format-number'
import { DriftWarnChip } from '@/components/v6/DriftWarnChip'

interface CellTrajectoriesProps {
  cells: TopCell[]
}

/**
 * I4: Diverging bar — renders negative to the left, positive to the right.
 * Scale: ±15% realized excess maps to ±50% of bar width each side.
 * Negative shown red, positive shown green. No clamping to 0.
 */
function DivergingBar({ value }: { value: number | null }) {
  if (value === null) {
    return (
      <div className="w-full h-[40px] flex items-center">
        <span className="text-[10px] text-ink-4 font-mono">no data</span>
      </div>
    )
  }

  // Scale: 15% excess = 50% bar width. Clamp at 50% each side.
  const MAX_EXCESS = 0.15
  const scaledPct = Math.min(50, Math.abs(value) / MAX_EXCESS * 50)
  const isPos = value >= 0

  return (
    <div className="w-full h-[40px] flex items-center">
      <div className="w-full flex items-center">
        {/* Left half (negative side) */}
        <div className="flex-1 flex justify-end">
          {!isPos && (
            <div
              className="h-[6px] bg-signal-neg rounded-l-[1px]"
              style={{ width: `${scaledPct}%` }}
            />
          )}
        </div>

        {/* Center tick */}
        <div className="w-px h-[10px] bg-ink-rule mx-[1px] flex-shrink-0" />

        {/* Right half (positive side) */}
        <div className="flex-1 flex justify-start">
          {isPos && (
            <div
              className="h-[6px] bg-signal-pos rounded-r-[1px]"
              style={{ width: `${scaledPct}%` }}
            />
          )}
        </div>
      </div>
    </div>
  )
}

export function CellTrajectories({ cells }: CellTrajectoriesProps) {
  const displayed = cells.slice(0, 6)

  if (displayed.length === 0) {
    return (
      <div className="text-center py-8 text-ink-4 text-sm">
        No cell data available
      </div>
    )
  }

  return (
    <div className="border border-paper-rule rounded-[2px] bg-paper px-[22px] py-[18px]">
      {/* Headers */}
      <div
        className="grid gap-[14px] pb-[10px] border-b border-ink-rule mb-1"
        style={{ gridTemplateColumns: '220px 1fr 120px' }}
      >
        <span className="text-[9px] font-semibold uppercase tracking-[0.14em] text-ink-4">Cell</span>
        <span className="text-[9px] font-semibold uppercase tracking-[0.14em] text-ink-4 text-center">
          Realized excess · negative ← 0% → positive
        </span>
        <span className="text-right text-[9px] font-semibold uppercase tracking-[0.14em] text-ink-4">
          Win rate · ex.
        </span>
      </div>

      {displayed.map((cell, i) => {
        const realized = cell.avg_realized_excess
        const hitRate = cell.hit_rate
        const realizedStr = fmtSignedPct(realized)
        // C2: sign-aware — fmtSignedPct handles negative correctly
        const hitRateStr = hitRate != null ? `${(hitRate * 100).toFixed(0)}%` : '—'

        // Drift: watch if hit_rate < 0.4 or realized excess < 0
        const isDrift = (hitRate != null && hitRate < 0.40) || (realized != null && realized < 0)
        const isNeg = realized != null && realized < 0

        const endpointClass = isNeg
          ? 'text-signal-neg'
          : isDrift
            ? 'text-signal-warn'
            : 'text-signal-pos'

        const isLast = i === displayed.length - 1

        return (
          <div
            key={cell.cell_label}
            className={`grid gap-[14px] items-center py-[11px] ${!isLast ? 'border-b border-dashed border-paper-rule' : ''}`}
            style={{ gridTemplateColumns: '220px 1fr 120px' }}
          >
            <div className="flex flex-col gap-[2px]">
              <span className="font-mono font-semibold text-ink-primary text-[13px]">
                {cell.cell_label}
              </span>
              <span className="text-[10px] text-ink-4">
                {cell.cap_tier} · {cell.action_display} · n={cell.call_count}
              </span>
              {/* I3: DriftWarnChip for WATCH state — uses drift_warn status */}
              {isDrift && (
                <DriftWarnChip driftStatus="drift_warn" className="mt-[2px]" />
              )}
            </div>

            {/* I4: Diverging bar */}
            <DivergingBar value={realized} />

            <div className={`text-right font-mono text-[13px] font-semibold ${endpointClass}`}>
              {hitRateStr}
              <span className="block text-[10px] font-normal mt-[1px]">
                {realizedStr}
              </span>
              <span className="block text-[10px] text-ink-4 font-normal mt-[1px]">
                {cell.in_flight_count} open
              </span>
            </div>
          </div>
        )
      })}

      <div className="mt-3 px-3 py-[10px] bg-paper-soft border border-paper-rule rounded-[2px] border-l-[3px] border-l-signal-info text-[12px] text-ink-secondary leading-snug">
        <strong className="text-ink-primary">Reading this:</strong> Win rate = % of calls that beat tier-anchor benchmark.
        Avg realized excess shows actual outperformance.
        Cells below 40% win rate are drift-flagged.
        Bar extends left (negative) or right (positive) from center zero line.
      </div>
    </div>
  )
}
