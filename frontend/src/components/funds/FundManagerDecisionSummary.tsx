'use client'

import Link from 'next/link'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { FundDecisionScoreRow } from '@/lib/queries/funds'

function scoreColor(score: number | null): string {
  if (score === null) return '#6b7280'
  if (score >= 65) return '#1D9E75'
  if (score >= 40) return '#f59e0b'
  return '#ef4444'
}

function DecisionStateBadge({ state }: { state: string | null }) {
  if (!state) return <span className="text-ink-tertiary font-sans text-[10px]">—</span>
  const colors: Record<string, string> = {
    Sharp: 'bg-signal-pos/15 text-signal-pos',
    Average: 'bg-signal-warn/10 text-signal-warn',
    Poor: 'bg-signal-neg/10 text-signal-neg',
  }
  const cls = colors[state] ?? 'text-ink-tertiary'
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold ${cls}`}
    >
      {state}
    </span>
  )
}

type Props = {
  scores: FundDecisionScoreRow[]
  mstar_id: string
}

export function FundManagerDecisionSummary({ scores, mstar_id }: Props) {
  if (scores.length === 0) {
    return (
      <p className="font-sans text-sm text-ink-secondary">
        No decision history available. Run <code>scripts/run_fund_decisions.py</code> to compute.
      </p>
    )
  }

  const latest = scores[0]
  const chartData = [...scores].reverse().map((s) => ({
    date: s.period_date,
    signal: s.signal_score !== null ? Number(s.signal_score) : null,
    outcome_1m: s.outcome_score_1m !== null ? Number(s.outcome_score_1m) : null,
  }))

  return (
    <div className="space-y-4">
      {/* Stats row — latest period */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="font-sans text-[11px] text-ink-tertiary">Latest state</span>
          <DecisionStateBadge state={latest.decision_state} />
        </div>
        <div className="font-sans text-[11px] text-ink-tertiary">
          <span className="text-ink-secondary">{latest.entries_count}</span> entries ·{' '}
          <span className="text-ink-secondary">{latest.exits_count}</span> exits ·{' '}
          <span className="text-ink-secondary">{latest.increases_count}</span> increases ·{' '}
          <span className="text-ink-secondary">{latest.decreases_count}</span> decreases
        </div>
        <Link
          href={`/funds/${mstar_id}/decisions`}
          className="font-sans text-[11px] text-teal-600 hover:underline ml-auto"
        >
          View full history →
        </Link>
      </div>

      {/* Bar chart */}
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: -16 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 9, fill: '#9ca3af' }}
              tickFormatter={(v: string) => v.slice(0, 7)}
            />
            <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: '#9ca3af' }} />
            <Tooltip
              formatter={(value: unknown, name: unknown) => [
                typeof value === 'number' ? `${value.toFixed(1)}` : '—',
                name === 'signal' ? 'Signal Score' : '1m Outcome',
              ]}
              labelFormatter={(label: unknown) => `Period: ${label}`}
              contentStyle={{ fontSize: 11 }}
            />
            <Legend wrapperStyle={{ fontSize: 10 }} />
            <Bar dataKey="signal" name="Signal Score" radius={[2, 2, 0, 0]}>
              {chartData.map((entry, i) => (
                <Cell key={i} fill={scoreColor(entry.signal)} />
              ))}
            </Bar>
            <Bar dataKey="outcome_1m" name="1m Outcome" fill="#94a3b8" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
