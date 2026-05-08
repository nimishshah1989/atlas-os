'use client'
import {
  LineChart as RechartsLineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'

type DataPoint = {
  date: string
  primary: number | null
  benchmark?: number | null
}

type Props = {
  data: DataPoint[]
  primaryLabel?: string
  benchmarkLabel?: string
  height?: number
  primaryColor?: string
  benchmarkColor?: string
  refLineY?: number
  className?: string
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
}

export function LineChart({
  data,
  primaryLabel = 'Value',
  benchmarkLabel,
  height = 120,
  primaryColor = 'var(--color-accent)',
  benchmarkColor = 'var(--color-paper-rule)',
  refLineY,
  className = '',
}: Props) {
  return (
    <div className={className} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartsLineChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
          <XAxis
            dataKey="date"
            tickFormatter={formatDate}
            tick={{ fontSize: 10, fontFamily: 'var(--font-sans)', fill: 'var(--color-ink-tertiary)' }}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            width={36}
            tick={{ fontSize: 10, fontFamily: 'var(--font-mono)', fill: 'var(--color-ink-tertiary)' }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'var(--color-paper)',
              border: '1px solid var(--color-paper-rule)',
              borderRadius: '2px',
              fontFamily: 'var(--font-sans)',
              fontSize: '11px',
              color: 'var(--color-ink-primary)',
            }}
            labelFormatter={(label) => typeof label === 'string' ? formatDate(label) : label}
          />
          {refLineY !== undefined && (
            <ReferenceLine y={refLineY} stroke="var(--color-paper-rule)" strokeDasharray="3 3" />
          )}
          <Line
            type="monotone"
            dataKey="primary"
            name={primaryLabel}
            stroke={primaryColor}
            strokeWidth={1.5}
            dot={false}
            connectNulls
          />
          {benchmarkLabel && (
            <Line
              type="monotone"
              dataKey="benchmark"
              name={benchmarkLabel}
              stroke={benchmarkColor}
              strokeWidth={1}
              strokeDasharray="4 2"
              dot={false}
              connectNulls
            />
          )}
        </RechartsLineChart>
      </ResponsiveContainer>
    </div>
  )
}
