// frontend/src/components/v6/stocks/CompositeTrajectoriesGrid.tsx
// Page 05 · 30-day composite trajectory grid
// Shows 6 watched names: top 3 BUYs + top 3 AVOIDs by |composite_score|
// Each row: stock name/meta | Recharts sparkline | endpoint value + delta
'use client'

import { useMemo } from 'react'
import {
  LineChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'
import type { LandscapeRow } from '@/lib/queries/v6/stocks-landscape'
import { pickSixStocks } from './helpers'

export { pickSixStocks }

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtComposite(n: number): string {
  return n >= 0 ? `+${n.toFixed(1)}` : n.toFixed(1)
}

function fmtDelta(delta: number): string {
  return delta >= 0 ? `Δ +${delta.toFixed(1)}` : `Δ ${delta.toFixed(1)}`
}

// ---------------------------------------------------------------------------
// SparklineTip
// ---------------------------------------------------------------------------

function SparkTip({ active, payload }: { active?: boolean; payload?: Array<{ value?: number }> }) {
  if (!active || !payload?.length) return null
  const v = payload[0].value
  if (v == null) return null
  return (
    <div className="bg-paper border border-paper-rule rounded-sm px-2 py-1 font-mono text-[10px] text-ink-primary shadow-sm">
      {fmtComposite(v)}
    </div>
  )
}

// ---------------------------------------------------------------------------
// TrajectoryRow — single sparkline row
// ---------------------------------------------------------------------------

function TrajectoryRow({ row }: { row: LandscapeRow }) {
  const traj = row.composite_trajectory_30d ?? []
  const action = row.action ?? 'WATCH'
  const lineColor =
    action === 'BUY' ? 'var(--color-signal-pos)' : action === 'AVOID' ? 'var(--color-signal-neg)' : 'var(--color-signal-warn)'

  const currentScore = row.composite_score ? parseFloat(row.composite_score) : 0
  const firstScore = traj.length > 0 ? traj[0].score : currentScore
  const delta = currentScore - firstScore

  // Recharts LineChart data: normalise to ensure x-axis is index-based
  const chartData = traj.map((pt, i) => ({ idx: i, score: pt.score }))
  // Append current if different from last traj point
  const lastTraj = traj[traj.length - 1]
  if (lastTraj && Math.abs(lastTraj.score - currentScore) > 0.01) {
    chartData.push({ idx: traj.length, score: currentScore })
  }

  // Determine endpoint color
  const endColor =
    currentScore >= 4 ? 'var(--color-signal-pos)' : currentScore <= -4 ? 'var(--color-signal-neg)' : 'var(--color-signal-warn)'

  const actionBadge =
    action === 'BUY' ? 'BUY' : action === 'AVOID' ? 'AVOID' : 'WATCH'

  return (
    <div
      className="grid items-center py-[11px] border-b border-dashed border-paper-rule last:border-b-0"
      style={{ gridTemplateColumns: '200px 1fr 90px', gap: '14px' }}
    >
      {/* Stock name */}
      <div className="flex flex-col gap-[2px]">
        <span className="font-mono font-semibold text-ink-primary text-[13px]">
          {row.symbol}
        </span>
        <span className="font-sans text-[10px] text-ink-tertiary">
          {row.sector ?? '—'} · {row.cap_tier} · {actionBadge}
        </span>
      </div>

      {/* Sparkline */}
      <div style={{ height: 36 }}>
        {chartData.length >= 2 ? (
          <ResponsiveContainer width="100%" height={36}>
            <LineChart data={chartData} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
              {/* Threshold line at 0 */}
              <ReferenceLine y={0} stroke="var(--color-ink-rule)" strokeDasharray="2 4" strokeWidth={1} />
              <Tooltip content={<SparkTip />} />
              <Line
                type="monotone"
                dataKey="score"
                stroke={lineColor}
                strokeWidth={1.6}
                dot={false}
                activeDot={{ r: 2.5, fill: lineColor }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-[36px] flex items-center justify-center font-sans text-[10px] text-ink-tertiary">
            —
          </div>
        )}
      </div>

      {/* Endpoint value + delta */}
      <div
        className="font-mono text-[13px] font-semibold text-right"
        style={{ color: endColor }}
      >
        {fmtComposite(currentScore)}
        <span className="font-mono text-[10px] text-ink-tertiary block mt-[1px]">
          {fmtDelta(delta)}
        </span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function CompositeTrajectoriesGrid({ data }: { data: LandscapeRow[] }) {
  const stocks = useMemo(() => pickSixStocks(data, { requireTrajectory: true }), [data])

  return (
    <section className="py-9 border-b border-paper-rule">
      <div className="max-w-[1400px] mx-auto px-8">
        <div className="flex items-baseline justify-between mb-5 flex-wrap gap-3">
          <div>
            <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary leading-none">
              Composite trajectories · 30 days
            </h2>
            <p className="font-sans text-[13px] text-ink-tertiary mt-1 max-w-[760px] leading-snug">
              How the composite score has evolved for six key names. Rising = thesis strengthening.
              Falling = early warning. Threshold for action change is at the dashed mid-line
              (composite ≥ +4 → BUY, ≤ −4 → AVOID).
            </p>
          </div>
        </div>

        <div className="bg-paper border border-paper-rule rounded-sm py-[18px] px-[22px]">
          {/* Column headers */}
          <div
            className="grid py-1 pb-[10px] font-sans text-[9px] tracking-[0.14em] uppercase text-ink-tertiary font-semibold border-b border-ink-rule"
            style={{ gridTemplateColumns: '200px 1fr 90px', gap: '14px' }}
          >
            <span>Stock</span>
            <span>30-day composite trajectory</span>
            <span className="text-right">Today · Δ30d</span>
          </div>

          {stocks.length === 0 ? (
            <div className="py-8 text-center font-sans text-[13px] text-ink-tertiary">
              No trajectory data available. Run the nightly pipeline.
            </div>
          ) : (
            stocks.map(s => <TrajectoryRow key={s.instrument_id} row={s} />)
          )}
        </div>
      </div>
    </section>
  )
}
