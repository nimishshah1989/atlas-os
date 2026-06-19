'use client'
// frontend/src/components/v6/sectors/SectorRSRatioCharts.tsx
//
// Three relative-strength ratio charts (sector index ÷ Nifty 50) side by side at
// Daily / Weekly / Monthly resolutions. A rising line = sector outperforming.
//
// Rendered with Atlas's TradingView Lightweight Charts wrapper (AtlasLightweightChart),
// fed by a ratio series we compute from de_index_prices. This avoids TradingView's
// data-gated public embed widget (which refuses NSE index/ratio symbols for
// anonymous viewers) while still being a genuine TradingView chart. A link opens
// the live interactive TradingView ratio chart for users who want it.

import { useMemo } from 'react'
import { AtlasLightweightChart, type ChartPoint } from '@/components/charts/AtlasLightweightChart'
import { sectorRatioSymbol } from '@/lib/v6/sectorTvSymbols'
import type { RatioPoint } from '@/lib/queries/v6/sector_index_rs'

type Props = {
  sectorName: string
  indexCode: string | null
  daily: RatioPoint[]
}

// Resample a daily series to the last point of each ISO-week or calendar-month.
// Exported for unit testing.
export function resample(daily: RatioPoint[], mode: 'W' | 'M'): ChartPoint[] {
  const byKey = new Map<string, RatioPoint>()
  for (const p of daily) {
    const key = mode === 'M' ? p.time.slice(0, 7) : isoWeekKey(p.time)
    byKey.set(key, p) // input is sorted ASC → last write wins (period close)
  }
  return Array.from(byKey.values())
}

function isoWeekKey(iso: string): string {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`)
  const day = (d.getUTCDay() + 6) % 7 // Mon=0
  d.setUTCDate(d.getUTCDate() - day + 3) // nearest Thursday
  const firstThu = new Date(Date.UTC(d.getUTCFullYear(), 0, 4))
  const week = 1 + Math.round(((d.getTime() - firstThu.getTime()) / 86400000 - 3 + ((firstThu.getUTCDay() + 6) % 7)) / 7)
  return `${d.getUTCFullYear()}-W${String(week).padStart(2, '0')}`
}

const PANELS: { code: 'D' | 'W' | 'M'; label: string }[] = [
  { code: 'D', label: 'Daily' },
  { code: 'W', label: 'Weekly' },
  { code: 'M', label: 'Monthly' },
]

export function SectorRSRatioCharts({ sectorName, indexCode, daily }: Props) {
  const panels = useMemo(() => {
    const weekly = resample(daily, 'W')
    const monthly = resample(daily, 'M')
    return {
      D: daily.slice(-252).map((p) => ({ time: p.time, value: p.value })) as ChartPoint[], // ~1y
      W: weekly.slice(-260), // ~5y
      M: monthly,            // full history
    }
  }, [daily])

  if (daily.length === 0) {
    return (
      <div className="bg-paper-soft border border-paper-rule rounded-[2px] p-4 text-center text-[12px] text-ink-tertiary">
        Relative-strength chart unavailable — no index price history mapped for {sectorName}.
      </div>
    )
  }

  const asOf = daily.at(-1)?.time?.slice(0, 10)
  const tvSymbol = sectorRatioSymbol(sectorName)

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {PANELS.map((p) => (
          <AtlasLightweightChart
            key={p.code}
            title={`${p.label}`}
            yLabel={`${indexCode ?? sectorName} ÷ Nifty 50`}
            asOf={asOf}
            height={320}
            showLastValue
            series={[{ name: `${sectorName} RS`, data: panels[p.code], color: 'teal', lineWidth: 2 }]}
          />
        ))}
      </div>
      <p className="font-sans text-[11px] text-ink-tertiary mt-3">
        Ratio of the sector index to Nifty 50 (rising = outperforming), from daily index closes.
        {tvSymbol && (
          <>
            {' '}
            <a
              href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvSymbol)}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-teal hover:underline"
            >
              Open live on TradingView ↗
            </a>
          </>
        )}
      </p>
    </>
  )
}

export default SectorRSRatioCharts
