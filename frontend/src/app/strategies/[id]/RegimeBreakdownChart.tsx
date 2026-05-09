'use client'
// src/app/strategies/[id]/RegimeBreakdownChart.tsx
// Stacked horizontal BarChart showing alpha per regime from backtest's regime_breakdown JSONB.
// Shape: {"Risk-On": {alpha: 0.12, days: 245}, ...}

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
  ResponsiveContainer,
} from 'recharts'

// Hex values matching design token comments in the spec
const REGIME_COLORS: Record<string, string> = {
  'Risk-On': '#22c55e33',       // signal-pos/20
  'Constructive': '#1D9E7526', // accent/15
  'Cautious': '#f59e0b26',     // signal-warn/15
  'Risk-Off': '#ef444433',     // signal-neg/20
}

const REGIME_STROKE: Record<string, string> = {
  'Risk-On': '#22c55e',
  'Constructive': '#1D9E75',
  'Cautious': '#f59e0b',
  'Risk-Off': '#ef4444',
}

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

type RegimeEntry = { regime: string; alpha: number; days: number }

function parseBreakdown(
  breakdown: Record<string, { alpha: number; days: number }> | null,
): RegimeEntry[] {
  if (!breakdown) return []
  return Object.entries(breakdown).map(([regime, data]) => ({
    regime,
    alpha: data.alpha,
    days: data.days,
  }))
}

type Props = {
  breakdown: Record<string, { alpha: number; days: number }> | null
}

export function RegimeBreakdownChart({ breakdown }: Props) {
  const entries = parseBreakdown(breakdown)

  if (entries.length === 0) {
    return (
      <div className="border border-paper-rule rounded-[2px] p-6 text-center">
        <p className="font-sans text-sm text-ink-tertiary">
          No regime breakdown stored for this backtest.
        </p>
      </div>
    )
  }

  return (
    <div className="border border-paper-rule rounded-[2px] p-4">
      <h3 className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-4">
        Alpha by Regime
      </h3>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart
          data={entries}
          layout="vertical"
          margin={{ top: 4, right: 24, bottom: 0, left: 80 }}
        >
          <XAxis
            type="number"
            tickFormatter={(v: number) => `${(v * 100).toFixed(1)}%`}
            tick={axisTickStyle}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            type="category"
            dataKey="regime"
            tick={{ fontSize: 10, fill: TERTIARY, fontFamily: 'var(--font-sans)' }}
            tickLine={false}
            axisLine={false}
            width={76}
          />
          <Tooltip
            contentStyle={tooltipStyle}
            formatter={(value: unknown, _name: unknown, entry: { payload?: RegimeEntry }) => [
              typeof value === 'number'
                ? `${(value * 100).toFixed(2)}% alpha · ${entry.payload?.days ?? 0} days`
                : '—',
              'Alpha',
            ]}
          />
          <Bar dataKey="alpha" isAnimationActive={false} maxBarSize={20}>
            {entries.map((entry) => (
              <Cell
                key={entry.regime}
                fill={REGIME_COLORS[entry.regime] ?? '#94a3b833'}
                stroke={REGIME_STROKE[entry.regime] ?? TERTIARY}
                strokeWidth={1}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="flex gap-4 mt-3 flex-wrap">
        {entries.map((e) => (
          <span key={e.regime} className="font-sans text-[10px] text-ink-tertiary">
            <span style={{ color: REGIME_STROKE[e.regime] ?? TERTIARY }}>&#9632;</span>{' '}
            {e.regime}:{' '}
            <span className="font-mono">{(e.alpha * 100).toFixed(2)}%</span> ({e.days}d)
          </span>
        ))}
      </div>
    </div>
  )
}
