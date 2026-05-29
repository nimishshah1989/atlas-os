'use client'

import { LineChart, Line, YAxis, ResponsiveContainer, ReferenceLine } from 'recharts'

// Accepts any row dict from getStockMetricHistory(). All fields are optional
// because Atlas's metric_history is wide and not every metric is populated
// for every date. We parse what we need defensively.
type MetricRow = Record<string, unknown>

interface SparklineTrajectoryGridProps {
  metricHistory: readonly MetricRow[]
}

interface SparkSpec {
  key: string
  label: string
  format: 'pct' | 'ratio' | 'absolute' | 'rs_percentile'
  /** Reference line to draw on the chart (e.g. 0 for returns, 50 for percentile rank, 1.0 for parity ratios). */
  reference?: number
  /** Direction signal: 'up_good' (rising is bullish), 'down_good' (rising is bearish — drawdown, vol) */
  directionGood: 'up_good' | 'down_good'
}

// 12 metrics fanned across strength / momentum / volume / risk.
// Only keys that exist on MetricHistoryRow are guaranteed to render;
// any sparkline with no valid data shows "no data".
const SPARKS: SparkSpec[] = [
  // Strength
  { key: 'rs_pctile_3m',      label: 'RS Percentile (3M)',     format: 'rs_percentile', reference: 0.5,  directionGood: 'up_good' },
  { key: 'ret_3m',            label: '3M Return',               format: 'pct',           reference: 0,    directionGood: 'up_good' },
  { key: 'ema_20_ratio',      label: 'Price ÷ EMA 20',          format: 'ratio',         reference: 1.0,  directionGood: 'up_good' },
  { key: 'ema_10_ratio',      label: 'EMA10 Momentum',           format: 'ratio',         reference: 1.0,  directionGood: 'up_good' },
  // Momentum / structure
  { key: 'extension_pct',     label: 'Extension vs 200D EMA',    format: 'pct',           reference: 0,    directionGood: 'up_good' },
  { key: 'drawdown_ratio_252', label: 'Drawdown Ratio (252)',    format: 'ratio',         reference: 1.0,  directionGood: 'up_good' },
  { key: 'max_drawdown_252',  label: 'Max Drawdown (252D)',      format: 'pct',           reference: 0,    directionGood: 'down_good' },
  // Volume
  { key: 'vol_ratio_63',      label: 'Volume Ratio (20D/63D)',   format: 'ratio',         reference: 1.0,  directionGood: 'up_good' },
  { key: 'avg_volume_20',     label: 'Average Volume (20D)',     format: 'absolute',                       directionGood: 'up_good' },
  // Risk
  { key: 'atr_21',            label: 'ATR (21)',                 format: 'absolute',                       directionGood: 'down_good' },
  // Hooks for later expansion (will show "no data" when not present in result set)
  { key: 'alpha_3m',          label: 'Alpha vs Nifty (3M)',      format: 'pct',           reference: 0,    directionGood: 'up_good' },
  { key: 'volume_expansion',  label: 'Volume Expansion',         format: 'ratio',         reference: 1.0,  directionGood: 'up_good' },
]

function fmt(value: number | null, format: SparkSpec['format']): string {
  if (value == null || Number.isNaN(value)) return '—'
  if (format === 'pct') return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`
  if (format === 'rs_percentile') return Math.round(value * 100).toString()
  if (format === 'ratio') return value.toFixed(3)
  return value.toFixed(2)
}

function deriveTrendColor(values: (number | null)[], directionGood: SparkSpec['directionGood']): string {
  // Compare last value to value 30 bars ago (or earliest if shorter).
  const valid = values.filter((v): v is number => v != null && !Number.isNaN(v))
  if (valid.length < 2) return '#9A8F82'
  const recent = valid.at(-1)!
  const reference = valid[Math.max(0, valid.length - 30)]
  const delta = recent - reference
  const rising = delta > 0
  if (directionGood === 'up_good') return rising ? '#2F6B43' : '#B0492C'
  return rising ? '#B0492C' : '#2F6B43'
}

function parse(value: unknown): number | null {
  if (value == null) return null
  if (typeof value === 'number') return Number.isNaN(value) ? null : value
  if (typeof value === 'string') {
    const n = parseFloat(value)
    return Number.isNaN(n) ? null : n
  }
  return null
}

function rowDate(row: MetricRow): string {
  const d = row.date
  if (d instanceof Date) return d.toISOString().slice(0, 10)
  if (typeof d === 'string') return d
  return ''
}

function SparkCell({ spec, history }: { spec: SparkSpec; history: readonly MetricRow[] }) {
  const data = history.map(row => ({
    date: rowDate(row),
    value: parse(row[spec.key]),
  }))
  const values = data.map(d => d.value)
  const validValues = values.filter((v): v is number => v != null)
  const latest = validValues.at(-1) ?? null
  const color = deriveTrendColor(values, spec.directionGood)
  const hasData = validValues.length > 1

  return (
    <div className="border border-paper-rule rounded p-3 bg-paper">
      <div className="flex items-center justify-between mb-1">
        <p className="font-mono text-[9px] uppercase tracking-wider text-ink-3 leading-tight">{spec.label}</p>
        <p className="font-mono text-[13px] font-semibold leading-none" style={{ color }}>{fmt(latest, spec.format)}</p>
      </div>
      <div className="h-[36px] -mx-1">
        {hasData ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
              <YAxis hide domain={['dataMin', 'dataMax']} />
              {spec.reference !== undefined && (
                <ReferenceLine y={spec.reference} stroke="#C2B8A8" strokeDasharray="2 2" strokeWidth={1} />
              )}
              <Line
                type="monotone"
                dataKey="value"
                stroke={color}
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="font-mono text-[10px] text-ink-4 italic mt-3">no data</p>
        )}
      </div>
    </div>
  )
}

export function SparklineTrajectoryGrid({ metricHistory }: SparklineTrajectoryGridProps) {
  if (!metricHistory || metricHistory.length < 2) return null

  return (
    <section className="px-6 py-6 border-b border-paper-rule">
      <div className="flex items-baseline justify-between mb-4">
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3">
          Signal Trajectory — 12 metrics, last {metricHistory.length} trading days
        </p>
        <p className="font-mono text-[9px] text-ink-4">
          green = improving · red = deteriorating · dashed = reference
        </p>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {SPARKS.map(spec => (
          <SparkCell key={spec.key as string} spec={spec} history={metricHistory} />
        ))}
      </div>
    </section>
  )
}
