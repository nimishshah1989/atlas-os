'use client'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
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
  const total = payload.reduce((s, p) => s + (p.value ?? 0), 0)
  return (
    <div className="bg-paper border border-paper-rule px-3 py-2 rounded-sm shadow-sm min-w-[160px]">
      <p className="font-sans text-[11px] text-ink-tertiary mb-1.5">{label}</p>
      {[...payload].reverse().map(p => (
        <p key={p.name} className="font-sans text-[11px] flex justify-between gap-4" style={{ color: p.fill }}>
          <span>{p.name}</span>
          <span className="font-mono tabular-nums">{(p.value * 100).toFixed(1)}%</span>
        </p>
      ))}
      <p className="font-sans text-[10px] text-ink-tertiary mt-1 border-t border-paper-rule pt-1 flex justify-between">
        <span>Total tracked</span>
        <span className="font-mono tabular-nums">{(total * 100).toFixed(0)}%</span>
      </p>
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
          {sectorName} — RS classification breakdown over time
        </p>
      )}
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={sampled} margin={{ top: 8, right: 16, bottom: 24, left: 40 }} barCategoryGap="10%">
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-paper-rule)" opacity={0.5} vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={formatTick}
            tick={{ fontFamily: 'var(--font-sans)', fontSize: 10, fill: 'var(--color-ink-tertiary)' }}
            interval="preserveStartEnd"
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
            tick={{ fontFamily: 'var(--font-sans)', fontSize: 10, fill: 'var(--color-ink-tertiary)' }}
            domain={[0, 1]}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ fontFamily: 'var(--font-sans)', fontSize: 10, paddingTop: 8 }}
            iconType="square"
            iconSize={8}
          />

          {MARKET_EVENTS.map(event => (
            <ReferenceLine
              key={event.id}
              x={event.startDate}
              stroke={event.color}
              strokeDasharray="4 2"
              strokeOpacity={0.5}
              label={{
                value: event.label,
                position: 'top',
                fontSize: 9,
                fill: event.color,
                fontFamily: 'var(--font-sans)',
              }}
            />
          ))}

          {/* Stacked bottom → top: Laggard, Weak, Neutral, Strong, Leader */}
          <Bar dataKey="laggard_pct" name="Laggard"  stackId="b" fill={CHART_COLORS.rsLaggard}       isAnimationActive={false} />
          <Bar dataKey="weak_pct"    name="Weak"     stackId="b" fill={CHART_COLORS.rsWeak}          isAnimationActive={false} />
          <Bar dataKey="neutral_pct" name="Neutral"  stackId="b" fill={CHART_COLORS.rsConsolidating} isAnimationActive={false} />
          <Bar dataKey="strong_pct"  name="Strong"   stackId="b" fill={CHART_COLORS.rsStrong}        isAnimationActive={false} />
          <Bar dataKey="leader_pct"  name="Leader"   stackId="b" fill={CHART_COLORS.rsLeader}        isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
