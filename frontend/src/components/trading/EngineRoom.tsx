'use client'

import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import type { InsightRow, GenePoolHealth, LeaderboardRow } from '@/lib/queries/strategy_lab'

const TEAL = '#1D9E75'
const RULE = '#e2e8f0'
const TERTIARY = '#94a3b8'

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

type ParamImportanceChartProps = {
  data: Record<string, number>
}

function ParameterImportanceChart({ data }: ParamImportanceChartProps) {
  const entries = Object.entries(data)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12)
    .map(([name, value]) => ({ name, value: Number(value.toFixed(3)) }))

  if (!entries.length) {
    return (
      <div className="flex items-center justify-center h-32">
        <p className="font-sans text-xs text-ink-tertiary">No parameter data yet — engine still optimizing.</p>
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={entries} layout="vertical" margin={{ top: 4, right: 12, bottom: 4, left: 120 }}>
        <XAxis type="number" tick={axisTickStyle} tickLine={false} axisLine={false}
          tickFormatter={(v: number) => v.toFixed(2)} />
        <YAxis type="category" dataKey="name" tick={axisTickStyle} tickLine={false} axisLine={false} width={116} />
        <Tooltip contentStyle={tooltipStyle}
          formatter={(value: unknown) => [
            typeof value === 'number' ? value.toFixed(3) : '—',
            'Importance',
          ]} />
        <Bar dataKey="value" radius={[0, 2, 2, 0]} isAnimationActive={false}>
          {entries.map((entry, i) => (
            <Cell key={`cell-${i}`} fill={i === 0 ? TEAL : `${TEAL}${Math.max(40, 255 - i * 18).toString(16).padStart(2, '0')}`} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

type GenePoolHealthPanelProps = {
  health: GenePoolHealth
}

function GenePoolHealthPanel({ health }: GenePoolHealthPanelProps) {
  const total = health.active_count + health.killed_count + health.promoted_count
  const survivalRate = total > 0 ? ((health.promoted_count / total) * 100).toFixed(1) : '0.0'
  const lastBorn = health.last_born_at
    ? new Date(health.last_born_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
    : '—'

  return (
    <div className="grid grid-cols-2 gap-3">
      {[
        { label: 'Active Genomes', value: health.active_count, cls: 'text-teal-600' },
        { label: 'Promoted to Leaderboard', value: health.promoted_count, cls: 'text-blue-600' },
        { label: 'Killed This Cycle', value: health.killed_count, cls: 'text-red-500' },
        { label: 'Promotion Rate', value: `${survivalRate}%`, cls: 'text-ink-primary' },
      ].map(({ label, value, cls }) => (
        <div key={label} className="border border-paper-rule rounded-[2px] p-3 bg-paper">
          <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide">{label}</p>
          <p className={`font-mono text-xl font-semibold mt-1 ${cls}`}>{value}</p>
        </div>
      ))}
      <div className="col-span-2 border border-paper-rule rounded-[2px] p-3 bg-paper">
        <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide">Last Genome Born</p>
        <p className="font-mono text-sm font-semibold text-ink-primary mt-1">{lastBorn}</p>
      </div>
    </div>
  )
}

function EvolutionTreePlaceholder({ leaderboard }: { leaderboard: LeaderboardRow[] }) {
  return (
    <div className="border border-paper-rule rounded-[2px] p-4 bg-paper">
      <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-3">Generation Tree</p>
      {leaderboard.length === 0 ? (
        <p className="font-sans text-sm text-ink-tertiary">No promoted strategies yet.</p>
      ) : (
        <div className="space-y-2">
          {leaderboard.slice(0, 8).map((row) => (
            <div key={row.genome_id} className="flex items-center gap-3">
              <span className="font-mono text-xs text-ink-tertiary w-6">#{row.rank}</span>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-sans text-xs text-ink-primary">{row.strategy_name}</span>
                  <span className="font-sans text-xs text-ink-tertiary">Gen {row.generation}</span>
                </div>
                <div className="h-1 bg-paper-rule rounded-full mt-1 overflow-hidden">
                  <div className="h-full rounded-full"
                    style={{ width: `${Math.min(100, Number(row.sortino_oos ?? 0) * 30)}%`, backgroundColor: TEAL }} />
                </div>
              </div>
              <span className="font-mono text-xs text-ink-primary w-12 text-right">
                {row.sortino_oos ? Number(row.sortino_oos).toFixed(2) : '—'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

type Props = {
  insights: InsightRow | null
  health: GenePoolHealth
  leaderboard: LeaderboardRow[]
}

export function EngineRoom({ insights, health, leaderboard }: Props) {
  const lastRun = insights?.generated_at
    ? new Date(insights.generated_at).toLocaleString('en-IN', {
        day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
      })
    : '—'

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="font-sans text-xs text-ink-tertiary">Last optimization run: <span className="font-mono">{lastRun}</span></p>
        <span className="font-sans text-xs px-2 py-1 rounded-[2px] bg-teal-50 text-teal-700 border border-teal-200">
          {health.active_count} genomes active
        </span>
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div className="space-y-4">
          <div className="border border-paper-rule rounded-[2px] p-4 bg-paper">
            <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-4">Parameter Importance</p>
            <ParameterImportanceChart data={insights?.parameter_importance ?? {}} />
          </div>
        </div>

        <div className="space-y-4">
          <div className="border border-paper-rule rounded-[2px] p-4 bg-paper">
            <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-4">Gene Pool Health</p>
            <GenePoolHealthPanel health={health} />
          </div>
        </div>
      </div>

      <EvolutionTreePlaceholder leaderboard={leaderboard} />

      {insights && insights.insight_bullets.length > 0 && (
        <div className="border border-paper-rule rounded-[2px] p-5 bg-paper">
          <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-3">Overnight Insight Feed</p>
          <ul className="space-y-3">
            {insights.insight_bullets.map((bullet, i) => (
              <li key={i} className="font-sans text-sm text-ink-primary flex gap-3 pb-3 border-b border-paper-rule last:border-0 last:pb-0">
                <span className="text-teal-600 font-mono text-xs mt-0.5 flex-shrink-0">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span>{bullet.replace(/^\d+\.\s*/, '')}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(!insights || insights.insight_bullets.length === 0) && (
        <div className="border border-paper-rule rounded-[2px] p-5 bg-paper text-center">
          <p className="font-sans text-sm text-ink-tertiary">No insights generated yet. Engine runs nightly after market close.</p>
        </div>
      )}
    </div>
  )
}
