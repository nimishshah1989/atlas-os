'use client'
// frontend/src/components/stocks/OBVContinuousChart.tsx
// 50-day OBV sparkline with zero-cross highlighted and slope annotation.
// Client component because Recharts requires browser environment.
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import type { OBVPoint } from '@/lib/queries/stocks'

interface OBVContinuousChartProps {
  series: OBVPoint[]
}

const MIN_POINTS = 14

/**
 * Compute slope (b) of OBV vs time index via simple OLS:
 *   b = (n * Σ(i * obv_i) − Σi * Σobv_i) / (n * Σi² − (Σi)²)
 */
function computeSlope(series: OBVPoint[]): number {
  const n = series.length
  if (n < 2) return 0
  let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0
  series.forEach((pt, i) => {
    sumX  += i
    sumY  += pt.obv
    sumXY += i * pt.obv
    sumXX += i * i
  })
  const denom = n * sumXX - sumX * sumX
  if (denom === 0) return 0
  return (n * sumXY - sumX * sumY) / denom
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
}

export function OBVContinuousChart({ series }: OBVContinuousChartProps) {
  if (series.length < MIN_POINTS) {
    return (
      <section data-testid="obv-chart">
        <h3 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
          OBV trend · 50 days
        </h3>
        <p className="text-xs text-ink-tertiary mt-2">
          Insufficient history (need {MIN_POINTS}+ trading days)
        </p>
      </section>
    )
  }

  const slope = computeSlope(series)
  const slopeSign = slope >= 0 ? '+' : ''
  const slopeClass = slope >= 0 ? 'text-signal-pos' : 'text-signal-neg'
  const slopeLabel = slope > 0 ? 'accumulating' : slope < 0 ? 'distributing' : 'flat'

  // Find zero-crossings: consecutive points where OBV sign flips
  const zeroCrossings = series
    .filter((pt, i) => {
      if (i === 0) return false
      const prev = series[i - 1]
      return (prev.obv >= 0 && pt.obv < 0) || (prev.obv < 0 && pt.obv >= 0)
    })
    .map((pt) => pt.date)

  return (
    <section data-testid="obv-chart">
      <h3 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
        OBV trend · 50 days
      </h3>
      <div className="flex items-baseline gap-3 mt-1">
        <span
          className={`font-mono text-lg font-medium ${slopeClass}`}
          data-testid="obv-slope"
        >
          {slopeSign}{slope.toFixed(4)}/day
        </span>
        <span className="text-xs text-ink-tertiary">{slopeLabel}</span>
      </div>

      <div style={{ height: 80 }} className="mt-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
            <XAxis
              dataKey="date"
              tickFormatter={formatDate}
              tick={{ fontSize: 9, fontFamily: 'var(--font-sans)', fill: 'var(--color-ink-tertiary)' }}
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              width={32}
              tick={{ fontSize: 9, fontFamily: 'var(--font-mono)', fill: 'var(--color-ink-tertiary)' }}
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
              labelFormatter={(label) => typeof label === 'string' ? formatDate(label) : String(label)}
            />
            {/* Zero-crossing reference lines */}
            {zeroCrossings.map((date) => (
              <ReferenceLine
                key={date}
                x={date}
                stroke="var(--color-signal-warn)"
                strokeDasharray="2 2"
                strokeWidth={1}
              />
            ))}
            {/* Zero-axis line */}
            <ReferenceLine y={0} stroke="var(--color-paper-rule)" strokeDasharray="3 3" />
            <Line
              type="monotone"
              dataKey="obv"
              name="OBV"
              stroke={slope >= 0 ? 'var(--color-signal-pos)' : 'var(--color-signal-neg)'}
              strokeWidth={1.5}
              dot={false}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <p className="text-xs text-ink-tertiary mt-2 max-w-prose">
        Validated_inverse at 63d horizon (IR -0.43). Cross-sectionally, falling-OBV
        stocks outperformed; for a held Stage 2 position, falling OBV is a topping
        warning. Zero-cross highlighted.
      </p>
    </section>
  )
}
