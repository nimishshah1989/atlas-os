'use client'
import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { IndicatorChart } from '@/components/regime/IndicatorChart'
import { rangeToDays, type TimeRange } from '@/lib/time-range'
import type { SectorMetricHistoryRow } from '@/lib/queries/sectors'

type Props = {
  sectorName: string
  range: string
  onClose: () => void
}

export function SectorDrawer({ sectorName, range, onClose }: Props) {
  const [history, setHistory] = useState<SectorMetricHistoryRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    setLoading(true)
    setError(false)
    const days = rangeToDays(range as TimeRange)
    fetch(`/api/sectors/${encodeURIComponent(sectorName)}/history?days=${days}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((data: SectorMetricHistoryRow[]) => {
        setHistory(data)
        setLoading(false)
      })
      .catch(() => {
        setError(true)
        setLoading(false)
      })
  }, [sectorName, range])

  const dateStr = (row: SectorMetricHistoryRow): string =>
    row.date instanceof Date
      ? row.date.toISOString().slice(0, 10)
      : String(row.date).slice(0, 10)

  const rsData       = history.map(r => ({ date: dateStr(r), value: r.bottomup_rs_3m_nifty500 != null ? parseFloat(r.bottomup_rs_3m_nifty500) : null }))
  const breadthData  = history.map(r => ({ date: dateStr(r), value: r.participation_50        != null ? parseFloat(r.participation_50)        : null }))
  const rsParticData = history.map(r => ({ date: dateStr(r), value: r.participation_rs        != null ? parseFloat(r.participation_rs)        : null }))

  const latest = history[history.length - 1]

  const currentRS       = latest?.bottomup_rs_3m_nifty500 != null ? `${(parseFloat(latest.bottomup_rs_3m_nifty500) * 100).toFixed(1)}%` : '—'
  const currentBreadth  = latest?.participation_50        != null ? `${(parseFloat(latest.participation_50) * 100).toFixed(0)}%`        : '—'
  const currentRSPartic = latest?.participation_rs        != null ? `${(parseFloat(latest.participation_rs) * 100).toFixed(0)}%`        : '—'

  const rsBullish       = latest?.bottomup_rs_3m_nifty500 != null ? parseFloat(latest.bottomup_rs_3m_nifty500) > 0  : null
  const breadthBullish  = latest?.participation_50        != null ? parseFloat(latest.participation_50) > 0.5       : null
  const rsParticBullish = latest?.participation_rs        != null ? parseFloat(latest.participation_rs) > 0.5       : null

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-40 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed right-0 top-0 h-full w-[480px] bg-paper border-l border-paper-rule z-50 overflow-y-auto shadow-xl">
        <div className="sticky top-0 bg-paper border-b border-paper-rule px-6 py-4 flex items-center justify-between">
          <div>
            <h2 className="font-sans text-sm font-semibold text-ink-primary">{sectorName}</h2>
            <p className="font-sans text-xs text-ink-tertiary mt-0.5">{range} metric history</p>
          </div>
          <button
            onClick={onClose}
            className="text-ink-tertiary hover:text-ink-primary transition-colors"
            aria-label="Close drawer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {loading ? (
          <div className="p-6 space-y-4">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-48 bg-paper-rule/20 rounded-sm animate-pulse" />
            ))}
          </div>
        ) : error ? (
          <div className="p-6">
            <p className="font-sans text-xs text-signal-neg">Failed to load sector history. Please try again.</p>
          </div>
        ) : (
          <div className="p-6 space-y-4">
            <IndicatorChart
              title="Relative Strength vs Nifty 500 (3M)"
              description="How this sector's stocks are performing relative to the broader Nifty 500 universe over a rolling 3-month window. Positive means sector leadership; negative means the sector is lagging the index."
              currentValue={currentRS}
              isBullish={rsBullish}
              data={rsData}
              refLine={0}
              refLabel="0"
              variant="area"
              yFormat="pct"
            />
            <IndicatorChart
              title="Breadth — % Stocks Above 50-Day EMA"
              description="Percentage of stocks within this sector currently trading above their 50-day exponential moving average. Above 50% means the majority of the sector is in a medium-term uptrend."
              currentValue={currentBreadth}
              isBullish={breadthBullish}
              data={breadthData}
              refLine={0.5}
              refLabel="50%"
              variant="area"
              yFormat="pct"
            />
            <IndicatorChart
              title="RS Participation — % Stocks with Positive RS"
              description="Fraction of the sector's stocks outperforming the Nifty 500 on a relative strength basis. High RS participation means leadership is broad, not concentrated in 1-2 names."
              currentValue={currentRSPartic}
              isBullish={rsParticBullish}
              data={rsParticData}
              refLine={0.5}
              refLabel="50%"
              variant="area"
              yFormat="pct"
            />
          </div>
        )}
      </div>
    </>
  )
}
