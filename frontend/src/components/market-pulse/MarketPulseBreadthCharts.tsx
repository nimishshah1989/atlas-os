'use client'
// Market Pulse §3.e — breadth participation history as four small theme-aware charts
// (count of Nifty 500 names above each trend EMA + net 52-week new highs), with a
// 1Y/2Y/5Y/10Y window toggle. Counts are integers. Fed the full ~10y daily history;
// the toggle slices client-side so there's no refetch.
import { useState } from 'react'
import { AtlasLightweightChart, type SeriesColor } from '@/components/charts/AtlasLightweightChart'
import { Panel } from '../ui/Panel'
import type { BreadthRow } from '@/lib/queries/breadth'

type NumKey = 'above_21' | 'above_50' | 'above_200' | 'net_new_highs'
const CHARTS: { key: NumKey; label: string; color: SeriesColor }[] = [
  { key: 'above_21', label: 'Above 21-EMA', color: 'teal' },
  { key: 'above_50', label: 'Above 50-EMA', color: 'pos' },
  { key: 'above_200', label: 'Above 200-EMA', color: 'warn' },
  { key: 'net_new_highs', label: 'Net new highs · 52w H − L', color: 'pos' },
]

// ~252 trading days per year; "All" = the full series.
const WINDOWS: { label: string; years: number | null }[] = [
  { label: '1Y', years: 1 }, { label: '2Y', years: 2 },
  { label: '5Y', years: 5 }, { label: '10Y', years: 10 }, { label: 'All', years: null },
]

export function MarketPulseBreadthCharts({ series }: { series: BreadthRow[] }) {
  const [years, setYears] = useState<number | null>(5)
  if (series.length < 2) return null
  const sliced = years == null ? series : series.slice(-Math.round(years * 252))

  return (
    <Panel
      eyebrow="Participation"
      title="Breadth — count of Nifty 500 names"
      info={{ title: 'Breadth history', body: 'How many of the ~500 Nifty 500 constituents sit above each trend EMA, plus the net 52-week new-high count (highs − lows). Counts are instruments (integers), tracked daily over up to 10 years — rising breadth = a broadening advance. Use the window toggle to zoom the history.' }}
    >
      <div className="mb-3 flex items-center gap-2">
        <span className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">History</span>
        <div className="inline-flex rounded-tile border border-edge-rule bg-surface-inset p-0.5">
          {WINDOWS.map((w) => (
            <button key={w.label} type="button" onClick={() => setYears(w.years)}
              className={`font-num text-[10px] px-2 py-0.5 rounded-tile transition-colors ${years === w.years ? 'bg-surface-raised text-txt-1 font-semibold' : 'text-txt-3 hover:text-txt-1'}`}>
              {w.label}
            </button>
          ))}
        </div>
        <span className="font-num text-[10px] tabular-nums text-txt-3">{sliced.length.toLocaleString('en-IN')} days</span>
      </div>
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        {CHARTS.map((c) => {
          const data = sliced.map((r) => ({ time: r.date, value: r[c.key] }))
          return (
            <div key={c.key}>
              <p className="mb-1.5 font-num text-[10px] uppercase tracking-wider text-txt-3">{c.label}</p>
              <AtlasLightweightChart height={148} precision={0} series={[{ name: c.label, color: c.color, data }]} />
            </div>
          )
        })}
      </div>
    </Panel>
  )
}
