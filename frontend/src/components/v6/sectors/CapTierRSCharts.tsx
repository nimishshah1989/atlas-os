'use client'

// CapTierRSCharts — relative strength of each cap tier vs Nifty 500, as line charts via
// TradingView Lightweight Charts. Each line = (tier index ÷ Nifty 500), rebased to 100 at
// the start of the selected window so "above 100 = outperforming Nifty 500". Shared period
// (10Y/5Y/2Y) + frequency (1D/1W/1M) toggles. Native foundation_staging.index_prices.

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
    <div className="inline-flex rounded-sm border border-paper-rule overflow-hidden">
      {options.map(o => (
        <button key={o} onClick={() => onChange(o)}
          className={`px-2 py-0.5 font-sans text-[10px] tracking-wide transition-colors ${
            o === value ? 'bg-ink-primary text-paper' : 'bg-paper text-ink-tertiary hover:text-ink-secondary'}`}>
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
    <section className="px-8 py-10 border-b border-paper-rule" aria-label="Cap-tier relative strength">
      <div className="flex items-baseline justify-between mb-5 flex-wrap gap-3">
        <div>
          <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary">Cap-tier relative strength</h2>
          <p className="font-sans text-[13px] text-ink-tertiary max-w-[720px] leading-[1.45] mt-1">
            Each tier index ÷ Nifty 500, rebased to 100 at window start — above 100 = outperforming the broad market.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Toggle options={['10Y', '5Y', '2Y']} value={history} onChange={setHistory} />
          <Toggle options={['1D', '1W', '1M']} value={freq} onChange={setFreq} />
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {rebased.map(t => (
          <AtlasLightweightChart key={t.field} title={t.label} yLabel="RS vs Nifty 500 (=100)"
            height={200} showLastValue series={[{ name: t.label, color: t.color, data: t.points }]} />
        ))}
      </div>
    </section>
  )
}
