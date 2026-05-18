'use client'

import {
  LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'

const BLUE = '#3b82f6'
const ORANGE = '#f97316'
const RULE = '#e2e8f0'
const TERTIARY = '#94a3b8'

const tooltipStyle = {
  backgroundColor: '#ffffff',
  border: `1px solid ${RULE}`,
  borderRadius: '2px',
  fontFamily: 'var(--font-sans)',
  fontSize: '11px',
  color: '#1e293b',
  padding: '6px 8px',
}

const axisTickStyle = { fontSize: 9, fill: TERTIARY }

export type WalkForwardPoint = {
  window: string
  in_sample: number | null
  out_of_sample: number | null
}

type Props = {
  data: WalkForwardPoint[]
}

export function WalkForwardChart({ data }: Props) {
  if (!data.length) {
    return (
      <div className="border border-paper-rule rounded-[2px] p-6 text-center bg-paper">
        <p className="font-sans text-sm text-ink-tertiary">Walk-forward results not yet available.</p>
        <p className="font-sans text-xs text-ink-tertiary mt-1">Requires at least 3 optimization cycles.</p>
      </div>
    )
  }

  return (
    <div className="border border-paper-rule rounded-[2px] p-4 bg-paper">
      <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-4">Walk-Forward Validation (Sortino)</p>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <XAxis dataKey="window" tick={axisTickStyle} tickLine={false} axisLine={false} />
          <YAxis tick={axisTickStyle} tickLine={false} axisLine={false} width={36}
            tickFormatter={(v: number) => v.toFixed(1)} />
          <Tooltip contentStyle={tooltipStyle}
            formatter={(value: unknown, name: unknown) => [
              typeof value === 'number' ? value.toFixed(2) : '—',
              name === 'in_sample' ? 'In-Sample' : 'Out-of-Sample',
            ]} />
          <Legend wrapperStyle={{ fontFamily: 'var(--font-sans)', fontSize: '10px' }} />
          <ReferenceLine y={1.0} stroke={RULE} strokeDasharray="3 3" />
          <Line type="monotone" dataKey="in_sample" stroke={BLUE} strokeWidth={1.5}
            dot={false} isAnimationActive={false} connectNulls name="in_sample" />
          <Line type="monotone" dataKey="out_of_sample" stroke={ORANGE} strokeWidth={1.5}
            strokeDasharray="4 2" dot={false} isAnimationActive={false} connectNulls name="out_of_sample" />
        </LineChart>
      </ResponsiveContainer>
      <p className="font-sans text-xs text-ink-tertiary mt-2">
        Blue = in-sample Sortino. Orange = held-out OOS Sortino. Gap indicates overfitting risk.
      </p>
    </div>
  )
}
