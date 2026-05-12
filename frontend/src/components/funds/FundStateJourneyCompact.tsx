'use client'
import { useState, useEffect } from 'react'
import { buildSegments } from '@/lib/state-segment-utils'
import { CHART_COLORS } from '@/lib/chart-colors'

type FundStateRow = {
  date: string
  nav_state: string | null
  composition_state: string | null
  holdings_state: string | null
}

type LaneDef = {
  key: keyof Omit<FundStateRow, 'date'>
  label: string
  colorMap: Record<string, string>
}

// NAV state mirrors the stock RS states (strips " NAV" for matching)
const NAV_COLORS: Record<string, string> = {
  'Leader NAV':        CHART_COLORS.rsLeader,
  'Strong NAV':        CHART_COLORS.rsStrong,
  'Emerging NAV':      CHART_COLORS.rsEmerging,
  'Average NAV':       CHART_COLORS.rsAverage,
  'Consolidating NAV': CHART_COLORS.rsConsolidating,
  'Weak NAV':          CHART_COLORS.rsWeak,
  'Laggard NAV':       CHART_COLORS.rsLaggard,
  DISLOCATION_SUSPENDED: CHART_COLORS.inkTertiary,
}

const COMP_COLORS: Record<string, string> = {
  Aligned:               CHART_COLORS.rsLeader,
  Mixed:                 CHART_COLORS.rsConsolidating,
  Misaligned:            CHART_COLORS.rsWeak,
  NO_DISCLOSURE:         CHART_COLORS.inkTertiary,
  DISLOCATION_SUSPENDED: CHART_COLORS.inkTertiary,
}

const HOLD_COLORS: Record<string, string> = {
  'Strong-Holdings':     CHART_COLORS.rsLeader,
  'Mixed-Holdings':      CHART_COLORS.rsConsolidating,
  'Weak-Holdings':       CHART_COLORS.rsWeak,
  NO_DISCLOSURE:         CHART_COLORS.inkTertiary,
  DISLOCATION_SUSPENDED: CHART_COLORS.inkTertiary,
}

const LANES: LaneDef[] = [
  { key: 'nav_state',         label: 'NAV',  colorMap: NAV_COLORS },
  { key: 'composition_state', label: 'Comp', colorMap: COMP_COLORS },
  { key: 'holdings_state',    label: 'Hold', colorMap: HOLD_COLORS },
]

type Props = {
  mstarId: string
  days?: number
}

export function FundStateJourneyCompact({ mstarId, days = 180 }: Props) {
  const [rows, setRows] = useState<FundStateRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const timer = setTimeout(() => {
      fetch(`/api/fund-states-compact?mstar_id=${encodeURIComponent(mstarId)}&days=${days}`)
        .then(r => r.ok ? r.json() : Promise.reject())
        .then((d: { rows: FundStateRow[] }) => { setRows(d.rows); setLoading(false) })
        .catch(() => setLoading(false))
    }, 300)
    return () => clearTimeout(timer)
  }, [mstarId, days])

  if (loading) {
    return (
      <div className="space-y-1">
        {LANES.map(l => (
          <div key={l.key} className="flex items-center gap-2">
            <span className="w-8 text-[10px] text-ink-tertiary font-mono shrink-0">{l.label}</span>
            <div className="flex-1 h-2 bg-paper-rule rounded-sm animate-pulse" />
          </div>
        ))}
      </div>
    )
  }

  if (rows.length === 0) {
    return <p className="text-xs text-ink-tertiary">No state history available for this fund.</p>
  }

  return (
    <div className="space-y-1.5">
      {LANES.map(lane => {
        const laneRows = rows
          .filter(r => r[lane.key] != null)
          .map(r => ({ date: new Date(r.date), state: r[lane.key] as string }))
        const segments = buildSegments(laneRows)
        const total = segments.reduce((s, seg) => s + seg.days, 0)
        if (total === 0) return null
        return (
          <div key={lane.key} className="flex items-center gap-2">
            <span className="w-8 text-[10px] text-ink-tertiary font-mono shrink-0">{lane.label}</span>
            <div className="flex-1 flex h-2.5 rounded-sm overflow-hidden bg-paper-rule">
              {segments.map((seg, i) => (
                <div
                  key={i}
                  className="h-full"
                  style={{
                    width: `${(seg.days / total) * 100}%`,
                    background: lane.colorMap[seg.state] ?? CHART_COLORS.inkTertiary,
                  }}
                  title={`${seg.state} · ${seg.days}d from ${seg.startDate.toISOString().slice(0, 10)}`}
                />
              ))}
            </div>
            {/* Current state label */}
            {segments.length > 0 && (
              <span className="text-[9px] text-ink-tertiary font-mono w-16 truncate shrink-0 text-right"
                title={segments[segments.length - 1].state}>
                {segments[segments.length - 1].state.replace(/ NAV$/, '').replace('-Holdings', '')}
                &nbsp;{segments[segments.length - 1].days}d
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}
