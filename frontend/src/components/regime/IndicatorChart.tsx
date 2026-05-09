'use client'
import { useMemo, useState } from 'react'
import { Maximize2, X } from 'lucide-react'
import type { ReactElement } from 'react'
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Cell,
  Brush,
} from 'recharts'

export type ChartPoint = { date: string; value: number | null }
export type YFormat = 'pct' | 'sigma' | 'ratio' | 'count' | 'large' | 'none'

type Props = {
  title: string
  description: string
  currentValue: string
  isBullish: boolean | null
  data: ChartPoint[]
  refLine?: number
  refLabel?: string
  variant: 'area' | 'bar' | 'line'
  yFormat?: YFormat
  invertBarColors?: boolean
}

const POS = '#22c55e'
const NEG = '#ef4444'
const TERTIARY = '#94a3b8'
const RULE = '#e2e8f0'

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

function makeYFmt(yFormat: YFormat): (v: number) => string {
  switch (yFormat) {
    case 'pct':   return (v) => `${(v * 100).toFixed(0)}%`
    case 'sigma': return (v) => `${v.toFixed(2)}σ`
    case 'ratio': return (v) => v.toFixed(2)
    case 'count': return (v) => v.toFixed(0)
    case 'large': return (v) => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(0)
    default:      return (v) => String(v)
  }
}

export function IndicatorChart({
  title,
  description,
  currentValue,
  isBullish,
  data,
  refLine,
  refLabel,
  variant,
  yFormat = 'none',
  invertBarColors = false,
}: Props) {
  const [expanded, setExpanded] = useState(false)
  const lineColor = isBullish === true ? POS : isBullish === false ? NEG : TERTIARY
  const yFmt = makeYFmt(yFormat)

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

  function buildChart(withBrush: boolean): ReactElement {
    const xAxis = (
      <XAxis
        dataKey="date"
        ticks={monthlyTicks}
        tickFormatter={formatXTick}
        tick={axisTickStyle}
        tickLine={false}
        axisLine={false}
      />
    )
    const yAxis = (
      <YAxis
        tickFormatter={yFmt}
        tick={axisTickStyle}
        tickLine={false}
        axisLine={false}
        width={36}
      />
    )
    const tip = (
      <Tooltip
        contentStyle={tooltipStyle}
        labelFormatter={(label) => formatTooltipDate(String(label))}
        formatter={(value: unknown) => [typeof value === 'number' ? yFmt(value) : '—', title]}
      />
    )
    const refEl = refLine !== undefined ? (
      <ReferenceLine
        y={refLine}
        stroke={TERTIARY}
        strokeDasharray="3 3"
        label={refLabel ? { value: refLabel, position: 'insideTopRight', fontSize: 8, fill: TERTIARY } : undefined}
      />
    ) : null
    const brushEl = withBrush ? (
      <Brush dataKey="date" height={22} stroke={RULE} tickFormatter={formatXTick} travellerWidth={6} />
    ) : null

    if (variant === 'area') {
      return (
        <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          {xAxis}{yAxis}{tip}{refEl}
          <Area
            type="monotone"
            dataKey="value"
            stroke={lineColor}
            fill={lineColor}
            fillOpacity={0.08}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
          {brushEl}
        </AreaChart>
      )
    } else if (variant === 'bar') {
      return (
        <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          {xAxis}{yAxis}{tip}{refEl}
          <Bar dataKey="value" maxBarSize={4} isAnimationActive={false}>
            {data.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={invertBarColors ? NEG : (entry.value ?? 0) >= 0 ? POS : NEG}
              />
            ))}
          </Bar>
          {brushEl}
        </BarChart>
      )
    } else {
      return (
        <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          {xAxis}{yAxis}{tip}{refEl}
          <Line
            type="monotone"
            dataKey="value"
            stroke={lineColor}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
          {brushEl}
        </LineChart>
      )
    }
  }

  return (
    <>
      <div className="border border-paper-rule rounded-sm p-5 flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between mb-2">
          <span className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary pr-2">
            {title}
          </span>
          <div className="flex items-center gap-2 shrink-0">
            {isBullish === true && (
              <span className="font-sans text-[10px] font-medium text-signal-pos">BULLISH</span>
            )}
            {isBullish === false && (
              <span className="font-sans text-[10px] font-medium text-signal-neg">BEARISH</span>
            )}
            <button
              onClick={() => setExpanded(true)}
              className="text-ink-tertiary hover:text-ink-secondary transition-colors ml-1"
              title="Expand chart"
            >
              <Maximize2 className="w-3 h-3" />
            </button>
          </div>
        </div>

        {/* Description — full text, no clamp */}
        <p className="font-sans text-xs text-ink-tertiary leading-relaxed mb-3">
          {description}
        </p>

        {/* Current value */}
        <div className="font-mono text-lg font-semibold mb-4" style={{ color: lineColor }}>
          {currentValue}
        </div>

        {/* Chart */}
        <div className="mt-auto">
          <ResponsiveContainer width="100%" height={200}>
            {buildChart(false)}
          </ResponsiveContainer>
        </div>
      </div>

      {/* Expand modal */}
      {expanded && (
        <div
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-6"
          onClick={() => setExpanded(false)}
        >
          <div
            className="bg-paper border border-paper-rule rounded-sm p-7 w-full max-w-4xl shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal header */}
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-3">
                <span className="font-sans text-sm font-semibold uppercase tracking-wide text-ink-secondary">
                  {title}
                </span>
                {isBullish === true && (
                  <span className="font-sans text-[10px] font-medium text-signal-pos">BULLISH</span>
                )}
                {isBullish === false && (
                  <span className="font-sans text-[10px] font-medium text-signal-neg">BEARISH</span>
                )}
              </div>
              <button
                onClick={() => setExpanded(false)}
                className="text-ink-tertiary hover:text-ink-secondary transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="font-sans text-xs text-ink-secondary leading-relaxed mb-4">
              {description}
            </p>

            <div className="font-mono text-2xl font-semibold mb-6" style={{ color: lineColor }}>
              {currentValue}
            </div>

            <ResponsiveContainer width="100%" height={400}>
              {buildChart(true)}
            </ResponsiveContainer>

            <p className="font-sans text-[10px] text-ink-tertiary mt-3">
              Drag the handles below the chart to zoom into a specific period. Click outside to close.
            </p>
          </div>
        </div>
      )}
    </>
  )
}
