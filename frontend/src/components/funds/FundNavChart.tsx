'use client'
import { useState, useMemo } from 'react'
import {
  ComposedChart, Line, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'
import type { FundNavHistoryRow } from '@/lib/queries/funds'

type Period = '1M' | '3M' | '6M' | '1Y' | '3Y' | '5Y'
const PERIOD_DAYS: Record<Period, number> = {
  '1M': 30, '3M': 90, '6M': 180, '1Y': 365, '3Y': 1095, '5Y': 1825,
}

function formatDate(d: Date): string {
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  return `${String(d.getDate()).padStart(2,'0')}-${months[d.getMonth()]}-${d.getFullYear()}`
}

function formatShortDate(d: Date): string {
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  return `${months[d.getMonth()]} '${String(d.getFullYear()).slice(2)}`
}

function formatNav(v: string | number): string {
  const n = typeof v === 'string' ? parseFloat(v) : v
  return `₹${n.toFixed(2)}`
}

function pctChange(from: number, to: number): string {
  const pct = ((to - from) / from) * 100
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`
}

type TooltipProps = { active?: boolean; payload?: { dataKey: string; value: number }[]; label?: string }
function CustomTooltip({ active, payload, label }: TooltipProps) {
  if (!active || !payload?.length) return null
  const nav = payload.find((p) => p.dataKey === 'nav_adj')?.value
  const change = payload.find((p) => p.dataKey === 'nav_change')?.value
  return (
    <div className="bg-paper border border-paper-rule rounded-sm shadow-sm px-3 py-2 text-[11px] font-sans space-y-0.5">
      <div className="text-ink-tertiary">{label}</div>
      {nav != null && <div className="font-mono font-semibold text-ink-primary">{formatNav(nav)}</div>}
      {change != null && nav != null && (
        <div className={`font-mono ${change >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
          {change >= 0 ? '+' : ''}{change.toFixed(2)} ({pctChange(nav - change, nav)})
        </div>
      )}
    </div>
  )
}

export function FundNavChart({ navHistory }: { navHistory: FundNavHistoryRow[] }) {
  const [period, setPeriod] = useState<Period>('1Y')

  const cutoff = useMemo(() => {
    const d = new Date()
    d.setDate(d.getDate() - PERIOD_DAYS[period])
    return d
  }, [period])

  const filtered = useMemo(
    () => navHistory.filter(r => new Date(r.nav_date) >= cutoff),
    [navHistory, cutoff],
  )

  const chartData = useMemo(
    () =>
      filtered.map(r => ({
        date: formatShortDate(new Date(r.nav_date)),
        fullDate: formatDate(new Date(r.nav_date)),
        nav_adj: parseFloat(r.nav_adj),
        nav_change: r.nav_change != null ? parseFloat(r.nav_change) : 0,
      })),
    [filtered],
  )

  const navValues = chartData.map(r => r.nav_adj).filter(Boolean)
  const minNav = navValues.length ? Math.min(...navValues) * 0.98 : 0
  const maxNav = navValues.length ? Math.max(...navValues) * 1.02 : 100

  const firstNav = chartData[0]?.nav_adj
  const lastNav = chartData[chartData.length - 1]?.nav_adj
  const totalReturn = firstNav && lastNav ? pctChange(firstNav, lastNav) : null
  const isPositive = totalReturn ? !totalReturn.startsWith('-') : null

  if (navHistory.length === 0) {
    return (
      <div className="flex items-center justify-center h-40 border border-paper-rule rounded-sm">
        <p className="font-sans text-xs text-ink-tertiary">No NAV history available</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div>
            <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
              NAV Price
            </div>
            <div className="font-sans text-[10px] text-ink-tertiary">Adjusted for dividends &amp; splits</div>
          </div>
          {totalReturn && (
            <div className={`font-mono text-sm font-semibold tabular-nums ${isPositive ? 'text-signal-pos' : 'text-signal-neg'}`}>
              {totalReturn}
            </div>
          )}
          {lastNav && (
            <div className="font-mono text-sm font-semibold text-ink-primary">
              {formatNav(lastNav)}
            </div>
          )}
        </div>
        <div className="flex gap-0.5">
          {(['1M', '3M', '6M', '1Y', '3Y', '5Y'] as Period[]).map(p => (
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

      {chartData.length < 5 ? (
        <div className="flex items-center justify-center h-40 border border-paper-rule rounded-sm">
          <p className="font-sans text-xs text-ink-tertiary">Insufficient data for selected period</p>
        </div>
      ) : (
        <div style={{ height: 200, minHeight: 200 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 32 }}>
              <XAxis
                dataKey="fullDate"
                tick={{ fontSize: 9, fill: '#94a3b8' }}
                interval="preserveStartEnd"
                tickFormatter={(_v, i) => {
                  if (i === 0 || i === chartData.length - 1) return chartData[i]?.date ?? ''
                  return ''
                }}
              />
              <YAxis
                yAxisId="nav"
                domain={[minNav, maxNav]}
                tick={{ fontSize: 9, fill: '#94a3b8' }}
                tickFormatter={v => `₹${v.toFixed(0)}`}
              />
              <YAxis
                yAxisId="change"
                orientation="right"
                tick={{ fontSize: 8, fill: '#94a3b8' }}
                tickFormatter={v => v.toFixed(1)}
                hide
              />
              <ReferenceLine yAxisId="change" y={0} stroke="#cbd5e1" strokeWidth={0.5} />
              <Tooltip content={<CustomTooltip />} />
              <Bar
                yAxisId="change"
                dataKey="nav_change"
                fill="#1D9E75"
                opacity={0.25}
                maxBarSize={4}
              />
              <Line
                yAxisId="nav"
                type="monotone"
                dataKey="nav_adj"
                stroke="#1D9E75"
                strokeWidth={1.5}
                dot={false}
                activeDot={{ r: 3 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
