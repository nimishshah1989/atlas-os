'use client'

import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'

const TEAL = '#1D9E75'
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

export type EquityCurvePoint = {
  date: string
  return_pct: number | null
}

function formatXTick(dateStr: string): string {
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString('en-IN', { month: 'short', year: '2-digit' })
  } catch {
    return dateStr
  }
}

type Props = {
  data: EquityCurvePoint[]
  title?: string
}

export function EquityCurveChart({ data, title = 'Equity Curve (rebased to 0%)' }: Props) {
  if (!data.length) {
    return (
      <div className="border border-paper-rule rounded-[2px] p-6 text-center bg-paper">
        <p className="font-sans text-sm text-ink-tertiary">Equity curve not yet available.</p>
        <p className="font-sans text-xs text-ink-tertiary mt-1">Strategy is in early optimization — paper trading starts after promotion.</p>
      </div>
    )
  }

  const maxVal = Math.max(...data.map(d => d.return_pct ?? 0))
  const minVal = Math.min(...data.map(d => d.return_pct ?? 0))

  return (
    <div className="border border-paper-rule rounded-[2px] p-4 bg-paper">
      <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-4">{title}</p>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="tealGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={TEAL} stopOpacity={0.25} />
              <stop offset="95%" stopColor={TEAL} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <XAxis dataKey="date" tickFormatter={formatXTick} tick={axisTickStyle} tickLine={false} axisLine={false} />
          <YAxis tick={axisTickStyle} tickLine={false} axisLine={false} width={42}
            domain={[Math.floor(minVal - 2), Math.ceil(maxVal + 2)]}
            tickFormatter={(v: number) => `${v.toFixed(0)}%`} />
          <Tooltip contentStyle={tooltipStyle}
            formatter={(value: unknown) => [
              typeof value === 'number' ? `${value.toFixed(2)}%` : '—',
              'Return',
            ]} />
          <ReferenceLine y={0} stroke={TERTIARY} strokeDasharray="3 3" />
          <Area type="monotone" dataKey="return_pct" stroke={TEAL} fill="url(#tealGrad)"
            strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
