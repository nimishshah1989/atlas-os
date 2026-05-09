'use client'
// src/app/strategies/[id]/EquityCurveChart.tsx
// Equity curve chart — paper performance vs Nifty500 benchmark.
// Falls back to placeholder if no paper data is available (pre-M16).

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import type { PaperPerfRow } from '@/lib/queries/paper_perf'

// Hex colors matching IndicatorChart.tsx design tokens
const POS = '#22c55e'
const ACCENT = '#1D9E75'
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

type ChartPoint = {
  date: string
  strategy: number | null
  nifty500: number | null
}

function buildSeries(rows: PaperPerfRow[]): ChartPoint[] {
  if (rows.length === 0) return []
  // Rebase both series to 0% at first observation
  const firstTotal = parseFloat(rows[0].total_value)
  return rows.map((r) => {
    const totalVal = parseFloat(r.total_value)
    const strategyPct = firstTotal > 0 ? ((totalVal - firstTotal) / firstTotal) * 100 : null
    const n500 = r.benchmark_nifty500_return != null
      ? parseFloat(r.benchmark_nifty500_return) * 100
      : null
    return {
      date: r.date instanceof Date
        ? r.date.toISOString().slice(0, 10)
        : String(r.date),
      strategy: strategyPct,
      nifty500: n500,
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

export function EquityCurveChart({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="border border-paper-rule rounded-[2px] p-6 text-center">
        <p className="font-sans text-sm text-ink-tertiary">
          Backtest equity series unavailable in v0 — coming with M16 paper-trader hookup.
        </p>
        <p className="font-sans text-xs text-ink-tertiary mt-1">
          Paper trading has not started for this strategy yet.
        </p>
      </div>
    )
  }

  const series = buildSeries(data)

  return (
    <div className="border border-paper-rule rounded-[2px] p-4">
      <h3 className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-4">
        Equity Curve (rebased to 0%)
      </h3>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={series} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
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
          />
          <Tooltip
            contentStyle={tooltipStyle}
            formatter={(value: unknown, name: unknown) => [
              typeof value === 'number' ? `${value.toFixed(2)}%` : '—',
              name === 'strategy' ? 'Strategy' : 'Nifty500',
            ]}
          />
          <Legend
            wrapperStyle={{ fontFamily: 'var(--font-sans)', fontSize: '10px' }}
          />
          <Line
            type="monotone"
            dataKey="strategy"
            stroke={POS}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
            connectNulls
            name="strategy"
          />
          <Line
            type="monotone"
            dataKey="nifty500"
            stroke={ACCENT}
            strokeWidth={1}
            strokeDasharray="4 2"
            dot={false}
            isAnimationActive={false}
            connectNulls
            name="nifty500"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
