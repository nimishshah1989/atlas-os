'use client'

type Segment = {
  pct: number
  color: 'green' | 'red' | 'neutral' | 'unknown'
}

type LensBarProps = {
  segments: Segment[]
  label: string
  asOfDate?: string   // shown below bar: "as of DD-MMM-YYYY"
  nullish?: boolean   // true when source data is NULL (no portfolio disclosure)
}

const COLOR_CLASS: Record<Segment['color'], string> = {
  green:   'bg-signal-pos/75',
  red:     'bg-signal-neg/70',
  neutral: 'bg-ink-tertiary/35',
  unknown: 'bg-ink-tertiary/15',
}

export function LensBar({ segments, label, asOfDate, nullish }: LensBarProps) {
  // When nullish: render a single full-width grey bar with "N/A" label
  if (nullish) {
    return (
      <div
        className="flex items-center gap-2"
        role="img"
        aria-label={`${label}: no portfolio disclosure available`}
      >
        <div className="flex-1 h-1.5 bg-ink-tertiary/10 rounded-full" />
        <span className="font-mono text-[10px] text-ink-tertiary whitespace-nowrap">N/A</span>
      </div>
    )
  }

  // Clamp each segment pct to [0, 100] and round to integer
  const clamped = segments.map(s => ({
    ...s,
    pct: Math.max(0, Math.min(100, Math.round(s.pct))),
  }))

  // Adjust the largest segment so the total is exactly 100 (prevents rounding gaps)
  const total = clamped.reduce((sum, s) => sum + s.pct, 0)
  if (total !== 100 && clamped.length > 0) {
    const maxIdx = clamped.reduce((mi, s, i) => (s.pct > clamped[mi].pct ? i : mi), 0)
    clamped[maxIdx].pct += 100 - total
  }

  const ariaLabel = `${label}: ${clamped.map(s => `${s.pct}% ${s.color}`).join(', ')}`

  return (
    <div className="space-y-0.5">
      <div
        className="flex w-full h-1.5 rounded-full overflow-hidden"
        role="img"
        aria-label={ariaLabel}
        title={asOfDate ? `as of ${asOfDate}` : undefined}
      >
        {clamped.map((s, i) => (
          <div
            key={i}
            className={COLOR_CLASS[s.color]}
            style={{ width: `${s.pct}%` }}
          />
        ))}
      </div>
      {asOfDate && (
        <div className="font-mono text-[9px] text-ink-tertiary">as of {asOfDate}</div>
      )}
    </div>
  )
}
