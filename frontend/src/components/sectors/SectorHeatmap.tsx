'use client'
import { useMemo, useState } from 'react'
import type { SectorStateRow } from '@/lib/queries/sectors'

const STATE_COLOR: Record<string, string> = {
  Overweight:  '#22c55e',
  Neutral:     '#f59e0b',
  Underweight: '#ef4444',
  Avoid:       '#7c2d12',
}

type Props = {
  history: SectorStateRow[]
  sectors: string[]
}

export function SectorHeatmap({ history, sectors }: Props) {
  const [tooltip, setTooltip] = useState<{ text: string; x: number; y: number } | null>(null)

  const { dates, cellMap } = useMemo(() => {
    const map = new Map<string, Map<string, string>>()
    const dateSet = new Set<string>()

    for (const row of history) {
      const d = row.date instanceof Date
        ? row.date.toISOString().slice(0, 10)
        : String(row.date).slice(0, 10)
      dateSet.add(d)
      if (!map.has(row.sector_name)) map.set(row.sector_name, new Map())
      map.get(row.sector_name)!.set(d, row.sector_state)
    }

    const sortedDates = [...dateSet].sort()
    return { dates: sortedDates, cellMap: map }
  }, [history])

  const monthLabels = useMemo(() => {
    const seen = new Set<string>()
    return dates.map((d) => {
      const m = d.slice(0, 7)
      if (seen.has(m)) return null
      seen.add(m)
      const dt = new Date(d)
      return dt.toLocaleDateString('en-US', { month: 'short', year: '2-digit' }).replace(' ', " '")
    })
  }, [dates])

  const cellW = Math.max(3, Math.min(14, Math.floor(900 / Math.max(dates.length, 1))))
  const cellH = 18

  return (
    <div className="relative overflow-x-auto">
      {/* Sector rows */}
      {sectors.map(sector => {
        const sectorMap = cellMap.get(sector) ?? new Map<string, string>()
        return (
          <div key={sector} className="flex items-center mb-px">
            <div
              className="font-sans text-[10px] text-ink-secondary shrink-0 pr-2 text-right"
              style={{ width: 144 }}
            >
              {sector}
            </div>
            {dates.map(d => {
              const state = sectorMap.get(d)
              const color = state ? (STATE_COLOR[state] ?? '#94a3b8') : '#e2e8f0'
              return (
                <div
                  key={d}
                  style={{
                    width: cellW,
                    height: cellH,
                    background: color,
                    opacity: state ? 0.75 : 0.3,
                    flexShrink: 0,
                    cursor: state ? 'pointer' : 'default',
                  }}
                  onMouseEnter={e => {
                    if (!state) return
                    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
                    const dt = new Date(d)
                    setTooltip({
                      text: `${sector} · ${dt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })} · ${state}`,
                      x: rect.left,
                      y: rect.top - 32,
                    })
                  }}
                  onMouseLeave={() => setTooltip(null)}
                />
              )
            })}
          </div>
        )
      })}

      {/* Month label row — below all sector rows so labels are never covered */}
      <div className="flex mt-1" style={{ paddingLeft: 144, height: 20 }}>
        {dates.map((d, i) => (
          <div key={d} style={{ width: cellW, flexShrink: 0, position: 'relative' }}>
            {monthLabels[i] && (
              <span
                style={{
                  position: 'absolute',
                  left: 0,
                  fontFamily: 'var(--font-sans)',
                  fontSize: 9,
                  color: '#94a3b8',
                  whiteSpace: 'nowrap',
                }}
              >
                {monthLabels[i]}
              </span>
            )}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-5 mt-3" style={{ paddingLeft: 144 }}>
        {(['Overweight', 'Neutral', 'Underweight', 'Avoid'] as const).map(label => (
          <span key={label} className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
            <span
              className="inline-block w-3 h-3"
              style={{ background: STATE_COLOR[label], opacity: 0.75 }}
            />
            {label}
          </span>
        ))}
      </div>

      {/* Tooltip (fixed position follows cursor) */}
      {tooltip && (
        <div
          className="fixed z-50 bg-paper border border-paper-rule rounded-[2px] px-2 py-1 font-sans text-[11px] text-ink-primary shadow-sm pointer-events-none"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          {tooltip.text}
        </div>
      )}
    </div>
  )
}
