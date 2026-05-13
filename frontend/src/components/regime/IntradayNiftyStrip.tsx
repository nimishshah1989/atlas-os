'use client'

import { useEffect, useRef, useState } from 'react'
import { Activity } from 'lucide-react'

// Market hours gate (IST = UTC+5:30) — copied from IntradayRSLeaders.tsx
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

function formatBarTime(isoString: string): string {
  const d = new Date(isoString)
  const ist = d.getUTCHours() * 60 + d.getUTCMinutes() + 330
  return `${String(Math.floor(ist / 60) % 24).padStart(2, '0')}:${String(ist % 60).padStart(2, '0')} IST`
}

function formatPrice(v: string | number): string {
  return '₹' + Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatReturn(pctStr: string | null): { text: string; cls: string } {
  if (pctStr == null) return { text: '—', cls: 'text-ink-tertiary' }
  const n = Number(pctStr)
  return { text: `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`, cls: n >= 0 ? 'text-signal-pos' : 'text-signal-neg' }
}

interface NiftyBar {
  bar_time: string
  open: string
  high: string
  low: string
  close: string
  return_since_open: string | null
  pct_change_since_open: string | null
}

interface NiftyData {
  data: NiftyBar | null
  meta: { data_as_of?: string; note?: string; fetched_at?: string; source?: string }
}

type LiveStatus = 'live' | 'waiting' | 'closed'

function LiveDot({ status }: { status: LiveStatus }) {
  const configs: Record<LiveStatus, { dot: string; label: string; labelCls: string }> = {
    live:    { dot: 'bg-signal-pos', label: 'LIVE',    labelCls: 'text-signal-pos' },
    waiting: { dot: 'bg-signal-warn', label: 'Waiting', labelCls: 'text-signal-warn' },
    closed:  { dot: 'bg-ink-tertiary', label: 'Closed',  labelCls: 'text-ink-tertiary' },
  }
  const { dot, label, labelCls } = configs[status]
  return (
    <span className="flex items-center gap-1">
      {status === 'live' ? (
        <span className="relative flex h-2 w-2">
          <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${dot} opacity-75`} />
          <span className={`relative inline-flex rounded-full h-2 w-2 ${dot}`} />
        </span>
      ) : (
        <span className={`h-2 w-2 rounded-full ${dot} inline-block`} />
      )}
      <span className={`font-sans text-[10px] font-semibold uppercase tracking-wider ${labelCls}`}>{label}</span>
    </span>
  )
}

export function IntradayNiftyStrip() {
  const [result, setResult] = useState<NiftyData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [marketOpen] = useState(() => isMarketOpen())
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  async function fetchNifty(): Promise<void> {
    try {
      const res = await fetch('/api/intraday?endpoint=nifty')
      if (!res.ok) { setError(true); return }
      const json = await res.json() as NiftyData
      setResult(json)
      setError(false)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!marketOpen) { setLoading(false); return }
    void fetchNifty()
    intervalRef.current = setInterval(() => void fetchNifty(), 30_000)
    return () => { if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null } }
  }, [marketOpen])

  const liveStatus: LiveStatus = !marketOpen ? 'closed' : (result?.data ? 'live' : 'waiting')
  const ret = formatReturn(result?.data?.pct_change_since_open ?? null)

  return (
    <div className="border border-paper-rule rounded-sm px-4 py-2.5 flex items-center gap-4 flex-wrap">
      <div className="flex items-center gap-2 shrink-0">
        <Activity className="w-3.5 h-3.5 text-teal" />
        <span className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-primary">Nifty 50</span>
        <LiveDot status={liveStatus} />
      </div>

      <span className="hidden sm:block text-paper-rule select-none">|</span>

      {error ? (
        <span className="font-sans text-xs text-signal-neg">Unable to load Nifty intraday data</span>
      ) : !marketOpen ? (
        <span className="font-sans text-xs text-ink-tertiary">Market closed · Intraday data 09:15–15:35 IST</span>
      ) : loading ? (
        <div className="flex items-center gap-3">
          {[1, 2, 3].map((i) => <div key={i} className="h-3 w-20 bg-paper-rule rounded animate-pulse" />)}
        </div>
      ) : result?.data == null ? (
        <span className="font-sans text-xs text-ink-tertiary">{result?.meta.note ?? 'Waiting for first bar...'}</span>
      ) : (
        <>
          <span className="font-mono text-sm font-semibold tabular-nums text-ink-primary">
            {formatPrice(result.data.close)}
          </span>
          <span className={`font-mono text-xs font-semibold tabular-nums ${ret.cls}`}>
            {ret.text} from open
          </span>
          <span className="hidden md:inline font-sans text-xs text-ink-secondary">
            H: {formatPrice(result.data.high)}&nbsp;&nbsp;L: {formatPrice(result.data.low)}
          </span>
          <span className="ml-auto font-sans text-[11px] text-ink-tertiary whitespace-nowrap">
            as of {formatBarTime(result.data.bar_time)}
          </span>
        </>
      )}
    </div>
  )
}
