'use client'

// StockRSChart — relative strength of the stock vs a baseline, as a line chart via the
// Atlas Lightweight wrapper. RS = (stock close ÷ baseline close), rebased to 100 at the
// start of the selected window, so "above 100 = outperforming the baseline since window
// start". Baseline toggle (Nifty 50 / Nifty 500) reads rs_n50 / rs_n500. EMA 20/50/200
// overlays auto-computed by the chart. Period toggle (5Y/2Y/1Y). postgres NUMERIC strings
// coerced with Number(). Native foundation_staging via getStockChartSeries().
import { useMemo, useState } from 'react'
import { AtlasLightweightChart } from '@/components/charts/AtlasLightweightChart'
import { toNumber } from '@/lib/v6/decimal'
import type { StockChartRow } from '@/lib/queries/v6/stock_lens'

type History = '5Y' | '2Y' | '1Y'
type Baseline = 'n50' | 'n500'
const YEARS: Record<History, number> = { '5Y': 5, '2Y': 2, '1Y': 1 }
const BASE_LABEL: Record<Baseline, string> = { n50: 'Nifty 50', n500: 'Nifty 500' }
const BASE_FIELD: Record<Baseline, keyof StockChartRow> = { n50: 'rs_n50', n500: 'rs_n500' }

function Toggle<T extends string>({ options, value, onChange, labelFor }: {
  options: T[]; value: T; onChange: (v: T) => void; labelFor?: (v: T) => string
}) {
  return (
    <div className="inline-flex rounded-sm border border-paper-rule overflow-hidden">
      {options.map(o => (
        <button key={o} onClick={() => onChange(o)}
          className={`px-2 py-0.5 font-sans text-[10px] tracking-wide transition-colors ${
            o === value ? 'bg-ink-primary text-paper' : 'bg-paper text-ink-tertiary hover:text-ink-secondary'}`}>
          {labelFor ? labelFor(o) : o}
        </button>
      ))}
    </div>
  )
}

export function StockRSChart({ rows, symbol }: { rows: StockChartRow[]; symbol: string }) {
  const [history, setHistory] = useState<History>('2Y')
  const [baseline, setBaseline] = useState<Baseline>('n500')

  const points = useMemo(() => {
    const field = BASE_FIELD[baseline]
    // window cutoff from the latest available date
    const dated = rows.filter(r => r[field] != null)
    if (dated.length === 0) return []
    const last = dated[dated.length - 1].date
    const cutoff = new Date(last + 'T00:00:00Z')
    cutoff.setUTCFullYear(cutoff.getUTCFullYear() - YEARS[history])
    const cutoffStr = cutoff.toISOString().slice(0, 10)

    const win = dated
      .filter(r => r.date >= cutoffStr)
      .map(r => ({ time: r.date, raw: toNumber(r[field] as string) }))
      .filter((p): p is { time: string; raw: number } => p.raw != null && p.raw > 0)
    if (win.length === 0) return []
    // rebase to 100 at the first point in the window
    const base = win[0].raw
    return win.map(p => ({ time: p.time, value: (p.raw / base) * 100 }))
  }, [rows, history, baseline])

  return (
    <section className="px-8 py-9 border-b border-paper-rule" aria-label="Relative strength chart">
      <div className="flex items-baseline justify-between mb-5 flex-wrap gap-3">
        <div>
          <h2 className="font-serif text-[26px] font-normal tracking-tight text-ink-primary">Relative strength · rebased to 100</h2>
          <p className="font-sans text-[13px] text-ink-tertiary max-w-[720px] leading-[1.45] mt-1">
            {symbol} ÷ {BASE_LABEL[baseline]}, rebased to 100 at window start — above 100 = outperforming since then. EMA 20/50/200 overlaid.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Toggle options={['n50', 'n500'] as Baseline[]} value={baseline} onChange={setBaseline} labelFor={b => BASE_LABEL[b]} />
          <Toggle options={['5Y', '2Y', '1Y']} value={history} onChange={setHistory} />
        </div>
      </div>
      {points.length > 0 ? (
        <AtlasLightweightChart
          title={`${symbol} vs ${BASE_LABEL[baseline]}`}
          yLabel={`RS vs ${BASE_LABEL[baseline]} (=100)`}
          height={360}
          showLastValue
          series={[{ name: `RS vs ${BASE_LABEL[baseline]}`, color: 'teal', data: points, overlays: ['ema20', 'ema50', 'ema200'] }]}
        />
      ) : (
        <p className="font-sans text-[13px] text-ink-tertiary italic">No relative-strength history available for {BASE_LABEL[baseline]}.</p>
      )}
    </section>
  )
}
