// frontend/src/components/v6/ConvictionTape.tsx
//
// 4-segment ribbon for (1m / 3m / 6m / 12m) conviction per stock.
// Each segment colored by direction verdict + IC strength. Click → fires
// onSegmentClick(tenure). Used in tables (compact) and stock detail (large).
//
// Visual contract (atlas-v6-ia.html §B.2):
//   POSITIVE  → signal-pos
//   NEGATIVE  → signal-neg
//   NEUTRAL   → ink-tertiary tint
// Borderline (POS with IC < 0.02) softens to signal-warn.

'use client'

import type { ConvictionTape as Tape, Tenure } from '@/lib/api/v1'

type Props = {
  tape: Tape
  compact?: boolean
  /** Segment that's currently expanded (for stock detail). */
  selected?: Tenure | null
  onSegmentClick?: (tenure: Tenure) => void
  className?: string
}

const TENURES: Tenure[] = ['1m', '3m', '6m', '12m']

type SegStyle = { fill: string; label: string; icText: string }

function styleFor(verdict: Tape[Tenure]): SegStyle {
  if (verdict.direction === 'NEUTRAL') {
    return { fill: 'bg-ink-tertiary/30 text-ink-secondary', label: '·', icText: 'text-ink-tertiary' }
  }
  if (verdict.direction === 'NEGATIVE') {
    return { fill: 'bg-signal-neg text-paper', label: '−', icText: 'text-paper' }
  }
  // POSITIVE; soften to warn if IC < 0.02
  if (verdict.ic != null && verdict.ic < 0.02) {
    return { fill: 'bg-signal-warn text-paper', label: '+', icText: 'text-paper' }
  }
  return { fill: 'bg-signal-pos text-paper', label: '+', icText: 'text-paper' }
}

export function ConvictionTape({
  tape,
  compact = false,
  selected = null,
  onSegmentClick,
  className = '',
}: Props) {
  const segWidth = compact ? 'w-7' : 'w-14'
  const segHeight = compact ? 'h-[14px]' : 'h-7'
  const fontSize = compact ? 'text-[9px]' : 'text-[11px]'
  const subSize = compact ? 'hidden' : 'block text-[9px]'

  return (
    <span className={`inline-flex border border-paper-rule rounded-[2px] overflow-hidden ${className}`}>
      {TENURES.map(t => {
        const v = tape[t]
        const s = styleFor(v)
        const isSelected = selected === t
        const interactive = onSegmentClick != null
        return (
          <button
            key={t}
            type="button"
            disabled={!interactive}
            onClick={() => onSegmentClick?.(t)}
            title={`${t} · ${v.direction} · IC ${v.ic?.toFixed(3) ?? '—'} · ${v.rule_count} rule${v.rule_count === 1 ? '' : 's'}`}
            className={`${segWidth} ${segHeight} ${s.fill} font-mono ${fontSize} tabular-nums leading-none flex flex-col items-center justify-center border-r border-paper-rule/40 last:border-r-0 ${interactive ? 'cursor-pointer hover:brightness-110' : 'cursor-default'} ${isSelected ? 'ring-1 ring-offset-1 ring-teal' : ''} transition-all`}
          >
            <span className={`${s.icText} font-semibold`}>{compact ? s.label : t}</span>
            {!compact && (
              <span className={`${subSize} ${s.icText} opacity-80`}>
                {s.label}
                {v.ic != null && Math.abs(v.ic) >= 0.01 ? ` ${(v.ic * 100).toFixed(1)}` : ''}
              </span>
            )}
          </button>
        )
      })}
    </span>
  )
}
