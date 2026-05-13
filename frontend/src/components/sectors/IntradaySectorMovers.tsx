'use client'
// allow-large: single cohesive intraday widget — isMarketOpen + LiveDot + SkeletonRows + main export all belong in one file

import { useEffect, useRef, useState } from 'react'
import { TrendingUp } from 'lucide-react'

// Market hours gate (IST = UTC+5:30)
function isMarketOpen(): boolean {
  const now = new Date()
  const utcMinutes = now.getUTCHours() * 60 + now.getUTCMinutes()
  const istMinutes = utcMinutes + 330 // UTC+5:30
  const dayOfWeek = new Date(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate() + Math.floor(istMinutes / 1440),
  ).getDay()
  if (dayOfWeek === 0 || dayOfWeek === 6) return false
  const istDayMinutes = istMinutes % 1440
  return istDayMinutes >= 555 && istDayMinutes <= 935
}

// Types
interface SectorMover {
  sector: string
  avg_return_since_open: string
  stock_count: number
}

interface SectorMoversData {
  data: SectorMover[]
  meta: {
    fetched_at?: string
    note?: string
    sector_count?: number
    data_as_of?: string
  }
}

type LiveStatus = 'live' | 'waiting' | 'closed'

// Live indicator dot
function LiveDot({ status }: { status: LiveStatus }) {
  if (status === 'live') {
    return (
      <span className="flex items-center gap-1">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-signal-pos opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-signal-pos" />
        </span>
        <span className="font-sans text-[10px] font-semibold text-signal-pos uppercase tracking-wider">
          LIVE
        </span>
      </span>
    )
  }
  if (status === 'waiting') {
    return (
      <span className="flex items-center gap-1">
        <span className="h-2 w-2 rounded-full bg-signal-warn inline-block" />
        <span className="font-sans text-[10px] font-semibold text-signal-warn uppercase tracking-wider">
          Waiting for data
        </span>
      </span>
    )
  }
  return (
    <span className="flex items-center gap-1">
      <span className="h-2 w-2 rounded-full bg-ink-tertiary inline-block" />
      <span className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
        Market closed
      </span>
    </span>
  )
}

// Skeleton loader
function SkeletonRows() {
  return (
    <>
      {[1, 2, 3].map((i) => (
        <div key={i} className="flex items-center gap-3 py-1.5 border-b border-paper-rule/50 last:border-0">
          <div className="h-3 w-28 bg-paper-rule rounded animate-pulse shrink-0" />
          <div className="flex-1 h-1.5 bg-paper-rule/50 rounded-full animate-pulse" />
          <div className="h-3 w-14 bg-paper-rule rounded animate-pulse shrink-0" />
          <div className="h-3 w-16 bg-paper-rule rounded animate-pulse shrink-0" />
        </div>
      ))}
    </>
  )
}

// Main component
export function IntradaySectorMovers() {
  const [result, setResult] = useState<SectorMoversData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [marketOpen] = useState(() => isMarketOpen())
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  async function fetchMovers(): Promise<void> {
    try {
      const res = await fetch('/api/intraday?endpoint=sector-movers')
      if (!res.ok) {
        setError(true)
        return
      }
      const json = (await res.json()) as SectorMoversData
      setResult(json)
      setError(false)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!marketOpen) {
      setLoading(false)
      return
    }
    void fetchMovers()
    intervalRef.current = setInterval(() => void fetchMovers(), 30_000)
    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [marketOpen])

  // Determine live status
  let liveStatus: LiveStatus = 'closed'
  if (marketOpen) {
    liveStatus = result && result.data.length > 0 ? 'live' : 'waiting'
  }

  return (
    <div className="border border-paper-rule rounded-sm">
      {/* Header */}
      <div className="px-4 py-3 border-b border-paper-rule flex items-center gap-2">
        <TrendingUp className="w-3.5 h-3.5 text-teal" />
        <span className="font-sans text-xs font-semibold text-ink-primary uppercase tracking-wide">
          Sector Movers — Intraday
        </span>
        <span className="ml-auto">
          <LiveDot status={liveStatus} />
        </span>
      </div>

      {/* Body */}
      <div className="px-4 py-3">
        {error ? (
          <p className="font-sans text-xs text-signal-neg py-1">
            Unable to load sector movers
          </p>
        ) : !marketOpen ? (
          <p className="font-sans text-xs text-ink-tertiary py-1">
            Intraday sector data available 09:15–15:35 IST
          </p>
        ) : loading ? (
          <SkeletonRows />
        ) : result && result.data.length === 0 ? (
          <p className="font-sans text-xs text-ink-tertiary py-1">
            {result.meta.note ?? 'Waiting for first bar...'}
          </p>
        ) : result ? (
          <div>
            {result.data.map((row) => {
              const pct = Number(row.avg_return_since_open) * 100
              const sign = pct >= 0 ? '+' : ''
              const barWidth = Math.min(Math.abs(pct) / 2 * 100, 100)
              const barColor = pct >= 0 ? 'bg-signal-pos' : 'bg-signal-neg'
              const textColor = pct >= 0 ? 'text-signal-pos' : 'text-signal-neg'
              return (
                <div
                  key={row.sector}
                  className="flex items-center gap-3 py-1.5 border-b border-paper-rule/50 last:border-0"
                >
                  <span className="font-sans text-xs text-ink-primary w-28 shrink-0 truncate">
                    {row.sector}
                  </span>
                  <div className="flex-1 h-1.5 bg-paper-rule rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${barColor}`}
                      style={{ width: `${barWidth}%` }}
                    />
                  </div>
                  <span
                    className={`font-mono text-xs tabular-nums font-semibold ${textColor} w-14 text-right shrink-0`}
                  >
                    {sign}{pct.toFixed(2)}%
                  </span>
                  <span className="font-mono text-[10px] text-ink-tertiary tabular-nums w-16 text-right shrink-0">
                    {row.stock_count} stocks
                  </span>
                </div>
              )
            })}
          </div>
        ) : null}
      </div>
    </div>
  )
}
