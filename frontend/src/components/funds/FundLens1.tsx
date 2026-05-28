'use client'
import { useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ReferenceLine, ResponsiveContainer,
} from 'recharts'
import type { FundMetricHistoryRow } from '@/lib/queries/funds'
import { ordinal } from '@/lib/ordinal'

type PeriodKey = '1M' | '3M' | '6M'
type ViewMode = 'rs' | 'returns'

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
  const [view, setView] = useState<ViewMode>('rs')
  const pctileKey = PCTILE_KEY[period]

  const rsChartData = metricHistory
    .filter(r => r[pctileKey] != null)
    .map(r => ({
      date: formatDate(new Date(r.nav_date)),
      pctile: parseFloat(r[pctileKey] as string) * 100,
    }))

  const retChartData = metricHistory
    .filter(r => r.ret_1m != null || r.ret_3m != null || r.ret_12m != null)
    .map(r => ({
      date: formatDate(new Date(r.nav_date)),
      ret_1m:  r.ret_1m  != null ? parseFloat(r.ret_1m)  * 100 : null,
      ret_3m:  r.ret_3m  != null ? parseFloat(r.ret_3m)  * 100 : null,
      ret_12m: r.ret_12m != null ? parseFloat(r.ret_12m) * 100 : null,
    }))

  const chartData   = view === 'rs' ? rsChartData : retChartData
  const insufficientData = chartData.length < 10

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
            {view === 'rs' ? 'RS Pctile' : 'Trailing Returns'}
          </div>
          <div className="font-sans text-[10px] text-ink-tertiary">
            {view === 'rs' ? `vs ${categoryName} peers` : '1M · 3M · 12M trailing'}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          {/* Mode toggle */}
          <div className="flex rounded-sm overflow-hidden border border-paper-rule">
            {(['rs', 'returns'] as ViewMode[]).map(m => (
              <button
                key={m}
                onClick={() => setView(m)}
                className={`px-2 py-0.5 font-sans text-[10px] font-medium transition-colors ${
                  view === m ? 'bg-teal text-paper' : 'bg-paper text-ink-secondary hover:bg-paper-rule/20'
                }`}
              >
                {m === 'rs' ? 'RS' : 'Ret'}
              </button>
            ))}
          </div>
          {/* Period selector — only shown for RS mode */}
          {view === 'rs' && (
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
          )}
        </div>
      </div>

      {insufficientData ? (
        <div className="flex items-center justify-center h-32 border border-paper-rule rounded-sm">
          <p className="font-sans text-xs text-ink-tertiary">Insufficient history</p>
        </div>
      ) : view === 'rs' ? (
        <div style={{ height: 160, minHeight: 160 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rsChartData} margin={{ top: 4, right: 8, bottom: 16, left: 24 }}>
              <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#94a3b8' }} interval="preserveStartEnd" />
              <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: '#94a3b8' }} tickFormatter={v => `${v}`} />
              <ReferenceLine y={50} stroke="#cbd5e1" strokeDasharray="4 3" strokeWidth={1} />
              <Tooltip
                contentStyle={{ fontSize: 11, fontFamily: 'var(--font-sans)' }}
                formatter={(v) => {
                  const n = typeof v === 'number' ? v : Number(v)
                  return [Number.isFinite(n) ? ordinal(Math.round(n)) : '—', 'RS Pctile']
                }}
              />
              <Line type="monotone" dataKey="pctile" stroke="#1D9E75" strokeWidth={1.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div style={{ height: 160, minHeight: 160 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={retChartData} margin={{ top: 4, right: 8, bottom: 16, left: 32 }}>
              <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#94a3b8' }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 9, fill: '#94a3b8' }} tickFormatter={v => `${v.toFixed(0)}%`} />
              <ReferenceLine y={0} stroke="#cbd5e1" strokeDasharray="4 3" strokeWidth={1} />
              <Tooltip
                contentStyle={{ fontSize: 11, fontFamily: 'var(--font-sans)' }}
                formatter={(v, name) => {
                  const n = typeof v === 'number' ? v : Number(v)
                  const label = name === 'ret_1m' ? '1M' : name === 'ret_3m' ? '3M' : '12M'
                  return [`${n >= 0 ? '+' : ''}${Number.isFinite(n) ? n.toFixed(1) : '—'}%`, label]
                }}
              />
              <Line type="monotone" dataKey="ret_1m"  stroke="#1D9E75" strokeWidth={1.5} dot={false} />
              <Line type="monotone" dataKey="ret_3m"  stroke="#0ea5e9" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
              <Line type="monotone" dataKey="ret_12m" stroke="#f59e0b" strokeWidth={1.5} dot={false} strokeDasharray="2 2" />
            </LineChart>
          </ResponsiveContainer>
          <div className="flex items-center gap-3 mt-1 justify-end">
            {[{ color: '#1D9E75', label: '1M' }, { color: '#0ea5e9', label: '3M' }, { color: '#f59e0b', label: '12M' }].map(l => (
              <div key={l.label} className="flex items-center gap-1">
                <div className="w-5 h-px" style={{ backgroundColor: l.color }} />
                <span className="font-sans text-[9px] text-ink-tertiary">{l.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
