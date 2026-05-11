'use client'
import { useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ReferenceLine, ResponsiveContainer,
} from 'recharts'
import type { FundMetricHistoryRow } from '@/lib/queries/funds'

type PeriodKey = '1M' | '3M' | '6M'
const PCTILE_KEY: Record<PeriodKey, keyof FundMetricHistoryRow> = {
  '1M': 'rs_pctile_1m',
  '3M': 'rs_pctile_3m',
  '6M': 'rs_pctile_6m',
}

function formatDate(d: Date): string {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${String(d.getDate()).padStart(2, '0')}-${months[d.getMonth()]}`
}

export function FundLens1({
  metricHistory,
  categoryName,
}: {
  metricHistory: FundMetricHistoryRow[]
  categoryName: string
}) {
  const [period, setPeriod] = useState<PeriodKey>('3M')
  const pctileKey = PCTILE_KEY[period]

  const chartData = metricHistory
    .filter(r => r[pctileKey] != null)
    .map(r => ({
      date: formatDate(new Date(r.nav_date)),
      pctile: parseFloat(r[pctileKey] as string) * 100,
    }))

  const insufficientData = chartData.length < 10

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
            RS Pctile
          </div>
          <div className="font-sans text-[10px] text-ink-tertiary">vs {categoryName} peers</div>
        </div>
        <div className="flex gap-0.5">
          {(['1M', '3M', '6M'] as PeriodKey[]).map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-2 py-0.5 rounded-sm font-sans text-[10px] font-medium transition-colors ${
                period === p ? 'bg-teal text-paper' : 'bg-paper-rule/20 text-ink-secondary hover:bg-paper-rule/40'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>
      {insufficientData ? (
        <div className="flex items-center justify-center h-32 border border-paper-rule rounded-sm">
          <p className="font-sans text-xs text-ink-tertiary">Insufficient history</p>
        </div>
      ) : (
        <div style={{ height: 160 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 16, left: 24 }}>
              <XAxis
                dataKey="date"
                tick={{ fontSize: 9, fill: '#94a3b8' }}
                interval="preserveStartEnd"
              />
              <YAxis
                domain={[0, 100]}
                tick={{ fontSize: 9, fill: '#94a3b8' }}
                tickFormatter={v => `${v}`}
              />
              <ReferenceLine y={50} stroke="#cbd5e1" strokeDasharray="4 3" strokeWidth={1} />
              <Tooltip
                contentStyle={{ fontSize: 11, fontFamily: 'var(--font-sans)' }}
                formatter={(v) => {
                  const n = typeof v === 'number' ? v : Number(v)
                  return [`${Number.isFinite(n) ? n.toFixed(0) : '—'}th`, 'RS Pctile']
                }}
              />
              <Line
                type="monotone"
                dataKey="pctile"
                stroke="#1D9E75"
                strokeWidth={1.5}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
