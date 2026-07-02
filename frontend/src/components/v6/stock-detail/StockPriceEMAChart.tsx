'use client'

// StockPriceEMAChart — the stock CLOSE with EMA 20/50/200 overlays, via the Atlas
// Lightweight chart wrapper (theme-aware; auto-computes the EMAs from overlays:[...]).
// Period toggle (5Y/2Y/1Y) trims the window. Native atlas_foundation.
import { useMemo, useState } from 'react'
import { AtlasLightweightChart } from '@/components/charts/AtlasLightweightChart'
import { toNumber } from '@/lib/v6/decimal'
import type { StockChartRow } from '@/lib/queries/v6/stock_lens'

type History = '5Y' | '2Y' | '1Y'
const YEARS: Record<History, number> = { '5Y': 5, '2Y': 2, '1Y': 1 }

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

export function StockPriceEMAChart({ rows, symbol }: { rows: StockChartRow[]; symbol: string }) {
  const [history, setHistory] = useState<History>('2Y')

  const points = useMemo(() => {
    const clean = rows
      .map((r) => ({ time: r.date, value: toNumber(r.close) }))
      .filter((p): p is { time: string; value: number } => p.value != null && p.value > 0)
    if (clean.length === 0) return []
    const last = clean[clean.length - 1].time
    const cutoff = new Date(last + 'T00:00:00Z')
    cutoff.setUTCFullYear(cutoff.getUTCFullYear() - YEARS[history])
    const cutoffStr = cutoff.toISOString().slice(0, 10)
    return clean.filter((p) => p.time >= cutoffStr)
  }, [rows, history])

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Trend</p>
          <h2 className="font-display text-[18px] font-medium text-txt-1">Price · EMA 20 / 50 / 200</h2>
          <p className="mt-0.5 max-w-[640px] font-sans text-[12px] text-txt-3">{symbol} daily close with the three trend EMAs · atlas_foundation.ohlcv_stock.</p>
        </div>
        <Toggle options={['5Y', '2Y', '1Y']} value={history} onChange={setHistory} />
      </div>
      {points.length > 0 ? (
        <AtlasLightweightChart yLabel="₹ (close)" height={360} showLastValue
          series={[{ name: 'Close', color: 'ink', data: points, overlays: ['ema20', 'ema50', 'ema200'] }]} />
      ) : (
        <p className="font-sans text-[13px] italic text-txt-3">No price history available.</p>
      )}
    </div>
  )
}
