'use client'
// frontend/src/components/v6/sectors/StrengthDistChart.tsx
// Strength distribution bar chart — quintile distribution of constituent 3M returns.
// Source: mv_sector_deepdive.strength_dist JSONB {very_strong, strong, neutral, weak, very_weak}.

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import type { StrengthDist } from '@/lib/queries/v6/sectors'

// ── Color map ─────────────────────────────────────────────────────────────────

const BUCKET_COLORS: Record<string, string> = {
  'Very Strong': '#2F6B43',
  'Strong':      '#1D9E75',
  'Neutral':     'var(--color-ink-4, #9A8F82)',
  'Weak':        '#B8860B',
  'Very Weak':   '#B0492C',
}

// ── Tooltip ───────────────────────────────────────────────────────────────────

type DistEntry = { name: string; value: number; total: number }
type DistTooltipArgs = { active?: boolean; payload?: Array<{ payload: DistEntry }> }

function DistTooltip({ active, payload }: DistTooltipArgs) {
  if (!active || !payload?.[0]) return null
  const entry = payload[0].payload
  const { name, value } = entry
  const color = BUCKET_COLORS[name] ?? 'var(--color-ink-4, #9A8F82)'
  return (
    <div className="bg-paper border border-paper-rule rounded-[2px] p-3 shadow-md">
      <div className="font-medium text-ink-primary text-[13px] mb-1" style={{ color }}>{name}</div>
      <div className="font-mono text-[12px] text-ink-secondary">{value} stocks</div>
      <div className="text-[11px] text-ink-tertiary mt-0.5">
        Top quintile = strongest 20% by 3M return
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function StrengthDistChart({ dist }: { dist: StrengthDist }) {
  const total = dist.very_strong + dist.strong + dist.neutral + dist.weak + dist.very_weak

  const data = [
    { name: 'Very Strong', value: dist.very_strong, total },
    { name: 'Strong',      value: dist.strong,      total },
    { name: 'Neutral',     value: dist.neutral,     total },
    { name: 'Weak',        value: dist.weak,         total },
    { name: 'Very Weak',   value: dist.very_weak,   total },
  ]

  if (total === 0) {
    return (
      <div className="flex items-center justify-center h-40 text-ink-tertiary font-sans text-sm">
        Strength distribution unavailable — no 3M return data.
      </div>
    )
  }

  return (
    <div data-testid="strength-dist-chart" aria-label="Constituent strength distribution by 3M return quintile">
      <ResponsiveContainer width="100%" height={170}>
        <BarChart
          data={data}
          margin={{ top: 8, right: 16, bottom: 4, left: 8 }}
          barCategoryGap="20%"
        >
          <XAxis
            dataKey="name"
            tick={{ fontFamily: 'Inter, sans-serif', fontSize: 10, fill: 'var(--color-ink-tertiary, #6B6157)' }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, fill: 'var(--color-ink-tertiary, #6B6157)' }}
            axisLine={false}
            tickLine={false}
            width={28}
          />
          <Tooltip content={<DistTooltip />} cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
          <Bar dataKey="value" radius={[2, 2, 0, 0]}>
            {data.map((entry) => (
              <Cell key={entry.name} fill={BUCKET_COLORS[entry.name] ?? 'var(--color-ink-4, #9A8F82)'} fillOpacity={0.85} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {/* Legend row */}
      <div className="flex items-center justify-center gap-4 mt-1">
        {data.map((d) => (
          <div key={d.name} className="flex items-center gap-1 text-[10px] text-ink-tertiary">
            <span
              className="w-2 h-2 rounded-[1px]"
              style={{ background: BUCKET_COLORS[d.name] ?? 'var(--color-ink-4, #9A8F82)', opacity: 0.85 }}
            />
            <span>
              {d.name.replace('Very Strong', 'V.Strong').replace('Very Weak', 'V.Weak')}:{' '}
              <span className="font-mono font-semibold text-ink-secondary">{d.value}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
