'use client'

import { useEffect, useRef, useState } from 'react'
import { Activity } from 'lucide-react'
import { RSPctileBar } from '@/lib/stock-formatters'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface IntradayLeader {
  instrument_id: string
  symbol: string
  sector: string
  tier: string
  close: number
  ema_20: number | null
  ema_50: number | null
  rs_vs_nifty: number | null
  rs_pctile_intraday: number | null
  bar_time: string
}

interface IntradayLeadersMeta {
  data_as_of?: string
  note?: string
  fetched_at?: string
  source?: string
  row_count?: number
}

interface IntradayLeadersData {
  data: IntradayLeader[]
  meta: IntradayLeadersMeta
}

// ---------------------------------------------------------------------------
// Market hours gate (IST = UTC+5:30)
// ---------------------------------------------------------------------------

function isMarketOpen(): boolean {
  const now = new Date()
  const utcMinutes = now.getUTCHours() * 60 + now.getUTCMinutes()
  const istMinutes = utcMinutes + 330 // UTC+5:30
  const dayOfWeek = new Date(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate() + Math.floor(istMinutes / 1440),
  ).getDay()

  // Market is closed on weekends
  if (dayOfWeek === 0 || dayOfWeek === 6) return false

  // 09:15 IST = 555 min, 15:35 IST = 935 min (from midnight IST)
  const istDayMinutes = istMinutes % 1440
  return istDayMinutes >= 555 && istDayMinutes <= 935
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function formatClose(value: number): string {
  return '₹' + Number(value).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function formatRsVsNifty(value: number | null): { text: string; cls: string } {
  if (value === null) return { text: '—', cls: 'text-ink-tertiary' }
  // rs_vs_nifty = stock_return_since_open / nifty_return_since_open (a ratio, not a fraction)
  const ratio = Number(value)
  const sign = ratio >= 0 ? '+' : ''
  const text = `${sign}${ratio.toFixed(2)}x`
  const cls = ratio >= 1 ? 'text-signal-pos' : 'text-signal-neg'
  return { text, cls }
}

function formatEma(value: number | null): string {
  if (value === null) return '—'
  return '₹' + Number(value).toFixed(2)
}

function formatBarTime(isoString: string): string {
  // Convert UTC datetime to IST (UTC+5:30) and return "HH:MM IST"
  const d = new Date(isoString)
  const totalUtcMinutes = d.getUTCHours() * 60 + d.getUTCMinutes()
  const istTotalMinutes = totalUtcMinutes + 330 // UTC+5:30
  const istH = Math.floor(istTotalMinutes / 60) % 24
  const istM = istTotalMinutes % 60
  const hh = String(istH).padStart(2, '0')
  const mm = String(istM).padStart(2, '0')
  return `${hh}:${mm} IST`
}

// ---------------------------------------------------------------------------
// Skeleton loader
// ---------------------------------------------------------------------------

function SkeletonRows() {
  return (
    <>
      {[1, 2, 3].map((i) => (
        <tr key={i} className="border-b border-paper-rule last:border-0">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((j) => (
            <td key={j} className="py-2 pr-3">
              <div className="h-3 bg-paper-rule rounded animate-pulse" />
            </td>
          ))}
        </tr>
      ))}
    </>
  )
}

// ---------------------------------------------------------------------------
// Live indicator dot
// ---------------------------------------------------------------------------

type LiveStatus = 'live' | 'waiting' | 'closed'

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

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function IntradayRSLeaders() {
  const [result, setResult] = useState<IntradayLeadersData | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<boolean>(false)
  const [marketOpen] = useState<boolean>(() => isMarketOpen())
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  async function fetchLeaders(): Promise<void> {
    try {
      const res = await fetch('/api/intraday?endpoint=rs-leaders&n=20')
      if (!res.ok) {
        setError(true)
        return
      }
      const json = (await res.json()) as IntradayLeadersData
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

    void fetchLeaders()

    intervalRef.current = setInterval(() => {
      void fetchLeaders()
    }, 30_000)

    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [marketOpen])

  // Determine live status for dot
  let liveStatus: LiveStatus = 'closed'
  if (marketOpen) {
    liveStatus = result && result.data.length > 0 ? 'live' : 'waiting'
  }

  return (
    <div className="border border-paper-rule rounded-sm">
      {/* Header */}
      <div className="px-4 py-3 border-b border-paper-rule flex items-center gap-2">
        <Activity className="w-3.5 h-3.5 text-teal" />
        <span className="font-sans text-xs font-semibold text-ink-primary uppercase tracking-wide">
          Live RS Leaders (Intraday)
        </span>
        <span className="font-sans text-[11px] text-ink-tertiary">
          ranked by intraday RS percentile
        </span>
        <span className="ml-auto">
          <LiveDot status={liveStatus} />
        </span>
      </div>

      {/* Body */}
      <div className="px-4 py-3">
        {error ? (
          <p className="font-sans text-xs text-signal-neg py-2">
            Unable to load intraday data
          </p>
        ) : !marketOpen ? (
          <p className="font-sans text-xs text-ink-tertiary py-2">
            Intraday data is only available during market hours (09:15–15:35 IST).
          </p>
        ) : loading ? (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <tbody>
                <SkeletonRows />
              </tbody>
            </table>
          </div>
        ) : result && result.data.length === 0 ? (
          <p className="font-sans text-xs text-ink-tertiary py-2">
            {result.meta.note ?? 'No intraday data yet'}
          </p>
        ) : result ? (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-paper-rule">
                  <th className="pb-1.5 w-6 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
                    #
                  </th>
                  <th className="pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
                    Symbol
                  </th>
                  <th className="pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary hidden sm:table-cell">
                    Sector
                  </th>
                  <th className="pb-1.5 text-right font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
                    Close
                  </th>
                  <th className="pb-1.5 text-right font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
                    RS vs Nifty
                  </th>
                  <th className="pb-1.5 text-right font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
                    RS Pctile
                  </th>
                  <th className="pb-1.5 text-right font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary hidden lg:table-cell">
                    EMA-20
                  </th>
                  <th className="pb-1.5 text-right font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary hidden md:table-cell">
                    Bar Time
                  </th>
                </tr>
              </thead>
              <tbody>
                {result.data.map((row, i) => {
                  const rsNifty = formatRsVsNifty(row.rs_vs_nifty)
                  // rs_pctile_intraday is a 0-1 fraction — RSPctileBar expects a
                  // 0-1 string (same shape as daily rs_pctile_3m)
                  const pctileStr =
                    row.rs_pctile_intraday !== null
                      ? String(row.rs_pctile_intraday)
                      : null
                  return (
                    <tr
                      key={row.instrument_id}
                      className="border-b border-paper-rule last:border-0 hover:bg-paper-rule/10"
                    >
                      <td className="py-1.5 font-mono text-xs text-ink-tertiary tabular-nums">
                        {i + 1}
                      </td>
                      <td className="py-1.5 pr-3">
                        <div className="font-sans text-xs font-semibold text-ink-primary">
                          {row.symbol}
                        </div>
                        <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wide">
                          {row.tier}
                        </div>
                      </td>
                      <td className="py-1.5 pr-3 font-sans text-xs text-ink-secondary hidden sm:table-cell">
                        {row.sector}
                      </td>
                      <td className="py-1.5 pr-3 text-right font-mono text-xs tabular-nums text-ink-primary">
                        {formatClose(row.close)}
                      </td>
                      <td className={`py-1.5 pr-3 text-right font-mono text-xs tabular-nums ${rsNifty.cls}`}>
                        {rsNifty.text}
                      </td>
                      <td className="py-1.5 pr-3 text-right">
                        <RSPctileBar value={pctileStr} />
                      </td>
                      <td className="py-1.5 pr-3 text-right font-mono text-xs tabular-nums text-ink-secondary hidden lg:table-cell">
                        {formatEma(row.ema_20)}
                      </td>
                      <td className="py-1.5 text-right font-mono text-xs tabular-nums text-ink-tertiary hidden md:table-cell">
                        {formatBarTime(row.bar_time)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </div>
  )
}
