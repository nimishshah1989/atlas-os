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

type Segment = {
  state: string
  startDate: Date
  endDate: Date
  days: number
}

function buildSegments(rows: { date: Date; state: string }[]): Segment[] {
  if (rows.length === 0) return []
  const segments: Segment[] = []
  let current = rows[0]
  let startDate = rows[0].date

  for (let i = 1; i < rows.length; i++) {
    if (rows[i].state !== current.state) {
      segments.push({
        state: current.state,
        startDate,
        endDate: rows[i - 1].date,
        days: i - segments.reduce((s, seg) => s + seg.days, 0),
      })
      current = rows[i]
      startDate = rows[i].date
    }
  }
  segments.push({
    state: current.state,
    startDate,
    endDate: rows[rows.length - 1].date,
    days: rows.length - segments.reduce((s, seg) => s + seg.days, 0),
  })
  return segments
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
      aria-label={`State history: ${segments.map(s => s.state).join(' → ')}`}
    >
      {segments.map((seg, i) => {
        const pct = (seg.days / total) * 100
        const color = STATE_COLORS[seg.state] ?? STATE_COLORS.DEFAULT
        const label = formatDateLabel(seg.startDate)
        return (
          <div
            key={i}
            className={`${color} relative group`}
            style={{ width: `${pct}%` }}
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
