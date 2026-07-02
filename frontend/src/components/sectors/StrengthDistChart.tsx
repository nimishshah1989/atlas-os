'use client'
// frontend/src/components/sectors/StrengthDistChart.tsx
// Strength distribution bar chart — quintile distribution of constituent 3M returns.
// Source: mv_sector_deepdive.strength_dist JSONB {very_strong, strong, neutral, weak, very_weak}.
// Theme-aware: bar colours come from the decile ramp via useThemeTokens so the chart
// recolours live with the day/night toggle.

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import type { StrengthDist } from '@/lib/queries/sectors'
import { useThemeTokens } from '@/components/ui/useThemeTokens'

// ── Bucket → decile-ramp anchor (strong = high decile … weak = low decile) ──────
const BUCKET_DECILE: Record<string, number> = {
  'Very Strong': 10,
  'Strong':      8,
  'Neutral':     5,
  'Weak':        3,
  'Very Weak':   1,
}

// ── Main component ────────────────────────────────────────────────────────────

export function StrengthDistChart({ dist }: { dist: StrengthDist }) {
  const t = useThemeTokens()
  const bucketColor = (name: string) => (t ? t.decile(BUCKET_DECILE[name]) : '#888888')
  const tick = t?.tick ?? '#888888'

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
      <div className="flex items-center justify-center h-40 text-txt-3 font-sans text-sm">
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
            tick={{ fontFamily: 'Inter, sans-serif', fontSize: 10, fill: tick }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fontFamily: 'var(--font-num), monospace', fontSize: 10, fill: tick }}
            axisLine={false}
            tickLine={false}
            width={28}
          />
          <Tooltip
            cursor={{ fill: t?.grid ?? 'rgba(0,0,0,0.04)' }}
            content={({ active, payload }) => {
              if (!active || !payload?.[0]) return null
              const entry = payload[0].payload as { name: string; value: number }
              return (
                <div className="rounded-tile border border-edge-rule bg-surface-raised p-3 shadow-panel">
                  <div className="font-medium text-[13px] mb-1" style={{ color: bucketColor(entry.name) }}>{entry.name}</div>
                  <div className="font-num text-[12px] tabular-nums text-txt-2">{entry.value} stocks</div>
                  <div className="text-[11px] text-txt-3 mt-0.5">
                    Top quintile = strongest 20% by 3M return
                  </div>
                </div>
              )
            }}
          />
          <Bar dataKey="value" radius={[2, 2, 0, 0]}>
            {data.map((entry) => (
              <Cell key={entry.name} fill={bucketColor(entry.name)} fillOpacity={0.85} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {/* Legend row */}
      <div className="flex items-center justify-center gap-4 mt-1">
        {data.map((d) => (
          <div key={d.name} className="flex items-center gap-1 text-[10px] text-txt-3">
            <span
              className="w-2 h-2 rounded-[1px]"
              style={{ background: bucketColor(d.name), opacity: 0.85 }}
            />
            <span>
              {d.name.replace('Very Strong', 'V.Strong').replace('Very Weak', 'V.Weak')}:{' '}
              <span className="font-num font-semibold tabular-nums text-txt-2">{d.value}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
