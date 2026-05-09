'use client'
import { useMemo } from 'react'
import {
  ComposedChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'

type DataRow = { date: string; highs: number; lows: number }

type Props = {
  data: DataRow[]
}

const POS = '#22c55e'
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

function formatXTick(dateStr: string): string {
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' }).replace(' ', " '")
  } catch {
    return dateStr
  }
}

function formatTooltipDate(dateStr: string): string {
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
  } catch {
    return dateStr
  }
}

export function HighsLowsChart({ data }: Props) {
  const monthlyTicks = useMemo(() => {
    const seen = new Set<string>()
    return data
      .filter((d) => {
        const month = d.date.slice(0, 7)
        if (seen.has(month)) return false
        seen.add(month)
        return true
      })
      .map((d) => d.date)
  }, [data])

  return (
    <ResponsiveContainer width="100%" height={200}>
      <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
        <XAxis
          dataKey="date"
          ticks={monthlyTicks}
          tickFormatter={formatXTick}
          tick={axisTickStyle}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={axisTickStyle}
          tickLine={false}
          axisLine={false}
          width={36}
        />
        <Tooltip
          contentStyle={tooltipStyle}
          labelFormatter={(label) => formatTooltipDate(String(label))}
          formatter={(value: unknown, name: unknown) => [
            typeof value === 'number' ? value : '—',
            name === 'highs' ? '52W Highs' : '52W Lows',
          ]}
        />
        <Bar dataKey="highs" maxBarSize={4} isAnimationActive={false}>
          {data.map((_, index) => (
            <Cell key={`h-${index}`} fill={POS} fillOpacity={0.8} />
          ))}
        </Bar>
        <Bar dataKey="lows" maxBarSize={4} isAnimationActive={false}>
          {data.map((_, index) => (
            <Cell key={`l-${index}`} fill={NEG} fillOpacity={0.8} />
          ))}
        </Bar>
      </ComposedChart>
    </ResponsiveContainer>
  )
}
