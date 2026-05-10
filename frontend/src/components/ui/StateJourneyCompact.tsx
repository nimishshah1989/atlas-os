'use client'
import { useState, useEffect } from 'react'
import { buildSegments } from '@/lib/state-segment-utils'
import { CHART_COLORS } from '@/lib/chart-colors'

type StateRow = {
  date: string
  rs_state: string | null
  momentum_state: string | null
  risk_state: string | null
  volume_state: string | null
}

type LaneDef = {
  key: keyof Omit<StateRow, 'date'>
  label: string
  colorMap: Record<string, string>
}

const RS_COLORS: Record<string, string> = {
  Leader:        CHART_COLORS.rsLeader,
  Strong:        CHART_COLORS.rsStrong,
  Emerging:      CHART_COLORS.rsEmerging,
  Consolidating: CHART_COLORS.rsConsolidating,
  Average:       CHART_COLORS.rsAverage,
  Weak:          CHART_COLORS.rsWeak,
  Laggard:       CHART_COLORS.rsLaggard,
}

const MOM_COLORS: Record<string, string> = {
  Accelerating:  CHART_COLORS.momAccelerating,
  Improving:     CHART_COLORS.momImproving,
  Flat:          CHART_COLORS.momFlat,
  Deteriorating: CHART_COLORS.momDeteriorating,
  Collapsing:    CHART_COLORS.momCollapsing,
}

const RISK_COLORS: Record<string, string> = {
  Low:           CHART_COLORS.rsStrong,
  Normal:        CHART_COLORS.inkTertiary,
  Elevated:      CHART_COLORS.rsConsolidating,
  High:          CHART_COLORS.rsWeak,
  'Below Trend': '#7C3AED',
}

const VOL_COLORS: Record<string, string> = {
  Accumulation:        CHART_COLORS.rsLeader,
  'Steady-Buying':     CHART_COLORS.rsStrong,
  Neutral:             CHART_COLORS.inkTertiary,
  Distribution:        CHART_COLORS.rsWeak,
  'Heavy Distribution': CHART_COLORS.rsLaggard,
}

const LANES: LaneDef[] = [
  { key: 'rs_state',       label: 'RS',  colorMap: RS_COLORS },
  { key: 'momentum_state', label: 'Mom', colorMap: MOM_COLORS },
  { key: 'risk_state',     label: 'Risk', colorMap: RISK_COLORS },
  { key: 'volume_state',   label: 'Vol', colorMap: VOL_COLORS },
]

type Props = {
  symbol?: string
  ticker?: string
  days?: number
}

export function StateJourneyCompact({ symbol, ticker, days = 90 }: Props) {
  const [rows, setRows] = useState<StateRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const param = symbol ? `symbol=${encodeURIComponent(symbol)}` : `ticker=${encodeURIComponent(ticker!)}`
    const timer = setTimeout(() => {
      fetch(`/api/states-compact?${param}&days=${days}`)
        .then(r => r.ok ? r.json() : Promise.reject())
        .then((d: { rows: StateRow[] }) => { setRows(d.rows); setLoading(false) })
        .catch(() => setLoading(false))
    }, 300)
    return () => clearTimeout(timer)
  }, [symbol, ticker, days])

  if (loading) {
    return (
      <div className="space-y-1">
        {LANES.map(l => (
          <div key={l.key} className="flex items-center gap-2">
            <span className="w-7 text-[10px] text-ink-tertiary font-mono shrink-0">{l.label}</span>
            <div className="flex-1 h-2 bg-paper-rule rounded-sm animate-pulse" />
          </div>
        ))}
      </div>
    )
  }

  if (rows.length === 0) return <p className="text-xs text-ink-tertiary">No state history</p>

  return (
    <div className="space-y-1">
      {LANES.map(lane => {
        const laneRows = rows
          .filter(r => r[lane.key] != null)
          .map(r => ({ date: new Date(r.date), state: r[lane.key] as string }))
        const segments = buildSegments(laneRows)
        const total = segments.reduce((s, seg) => s + seg.days, 0)
        if (total === 0) return null
        return (
          <div key={lane.key} className="flex items-center gap-2">
            <span className="w-7 text-[10px] text-ink-tertiary font-mono shrink-0">{lane.label}</span>
            <div className="flex-1 flex h-2 rounded-sm overflow-hidden bg-paper-rule">
              {segments.map((seg, i) => (
                <div
                  key={i}
                  className="h-full"
                  style={{
                    width: `${(seg.days / total) * 100}%`,
                    background: lane.colorMap[seg.state] ?? CHART_COLORS.inkTertiary,
                  }}
                  title={`${seg.state} (${seg.days}d from ${seg.startDate.toISOString().slice(0, 10)})`}
                />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
