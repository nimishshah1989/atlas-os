'use client'
import { useState } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, Legend,
  ResponsiveContainer,
} from 'recharts'
import type { FundLensHistoryRow } from '@/lib/queries/funds'

type View = 'composition' | 'holdings'

function formatDate(d: Date): string {
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  return `${months[d.getMonth()]} '${String(d.getFullYear()).slice(2)}`
}

type LensTooltipProps = {
  active?: boolean
  payload?: { name: string; value: number; color: string }[]
  label?: string
}
function CustomTooltip({ active, payload, label }: LensTooltipProps) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-paper border border-paper-rule rounded-sm shadow-sm px-3 py-2 text-[10px] font-sans space-y-0.5 min-w-[140px]">
      <div className="text-ink-tertiary font-semibold mb-1">{label}</div>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center justify-between gap-3">
          <span style={{ color: p.color }}>{p.name}</span>
          <span className="font-mono">{p.value?.toFixed(1)}%</span>
        </div>
      ))}
    </div>
  )
}

export function FundLensHistory({ lensHistory }: { lensHistory: FundLensHistoryRow[] }) {
  const [view, setView] = useState<View>('composition')

  if (lensHistory.length === 0) {
    return (
      <div className="flex items-center justify-center h-40 border border-paper-rule rounded-sm">
        <p className="font-sans text-xs text-ink-tertiary">No disclosure history available</p>
      </div>
    )
  }

  const chartData = lensHistory.map(r => {
    const date = formatDate(new Date(r.as_of_date))
    if (view === 'composition') {
      return {
        date,
        Aligned: r.aligned_aum_pct != null ? parseFloat(r.aligned_aum_pct) : null,
        Neutral: r.neutral_aum_pct != null ? parseFloat(r.neutral_aum_pct) : null,
        Avoid:   r.avoid_aum_pct   != null ? parseFloat(r.avoid_aum_pct)   : null,
      }
    } else {
      return {
        date,
        Strong:  r.strong_aum_pct  != null ? parseFloat(r.strong_aum_pct)  : null,
        Unknown: r.unknown_aum_pct != null ? parseFloat(r.unknown_aum_pct) : null,
        Weak:    r.weak_aum_pct    != null ? parseFloat(r.weak_aum_pct)    : null,
      }
    }
  })

  const compositionConfig = [
    { key: 'Aligned', color: '#1D9E75', stackId: 'a' },
    { key: 'Neutral', color: '#94a3b8', stackId: 'a' },
    { key: 'Avoid',   color: '#ef4444', stackId: 'a' },
  ]

  const holdingsConfig = [
    { key: 'Strong',  color: '#1D9E75', stackId: 'b' },
    { key: 'Unknown', color: '#94a3b8', stackId: 'b' },
    { key: 'Weak',    color: '#ef4444', stackId: 'b' },
  ]

  const areaConfig = view === 'composition' ? compositionConfig : holdingsConfig

  const latestRow = lensHistory[lensHistory.length - 1]
  const lastDisclosed = latestRow?.last_disclosed_date
    ? new Date(latestRow.last_disclosed_date).toLocaleDateString('en-IN', {
        day: '2-digit', month: 'short', year: 'numeric',
      }).replace(',', '')
    : null

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
            Lens History
          </div>
          <div className="font-sans text-[10px] text-ink-tertiary">
            {lensHistory.length} disclosure{lensHistory.length !== 1 ? 's' : ''}
            {lastDisclosed && ` · Last: ${lastDisclosed}`}
          </div>
        </div>
        <div className="flex gap-0.5">
          {(['composition', 'holdings'] as View[]).map(v => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`px-2 py-0.5 rounded-sm font-sans text-[10px] font-medium transition-colors ${
                view === v ? 'bg-teal text-paper' : 'bg-paper-rule/20 text-ink-secondary hover:bg-paper-rule/40'
              }`}
            >
              {v === 'composition' ? 'Sectors' : 'Holdings'}
            </button>
          ))}
        </div>
      </div>

      <div style={{ height: 180, minHeight: 180 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 28 }}>
            <XAxis
              dataKey="date"
              tick={{ fontSize: 9, fill: '#94a3b8' }}
              interval="preserveStartEnd"
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fontSize: 9, fill: '#94a3b8' }}
              tickFormatter={v => `${v}%`}
              width={26}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ fontSize: 10, fontFamily: 'var(--font-sans)', paddingTop: 4 }}
            />
            {areaConfig.map(({ key, color, stackId }) => (
              <Area
                key={key}
                type="monotone"
                dataKey={key}
                stackId={stackId}
                fill={color}
                stroke={color}
                fillOpacity={0.7}
                strokeWidth={0}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
