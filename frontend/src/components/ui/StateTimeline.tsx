import { buildSegments, type Segment } from '@/lib/state-segment-utils'

const STATE_COLORS: Record<string, string> = {
  'Risk-On':      'bg-signal-pos',
  'Constructive': 'bg-teal',
  'Cautious':     'bg-signal-warn',
  'Risk-Off':     'bg-signal-neg',
  // Sector states
  'Overweight':   'bg-signal-pos',
  'Neutral':      'bg-accent/40',
  'Underweight':  'bg-signal-warn',
  'Avoid':        'bg-signal-neg',
  // Generic fallback
  DEFAULT:        'bg-paper-rule',
}

type Props = {
  rows: { date: Date; state: string }[]
  height?: number
  className?: string
}

export function StateTimeline({ rows, height = 12, className = '' }: Props) {
  const segments = buildSegments(rows)
  const total = segments.reduce((s, seg) => s + seg.days, 0)

  if (total === 0) return null

  return (
    <div
      className={`flex w-full rounded-[2px] overflow-hidden ${className}`}
      style={{ height }}
      role="img"
      aria-label={`State history: ${segments.map((s: Segment) => s.state).join(' → ')}`}
    >
      {segments.map((seg: Segment, i: number) => {
        const color = STATE_COLORS[seg.state] ?? STATE_COLORS.DEFAULT
        const label = formatDateLabel(seg.startDate)
        return (
          <div
            key={i}
            className={`${color} relative group`}
            style={{ width: `${(seg.days / total) * 100}%` }}
            title={`${seg.state} — from ${label}`}
          />
        )
      })}
    </div>
  )
}

function formatDateLabel(d: Date): string {
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: '2-digit' })
}
