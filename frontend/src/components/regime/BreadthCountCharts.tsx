'use client'

// BreadthCountCharts — the 3 Nifty-500 breadth count charts for Markets Today
// (markets-today-redesign spec C). Absolute COUNTS of Nifty-500 stocks above the
// 21 / 50 / 200-EMA, as line charts via TradingView Lightweight Charts. Shared
// history toggle (10y / 5y / 2y) + frequency toggle (1d / 1w / 1m). Data is the
// native foundation_staging.breadth_nifty500_daily series passed from the server.

import { useMemo, useState } from 'react'
import { AtlasLightweightChart } from '@/components/charts/AtlasLightweightChart'
import type { BreadthRow } from '@/lib/queries/v6/breadth'

type History = '10Y' | '5Y' | '2Y'
type Freq = '1D' | '1W' | '1M'

const YEARS: Record<History, number> = { '10Y': 10, '5Y': 5, '2Y': 2 }

function periodKey(d: string, freq: Freq): string {
  if (freq === '1M') return d.slice(0, 7) // YYYY-MM
  // ISO-ish week bucket (year + week number)
  const dt = new Date(d + 'T00:00:00Z')
  const jan1 = Date.UTC(dt.getUTCFullYear(), 0, 1)
  const week = Math.ceil(((dt.getTime() - jan1) / 86_400_000 + 1) / 7)
  return `${dt.getUTCFullYear()}-W${week}`
}

// Keep the LAST observation of each week / month (rows arrive ASC by date).
function resample(rows: BreadthRow[], freq: Freq): BreadthRow[] {
  if (freq === '1D') return rows
  const lastByKey = new Map<string, BreadthRow>()
  for (const r of rows) lastByKey.set(periodKey(r.date, freq), r)
  return Array.from(lastByKey.values())
}

function Toggle<T extends string>({ options, value, onChange }: {
  options: T[]; value: T; onChange: (v: T) => void
}) {
  return (
    <div className="inline-flex rounded-sm border border-paper-rule overflow-hidden">
      {options.map(o => (
        <button
          key={o}
          onClick={() => onChange(o)}
          className={`px-2 py-0.5 font-sans text-[10px] tracking-wide transition-colors ${
            o === value ? 'bg-ink-primary text-paper' : 'bg-paper text-ink-tertiary hover:text-ink-secondary'
          }`}
        >
          {o}
        </button>
      ))}
    </div>
  )
}

const CHARTS: { field: keyof BreadthRow; label: string; color: 'teal' | 'pos' | 'ink' | 'warn' }[] = [
  { field: 'above_21', label: 'Above 21-EMA', color: 'teal' },
  { field: 'above_50', label: 'Above 50-EMA', color: 'pos' },
  { field: 'above_200', label: 'Above 200-EMA', color: 'ink' },
  { field: 'gc_50_200', label: '50-EMA > 200-EMA (golden cross)', color: 'warn' },
]

export function BreadthCountCharts({ series }: { series: BreadthRow[] }) {
  const [history, setHistory] = useState<History>('10Y')
  const [freq, setFreq] = useState<Freq>('1W')

  const data = useMemo(() => {
    if (series.length === 0) return []
    const last = series[series.length - 1].date
    const cutoff = new Date(last + 'T00:00:00Z')
    cutoff.setUTCFullYear(cutoff.getUTCFullYear() - YEARS[history])
    const cutoffStr = cutoff.toISOString().slice(0, 10)
    return resample(series.filter(r => r.date >= cutoffStr), freq)
  }, [series, history, freq])

  const latest = series.length ? series[series.length - 1] : null

  return (
    <section className="px-6 py-6 border-b border-paper-rule">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
            Market Breadth · Nifty 500 — count above EMA
          </h2>
          {latest && (
            <div className="font-sans text-[10px] text-ink-tertiary/70 mt-0.5">
              of {latest.n_members} members · {latest.above_21} &gt; 21-EMA · {latest.above_50} &gt; 50-EMA · {latest.above_200} &gt; 200-EMA · {latest.gc_50_200} golden-cross
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Toggle options={['10Y', '5Y', '2Y']} value={history} onChange={setHistory} />
          <Toggle options={['1D', '1W', '1M']} value={freq} onChange={setFreq} />
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {CHARTS.map(c => (
          <AtlasLightweightChart
            key={c.field}
            title={c.label}
            yLabel="# of Nifty 500"
            height={200}
            showLastValue
            series={[{
              name: c.label,
              color: c.color,
              data: data.map(r => ({ time: r.date, value: Number(r[c.field]) })),
            }]}
          />
        ))}
      </div>
    </section>
  )
}
