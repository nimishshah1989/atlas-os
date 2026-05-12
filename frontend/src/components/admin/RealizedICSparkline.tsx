// SP04 Stage 4c — small sparkline showing 30-day realized IC vs predicted.
// Red threshold line at 0.5×predicted highlights revert territory.
'use client'

import {
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
} from 'recharts'

type TrailRow = {
  as_of_date: string | Date
  realized_ic: string | null
  ic_ratio: string | null
}

type Props = {
  trail: TrailRow[]
  predictedIc: string | null
}

export function RealizedICSparkline({ trail, predictedIc }: Props) {
  if (trail.length === 0) {
    return (
      <span className="font-sans text-[10px] text-ink-tertiary">
        no realized-IC data yet
      </span>
    )
  }
  const predicted = predictedIc ? parseFloat(predictedIc) : null
  const threshold = predicted !== null ? predicted * 0.5 : null

  const data = trail.map((t) => ({
    date: typeof t.as_of_date === 'string' ? t.as_of_date.slice(5) : '',
    realized: t.realized_ic ? parseFloat(t.realized_ic) : null,
    ratio: t.ic_ratio ? parseFloat(t.ic_ratio) : null,
  }))

  return (
    <div className="h-12 w-48">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          <XAxis dataKey="date" hide />
          <YAxis hide domain={['auto', 'auto']} />
          {threshold !== null && (
            <ReferenceLine
              y={threshold}
              stroke="#C84B3B"
              strokeDasharray="2 2"
              strokeWidth={1}
            />
          )}
          {predicted !== null && (
            <ReferenceLine
              y={predicted}
              stroke="#7A7A7A"
              strokeDasharray="2 2"
              strokeWidth={1}
            />
          )}
          <Tooltip
            contentStyle={{
              fontSize: '11px',
              padding: '4px 8px',
              border: '1px solid #E5E2DC',
              borderRadius: '2px',
            }}
          />
          <Line
            type="monotone"
            dataKey="realized"
            stroke="#1D9E75"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
