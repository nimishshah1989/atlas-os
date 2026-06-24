'use client'

// StockPriceEMAChart — the stock CLOSE with EMA 20/50/200 overlays, via the Atlas
// Lightweight chart wrapper (which auto-computes the EMAs from overlays:[...]).
// Period toggle (5Y/2Y/1Y) trims the window. Source: getStockChartSeries() rows
// (postgres NUMERIC strings — coerced with Number()). Native foundation_staging.
import { useMemo, useState } from 'react'
import { AtlasLightweightChart } from '@/components/charts/AtlasLightweightChart'
import { toNumber } from '@/lib/v6/decimal'
import type { StockChartRow } from '@/lib/queries/v6/stock_lens'

type History = '5Y' | '2Y' | '1Y'
const YEARS: Record<History, number> = { '5Y': 5, '2Y': 2, '1Y': 1 }

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

export function StockPriceEMAChart({ rows, symbol }: { rows: StockChartRow[]; symbol: string }) {
  const [history, setHistory] = useState<History>('2Y')

  const points = useMemo(() => {
    const clean = rows
      .map(r => ({ time: r.date, value: toNumber(r.close) }))
      .filter((p): p is { time: string; value: number } => p.value != null && p.value > 0)
    if (clean.length === 0) return []
    const last = clean[clean.length - 1].time
    const cutoff = new Date(last + 'T00:00:00Z')
    cutoff.setUTCFullYear(cutoff.getUTCFullYear() - YEARS[history])
    const cutoffStr = cutoff.toISOString().slice(0, 10)
    return clean.filter(p => p.time >= cutoffStr)
  }, [rows, history])

  return (
    <section className="px-8 py-9 border-b border-paper-rule" aria-label="Price and EMAs">
      <div className="flex items-baseline justify-between mb-5 flex-wrap gap-3">
        <div>
          <h2 className="font-serif text-[26px] font-normal tracking-tight text-ink-primary">Price · EMA 20 / 50 / 200</h2>
          <p className="font-sans text-[13px] text-ink-tertiary max-w-[720px] leading-[1.45] mt-1">
            {symbol} daily close with the three trend EMAs. Native from foundation_staging.ohlcv_stock.
          </p>
        </div>
        <Toggle options={['5Y', '2Y', '1Y']} value={history} onChange={setHistory} />
      </div>
      {points.length > 0 ? (
        <AtlasLightweightChart
          title={`${symbol} close`}
          yLabel="₹ (close)"
          height={360}
          showLastValue
          series={[{ name: 'Close', color: 'ink', data: points, overlays: ['ema20', 'ema50', 'ema200'] }]}
        />
      ) : (
        <p className="font-sans text-[13px] text-ink-tertiary italic">No price history available.</p>
      )}
    </section>
  )
}
