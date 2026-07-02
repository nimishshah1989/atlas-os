'use client'

// CapTierRSCharts — relative strength of each cap tier vs Nifty 500, as line charts via
// TradingView Lightweight Charts. Each line = (tier index ÷ Nifty 500), rebased to 100 at
// the start of the selected window so "above 100 = outperforming Nifty 500". Shared period
// (10Y/5Y/2Y) + frequency (1D/1W/1M) toggles. Native atlas_foundation.index_prices.

import { useMemo, useState } from 'react'
import { AtlasLightweightChart } from '@/components/charts/AtlasLightweightChart'
import type { CapTierRSRow } from '@/lib/queries/v6/rs_charts'

type History = '10Y' | '5Y' | '2Y'
type Freq = '1D' | '1W' | '1M'
const YEARS: Record<History, number> = { '10Y': 10, '5Y': 5, '2Y': 2 }

const TIERS: { field: keyof CapTierRSRow; label: string; color: 'teal' | 'pos' | 'warn' | 'neg' }[] = [
  { field: 'sc', label: 'Smallcap 250 vs Nifty 500', color: 'teal' },
  { field: 'mc', label: 'Midcap 150 vs Nifty 500', color: 'pos' },
  { field: 'micro', label: 'Microcap 250 vs Nifty 500', color: 'warn' },
  { field: 'junior', label: 'Next 50 (juniorBeES) vs Nifty 500', color: 'neg' },
]

function periodKey(d: string, freq: Freq): string {
  if (freq === '1M') return d.slice(0, 7)
  const dt = new Date(d + 'T00:00:00Z')
  const jan1 = Date.UTC(dt.getUTCFullYear(), 0, 1)
  return `${dt.getUTCFullYear()}-W${Math.ceil(((dt.getTime() - jan1) / 86_400_000 + 1) / 7)}`
}
function resample(rows: CapTierRSRow[], freq: Freq): CapTierRSRow[] {
  if (freq === '1D') return rows
  const m = new Map<string, CapTierRSRow>()
  for (const r of rows) m.set(periodKey(r.date, freq), r)
  return Array.from(m.values())
}

function Toggle<T extends string>({ options, value, onChange }: { options: T[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex rounded-tile border border-edge-rule overflow-hidden">
      {options.map(o => (
        <button key={o} onClick={() => onChange(o)}
          className={`px-2 py-0.5 font-num text-[10px] tracking-wide transition-colors ${
            o === value ? 'bg-brand-soft text-brand' : 'bg-surface-raised text-txt-3 hover:text-txt-2'}`}>
          {o}
        </button>
      ))}
    </div>
  )
}

export function CapTierRSCharts({ series }: { series: CapTierRSRow[] }) {
  const [history, setHistory] = useState<History>('5Y')
  const [freq, setFreq] = useState<Freq>('1W')

  const data = useMemo(() => {
    if (series.length === 0) return []
    const last = series[series.length - 1].date
    const cutoff = new Date(last + 'T00:00:00Z')
    cutoff.setUTCFullYear(cutoff.getUTCFullYear() - YEARS[history])
    const cutoffStr = cutoff.toISOString().slice(0, 10)
    return resample(series.filter(r => r.date >= cutoffStr), freq)
  }, [series, history, freq])

  // rebase each tier to 100 at the first non-null point in the window
  const rebased = useMemo(() => {
    const base: Partial<Record<keyof CapTierRSRow, number>> = {}
    for (const t of TIERS) {
      const first = data.find(r => r[t.field] != null)
      if (first) base[t.field] = parseFloat(first[t.field] as string)
    }
    return TIERS.map(t => ({
      ...t,
      points: data
        .filter(r => r[t.field] != null && base[t.field])
        .map(r => ({ time: r.date, value: (parseFloat(r[t.field] as string) / (base[t.field] as number)) * 100 })),
    }))
  }, [data])

  return (
    <section className="rounded-panel border border-edge-hair bg-surface-panel shadow-panel" aria-label="Cap-tier relative strength">
      <header className="flex items-baseline justify-between gap-3 flex-wrap border-b border-edge-hair px-5 py-3.5">
        <div className="min-w-0">
          <div className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Cap tiers</div>
          <h2 className="font-display text-[15px] font-medium leading-tight text-txt-1">Cap-tier relative strength</h2>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Toggle options={['10Y', '5Y', '2Y']} value={history} onChange={setHistory} />
          <Toggle options={['1D', '1W', '1M']} value={freq} onChange={setFreq} />
        </div>
      </header>
      <div className="px-5 py-4">
        <p className="font-sans text-[12.5px] text-txt-2 max-w-[760px] leading-[1.5] mb-4">
          Each tier index ÷ Nifty 500, <strong className="text-txt-1 font-medium">rebased to 100 at the window start</strong>.
          The latest plotted value is the running outperformance: e.g. 123.7 = +23.7% vs Nifty 500 over the window; below 100 = lagging.
        </p>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {rebased.map(t => {
            const latest = t.points.length ? t.points[t.points.length - 1].value : null
            return (
              <div key={t.field}>
                <AtlasLightweightChart title={t.label} yLabel="RS vs Nifty 500 (=100)"
                  height={200} showLastValue series={[{ name: t.label, color: t.color, data: t.points }]} />
                {latest != null && (
                  <p className="font-num text-[11px] tabular-nums text-txt-3 mt-1">
                    latest <span className="text-txt-1 font-semibold">{latest.toFixed(1)}</span> ={' '}
                    <span className={latest >= 100 ? 'text-sig-pos' : 'text-sig-neg'}>
                      {latest >= 100 ? '+' : ''}{(latest - 100).toFixed(1)}%
                    </span>{' '}vs Nifty 500 since window start
                  </p>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
