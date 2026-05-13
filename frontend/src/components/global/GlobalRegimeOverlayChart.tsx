'use client'
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceArea,
  ResponsiveContainer,
} from 'recharts'
import type { GlobalRegimeHistoryRow } from '@/lib/queries/global'

type Props = {
  history: GlobalRegimeHistoryRow[]
}

type RegimePeriod = {
  start: string
  end: string
  regime: string
}

const REGIME_COLORS: Record<string, { fill: string; opacity: number }> = {
  'Strong':  { fill: '#22c55e', opacity: 0.12 },
  'Healthy': { fill: '#14b8a6', opacity: 0.12 },
  'Caution': { fill: '#f59e0b', opacity: 0.12 },
  'Weak':    { fill: '#ef4444', opacity: 0.12 },
}

const REGIME_LABELS: Record<string, string> = {
  'Strong':  'Strong',
  'Healthy': 'Healthy',
  'Caution': 'Caution',
  'Weak':    'Weak',
}

function toDateStr(d: string): string {
  return String(d).slice(0, 10)
}

function formatXTick(dateStr: string): string {
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' }).replace(' ', " '")
  } catch {
    return dateStr
  }
}

function formatYAxisPrice(v: number): string {
  return `$${v.toFixed(0)}`
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
  border: '1px solid #e2e8f0',
  borderRadius: '2px',
  fontFamily: 'var(--font-sans)',
  fontSize: '11px',
  color: '#1e293b',
  padding: '6px 8px',
}

export function GlobalRegimeOverlayChart({ history }: Props) {
  // Build chart data
  const chartData = history.map((row) => ({
    date: toDateStr(row.date),
    price: row.benchmark_close != null ? parseFloat(row.benchmark_close) : null,
  }))

  // Build regime periods by detecting regime changes
  const regimePeriods: RegimePeriod[] = []
  if (history.length > 0) {
    let currentRegime = history[0].regime_state ?? 'Healthy'
    let periodStart = toDateStr(history[0].date)

    for (let i = 1; i < history.length; i++) {
      const rowRegime = history[i].regime_state ?? currentRegime
      if (rowRegime !== currentRegime) {
        regimePeriods.push({
          start: periodStart,
          end: toDateStr(history[i - 1].date),
          regime: currentRegime,
        })
        currentRegime = rowRegime
        periodStart = toDateStr(history[i].date)
      }
    }
    // Close the last period
    regimePeriods.push({
      start: periodStart,
      end: toDateStr(history[history.length - 1].date),
      regime: currentRegime,
    })
  }

  // Unique regimes in data for legend
  const uniqueRegimes = Array.from(
    new Set(history.map((r) => r.regime_state).filter((s): s is string => s != null))
  )

  return (
    <div>
      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          {/* Regime background shading */}
          {regimePeriods.map((period, i) => {
            const colors = REGIME_COLORS[period.regime] ?? { fill: '#94a3b8', opacity: 0.08 }
            return (
              <ReferenceArea
                key={`regime-${i}`}
                x1={period.start}
                x2={period.end}
                fill={colors.fill}
                fillOpacity={colors.opacity}
                strokeOpacity={0}
              />
            )
          })}

          <XAxis
            dataKey="date"
            tickFormatter={formatXTick}
            tick={{ fontSize: 9, fill: '#94a3b8' }}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tickFormatter={formatYAxisPrice}
            tick={{ fontSize: 9, fill: '#94a3b8' }}
            tickLine={false}
            axisLine={false}
            width={44}
            domain={['auto', 'auto']}
          />
          <Tooltip
            contentStyle={tooltipStyle}
            labelFormatter={(label) => formatTooltipDate(String(label))}
            formatter={(value: unknown) => [
              typeof value === 'number' ? `$${value.toFixed(2)}` : '—',
              'VT (World ETF)',
            ]}
          />
          <Line
            type="monotone"
            dataKey="price"
            stroke="#1e293b"
            strokeWidth={1.5}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>

      {/* Regime legend */}
      <div className="flex items-center gap-4 mt-3 flex-wrap">
        {uniqueRegimes.map((regime) => {
          const colors = REGIME_COLORS[regime] ?? { fill: '#94a3b8', opacity: 0.08 }
          return (
            <div key={regime} className="flex items-center gap-1.5">
              <span
                className="inline-block w-3 h-3 rounded-sm"
                style={{ backgroundColor: colors.fill, opacity: 0.6 }}
              />
              <span className="font-sans text-[11px] text-ink-tertiary">
                {REGIME_LABELS[regime] ?? regime}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
