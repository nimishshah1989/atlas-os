'use client'

import { useEffect, useRef, useState } from 'react'

interface IntradayStockBadgeProps {
  instrumentId: string
}

function isMarketOpen(): boolean {
  const now = new Date()
  const utcMinutes = now.getUTCHours() * 60 + now.getUTCMinutes()
  const istMinutes = utcMinutes + 330
  const dayOfWeek = new Date(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate() + Math.floor(istMinutes / 1440),
  ).getDay()
  if (dayOfWeek === 0 || dayOfWeek === 6) return false
  const istDayMinutes = istMinutes % 1440
  return istDayMinutes >= 555 && istDayMinutes <= 935
}

export function IntradayStockBadge({ instrumentId }: IntradayStockBadgeProps) {
  const [price, setPrice] = useState<string | null>(null)
  const [marketOpen] = useState(() => isMarketOpen())
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!marketOpen) return
    const fetch_ = async () => {
      try {
        const res = await fetch('/api/intraday?endpoint=prices')
        if (!res.ok) return
        const json = await res.json() as { data: Record<string, string> | null }
        const p = json.data?.[instrumentId] ?? null
        setPrice(p)
      } catch { /* silent — badge disappears if unavailable */ }
    }
    void fetch_()
    intervalRef.current = setInterval(() => void fetch_(), 30_000)
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [marketOpen, instrumentId])

  if (!marketOpen && price == null) return null
  if (marketOpen && price == null) return null

  const formatted = price
    ? '₹' + Number(price).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : null

  if (!formatted) return null

  return (
    <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm border border-teal/30 bg-teal/5">
      <span className="relative flex h-1.5 w-1.5">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-teal opacity-75" />
        <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-teal" />
      </span>
      <span className="font-sans text-[10px] font-semibold text-teal uppercase tracking-wider">LIVE</span>
      <span className="font-mono text-xs font-semibold text-ink-primary tabular-nums">{formatted}</span>
    </div>
  )
}
