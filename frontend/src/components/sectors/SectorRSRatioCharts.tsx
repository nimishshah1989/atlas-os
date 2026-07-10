'use client'
// frontend/src/components/sectors/SectorRSRatioCharts.tsx
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
import { sectorRatioSymbol } from '@/lib/sectorTvSymbols'
import type { RatioPoint, IntradayPoint } from '@/lib/queries/sector_index_rs'

type Props = {
  sectorName: string
  indexCode: string | null
  daily: RatioPoint[]
  intraday?: IntradayPoint[]
}

// Splice today's live intraday RS points onto the Daily panel. Daily closes are
// date strings (whole-day) and intraday points are epoch seconds, so both are
// coerced to epoch seconds and merged into one strictly-ascending numeric series
// (lightweight-charts requires monotonic time). With no live tail the daily series
// is returned untouched, so overnight/weekend rendering is identical to before.
// Exported for unit testing.
export function mergeDailyIntraday(dailyTail: RatioPoint[], intraday: IntradayPoint[]): ChartPoint[] {
  if (intraday.length === 0) return dailyTail.map((p) => ({ time: p.time, value: p.value }))
  const toEpoch = (d: string) => Math.floor(Date.parse(`${d.slice(0, 10)}T00:00:00Z`) / 1000)
  const merged = new Map<number, number>()
  for (const p of dailyTail) merged.set(toEpoch(p.time), p.value)
  for (const p of intraday) merged.set(p.time, p.value) // live tick wins at its epoch
  return Array.from(merged.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([time, value]) => ({ time, value }))
}

// IST-shifted (UTC+5:30) parts of an epoch-seconds instant, for labels/keys.
const istDate = (epoch: number) => new Date((epoch + 19800) * 1000).toISOString().slice(0, 10)
const istTime = (epoch: number) => new Date((epoch + 19800) * 1000).toISOString().slice(11, 16)

// Fold today's latest live tick into the daily series as a synthetic "today" close,
// so the CURRENT week and month also reflect "now" (their last point becomes today's
// live ratio) — not just the Daily panel. Empty tail → daily untouched. Exported for
// unit testing.
export function foldLiveIntoDaily(daily: RatioPoint[], intraday: IntradayPoint[]): RatioPoint[] {
  if (intraday.length === 0) return daily
  const live = intraday[intraday.length - 1]
  return [...daily, { time: istDate(live.time), value: live.value }]
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

export function SectorRSRatioCharts({ sectorName, indexCode, daily, intraday = [] }: Props) {
  const panels = useMemo(() => {
    // Fold today's live tick into the daily series before resampling so the current
    // week and month also end on today's live value (not just the Daily panel).
    const withLive = foldLiveIntoDaily(daily, intraday)
    return {
      D: mergeDailyIntraday(daily.slice(-252), intraday), // ~1y daily + today's live tail
      W: resample(withLive, 'W').slice(-260), // ~5y, current week = today's live value
      M: resample(withLive, 'M'),             // full history, current month = today's live
    }
  }, [daily, intraday])

  if (daily.length === 0) {
    return (
      <div className="bg-surface-panel border border-edge-hair rounded-panel shadow-panel p-4 text-center text-[12px] text-txt-3">
        Relative-strength chart unavailable — no index price history mapped for {sectorName}.
      </div>
    )
  }

  const asOf = daily.at(-1)?.time?.slice(0, 10)
  // With a live tail every panel is current to "now": the Daily panel shows the
  // last tick's date + time (IST), Weekly/Monthly show today's date (their current
  // period now carries today's live value). No tail → all fall back to the EOD close.
  const liveEpoch = intraday.length ? intraday[intraday.length - 1].time : null
  const liveDate = liveEpoch != null ? istDate(liveEpoch) : undefined
  const liveDateTime = liveEpoch != null ? `${liveDate} ${istTime(liveEpoch)} IST` : undefined
  const tvSymbol = sectorRatioSymbol(sectorName)

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {PANELS.map((p) => (
          <AtlasLightweightChart
            key={p.code}
            title={`${p.label}`}
            yLabel={`${indexCode ?? sectorName} ÷ Nifty 50`}
            asOf={p.code === 'D' ? (liveDateTime ?? asOf) : (liveDate ?? asOf)}
            height={320}
            showLastValue
            series={[{ name: `${sectorName} RS`, data: panels[p.code], color: 'teal', lineWidth: 2 }]}
          />
        ))}
      </div>
      <p className="font-sans text-[11px] text-txt-3 mt-3">
        Ratio of the sector index to Nifty 50 (rising = outperforming), from daily index closes.
        {tvSymbol && (
          <>
            {' '}
            <a
              href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvSymbol)}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand hover:underline"
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
