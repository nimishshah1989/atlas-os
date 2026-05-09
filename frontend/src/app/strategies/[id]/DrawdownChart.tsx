'use client'
// src/app/strategies/[id]/DrawdownChart.tsx
// Drawdown chart computed client-side from running peak of total_value.
// Inverted AreaChart with signal-neg fill.

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'
import type { PaperPerfRow } from '@/lib/queries/paper_perf'

const NEG = '#ef4444'
const TERTIARY = '#94a3b8'
const RULE = '#e2e8f0'

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

type ChartPoint = { date: string; drawdown: number }

function buildDrawdownSeries(rows: PaperPerfRow[]): ChartPoint[] {
  let peak = -Infinity
  return rows.map((r) => {
    const val = parseFloat(r.total_value)
    if (val > peak) peak = val
    const dd = peak > 0 ? ((val - peak) / peak) * 100 : 0
    return {
      date: r.date instanceof Date
        ? r.date.toISOString().slice(0, 10)
        : String(r.date),
      drawdown: dd,
    }
  })
}

function formatXTick(dateStr: string): string {
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' }).replace(' ', " '")
  } catch {
    return dateStr
  }
}

type Props = {
  data: PaperPerfRow[]
}

export function DrawdownChart({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="border border-paper-rule rounded-[2px] p-6 text-center">
        <p className="font-sans text-sm text-ink-tertiary">
          No drawdown data — paper trading not yet active.
        </p>
      </div>
    )
  }

  const series = buildDrawdownSeries(data)

  return (
    <div className="border border-paper-rule rounded-[2px] p-4">
      <h3 className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-4">
        Drawdown from Peak
      </h3>
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={series} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <XAxis
            dataKey="date"
            tickFormatter={formatXTick}
            tick={axisTickStyle}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            tickFormatter={(v: number) => `${v.toFixed(1)}%`}
            tick={axisTickStyle}
            tickLine={false}
            axisLine={false}
            width={42}
            domain={['dataMin', 0]}
          />
          <Tooltip
            contentStyle={tooltipStyle}
            formatter={(value: unknown) => [
              typeof value === 'number' ? `${value.toFixed(2)}%` : '—',
              'Drawdown',
            ]}
          />
          <ReferenceLine y={0} stroke={TERTIARY} strokeDasharray="3 3" />
          <Area
            type="monotone"
            dataKey="drawdown"
            stroke={NEG}
            fill={NEG}
            fillOpacity={0.12}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
