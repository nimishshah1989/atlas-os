'use client'

// StockRSChart — relative strength of the stock vs a baseline, rebased to 100 at the
// start of the selected window (above 100 = outperforming since window start). Baseline
// toggle (Nifty 50 / Nifty 500). EMA 20/50/200 overlaid. Theme-aware Atlas Lightweight
// wrapper. Native atlas_foundation via getStockChartSeries().
import { useMemo, useState } from 'react'
import { AtlasLightweightChart } from '@/components/charts/AtlasLightweightChart'
import { toNumber } from '@/lib/decimal'
import type { StockChartRow } from '@/lib/queries/stock_lens'

type History = '5Y' | '2Y' | '1Y'
type Baseline = 'n50' | 'n500'
const YEARS: Record<History, number> = { '5Y': 5, '2Y': 2, '1Y': 1 }
const BASE_LABEL: Record<Baseline, string> = { n50: 'Nifty 50', n500: 'Nifty 500' }
const BASE_FIELD: Record<Baseline, keyof StockChartRow> = { n50: 'rs_n50', n500: 'rs_n500' }

function Toggle<T extends string>({ options, value, onChange, labelFor }: { options: T[]; value: T; onChange: (v: T) => void; labelFor?: (v: T) => string }) {
  return (
    <div className="inline-flex overflow-hidden rounded-tile border border-edge-rule">
      {options.map((o) => (
        <button key={o} onClick={() => onChange(o)}
          className={`px-2 py-0.5 font-num text-[10px] tracking-wide transition-colors ${
            o === value ? 'bg-surface-raised text-txt-1' : 'bg-surface-panel text-txt-3 hover:text-txt-1'}`}>
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
    const dated = rows.filter((r) => r[field] != null)
    if (dated.length === 0) return []
    const last = dated[dated.length - 1].date
    const cutoff = new Date(last + 'T00:00:00Z')
    cutoff.setUTCFullYear(cutoff.getUTCFullYear() - YEARS[history])
    const cutoffStr = cutoff.toISOString().slice(0, 10)

    const win = dated
      .filter((r) => r.date >= cutoffStr)
      .map((r) => ({ time: r.date, raw: toNumber(r[field] as string) }))
      .filter((p): p is { time: string; raw: number } => p.raw != null && p.raw > 0)
    if (win.length === 0) return []
    const base = win[0].raw
    return win.map((p) => ({ time: p.time, value: (p.raw / base) * 100 }))
  }, [rows, history, baseline])

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Relative strength</p>
          <h2 className="font-display text-[18px] font-medium text-txt-1">RS vs baseline · rebased to 100</h2>
          <p className="mt-0.5 max-w-[640px] font-sans text-[12px] text-txt-3">{symbol} ÷ {BASE_LABEL[baseline]}, rebased to 100 at window start — above 100 = outperforming since then.</p>
        </div>
        <div className="flex items-center gap-2">
          <Toggle options={['n50', 'n500'] as Baseline[]} value={baseline} onChange={setBaseline} labelFor={(b) => BASE_LABEL[b]} />
          <Toggle options={['5Y', '2Y', '1Y']} value={history} onChange={setHistory} />
        </div>
      </div>
      {points.length > 0 ? (
        <AtlasLightweightChart yLabel={`RS vs ${BASE_LABEL[baseline]} (=100)`} height={360} showLastValue
          series={[{ name: `RS vs ${BASE_LABEL[baseline]}`, color: 'teal', data: points, overlays: ['ema20', 'ema50', 'ema200'] }]} />
      ) : (
        <p className="font-sans text-[13px] italic text-txt-3">No relative-strength history available for {BASE_LABEL[baseline]}.</p>
      )}
    </div>
  )
}
