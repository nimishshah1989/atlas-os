'use client'

import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip,
} from 'recharts'
import type { LeaderboardRow } from '@/lib/queries/strategy_lab'

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

type RadarPoint = { subject: string; value: number; fullMark: number }

function buildRadarData(row: LeaderboardRow): RadarPoint[] {
  const sortino = Math.min(3, Math.max(0, Number(row.sortino_oos ?? 0)))
  const calmar = Math.min(3, Math.max(0, Number(row.calmar_oos ?? 0)))
  const alpha = Math.min(1, Math.max(-1, Number(row.alpha_30d ?? 0)))
  const alphaNorm = (alpha + 1) / 2 * 3

  const breakdown = row.regime_breakdown ?? {}
  const bullExposure = (breakdown.bull ?? 0) + (breakdown.recovery ?? 0)
  const drawdownControl = 1 - (breakdown.bear ?? 0)

  return [
    { subject: 'Sortino', value: Number(sortino.toFixed(2)), fullMark: 3 },
    { subject: 'Calmar', value: Number(calmar.toFixed(2)), fullMark: 3 },
    { subject: 'Alpha', value: Number(alphaNorm.toFixed(2)), fullMark: 3 },
    { subject: 'Bull Exp.', value: Number((bullExposure * 3).toFixed(2)), fullMark: 3 },
    { subject: 'DD Control', value: Number((drawdownControl * 3).toFixed(2)), fullMark: 3 },
  ]
}

type Props = {
  strategy: LeaderboardRow
}

export function GenomeRadarChart({ strategy }: Props) {
  const data = buildRadarData(strategy)
  return (
    <div className="border border-paper-rule rounded-[2px] p-4 bg-paper">
      <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-4">Genome DNA</p>
      <ResponsiveContainer width="100%" height={220}>
        <RadarChart data={data} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
          <PolarGrid stroke={RULE} />
          <PolarAngleAxis dataKey="subject" tick={{ fontSize: 10, fill: TERTIARY, fontFamily: 'var(--font-sans)' }} />
          <PolarRadiusAxis domain={[0, 3]} tick={false} axisLine={false} />
          <Tooltip contentStyle={tooltipStyle}
            formatter={(value: unknown) => [
              typeof value === 'number' ? value.toFixed(2) : '—',
              'Score',
            ]} />
          <Radar name={strategy.strategy_name} dataKey="value"
            stroke={TEAL} fill={TEAL} fillOpacity={0.25} strokeWidth={1.5}
            isAnimationActive={false} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  )
}
