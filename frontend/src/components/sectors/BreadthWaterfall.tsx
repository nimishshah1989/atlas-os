'use client'
import {
  ComposedChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer, Legend,
} from 'recharts'
import type { BreadthWaterfallRow } from '@/lib/queries/sectors'
import { MARKET_EVENTS } from '@/lib/event-library'
import { CHART_COLORS } from '@/lib/chart-colors'

type Props = {
  data: BreadthWaterfallRow[]
  sectorName?: string
  height?: number
}

function formatTick(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-IN', { month: 'short', year: '2-digit' })
}

type TooltipPayloadItem = {
  name: string
  value: number
  fill: string
}

function CustomTooltip({ active, payload, label }: {
  active?: boolean
  payload?: TooltipPayloadItem[]
  label?: string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-paper border border-paper-rule px-3 py-2 rounded-sm shadow-sm">
      <p className="font-sans text-[11px] text-ink-tertiary mb-1">{label}</p>
      {payload.map(p => (
        <p key={p.name} className="font-sans text-xs" style={{ color: p.fill }}>
          {p.name}: {(p.value * 100).toFixed(1)}%
        </p>
      ))}
    </div>
  )
}

export function BreadthWaterfall({ data, sectorName, height = 280 }: Props) {
  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-ink-tertiary font-sans text-sm">
        {sectorName
          ? `Insufficient history (< 30 days for ${sectorName}).`
          : 'Insufficient breadth history.'}
      </div>
    )
  }

  const sampleEvery = data.length > 600 ? Math.ceil(data.length / 300) : 1
  const sampled = data.filter((_, i) => i % sampleEvery === 0)

  return (
    <div>
      {sectorName && (
        <p className="font-sans text-[11px] text-ink-tertiary mb-2">
          {sectorName} — Leader + Strong breadth over time
        </p>
      )}
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={sampled} margin={{ top: 8, right: 16, bottom: 24, left: 40 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-paper-rule)" opacity={0.5} />
          <XAxis
            dataKey="date"
            tickFormatter={formatTick}
            tick={{ fontFamily: 'var(--font-sans)', fontSize: 10, fill: 'var(--color-ink-tertiary)' }}
            interval="preserveStartEnd"
          />
          <YAxis
            tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
            tick={{ fontFamily: 'var(--font-sans)', fontSize: 10, fill: 'var(--color-ink-tertiary)' }}
            domain={[0, 1]}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ fontFamily: 'var(--font-sans)', fontSize: 10 }}
            iconType="square"
          />

          {MARKET_EVENTS.map(event => (
            <ReferenceLine
              key={event.id}
              x={event.startDate}
              stroke={event.color}
              strokeDasharray="4 2"
              strokeOpacity={0.7}
              label={{
                value: event.label,
                position: 'top',
                fontSize: 9,
                fill: event.color,
                fontFamily: 'var(--font-sans)',
              }}
            />
          ))}

          <Bar
            dataKey="leader_pct"
            name="Leader"
            stackId="breadth"
            fill={CHART_COLORS.rsLeader}
            isAnimationActive={false}
          />
          <Bar
            dataKey="strong_pct"
            name="Strong"
            stackId="breadth"
            fill={CHART_COLORS.rsStrong}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
