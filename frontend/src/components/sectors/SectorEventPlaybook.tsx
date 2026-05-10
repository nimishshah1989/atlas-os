'use client'
import { AlertTriangle } from 'lucide-react'
import type { PlaybookEntry } from '@/lib/queries/sectors'

type Props = {
  entries: PlaybookEntry[]
  currentOverweightSectors: string[]
}

function formatDateRange(start: string, end: string): string {
  const fmt = (s: string) =>
    new Date(s).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
  if (start === end) return fmt(start)
  return `${fmt(start)} – ${fmt(end)}`
}

export function SectorEventPlaybook({ entries, currentOverweightSectors }: Props) {
  if (entries.length === 0) {
    return (
      <div className="px-6 py-5 border-b border-paper-rule">
        <h2 className="font-sans text-xs font-semibold text-ink-tertiary uppercase tracking-wider mb-2">
          Historical Event Playbook
        </h2>
        <p className="font-sans text-[11px] text-ink-tertiary">
          No historical events matched the current regime. Data will appear once regime state is classified.
        </p>
      </div>
    )
  }

  return (
    <div className="px-6 py-5 border-b border-paper-rule">
      <h2 className="font-sans text-xs font-semibold text-ink-tertiary uppercase tracking-wider mb-1">
        Historical Event Playbook
      </h2>
      <p className="font-sans text-[11px] text-ink-tertiary mb-4 max-w-2xl leading-relaxed">
        Sector leadership during the closest analogues to the current regime. Leaders outperformed Nifty 500 by the widest margin; Laggards underperformed the most. Current Overweight sectors in the Laggards column are flagged.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {entries.map(entry => {
          const atRisk = currentOverweightSectors.filter(s =>
            entry.laggards.some(l => l.sector_name === s),
          )
          return (
            <div key={entry.event_id} className="border border-paper-rule rounded-sm p-3 bg-paper">
              {atRisk.length > 0 && (
                <div className="flex items-start gap-1.5 mb-2 px-2 py-1.5 bg-signal-warn/10 border border-signal-warn/30 rounded-sm">
                  <AlertTriangle className="w-3 h-3 text-signal-warn flex-shrink-0 mt-0.5" />
                  <span className="font-sans text-[11px] text-signal-warn leading-snug">
                    {atRisk.join(', ')} {atRisk.length === 1 ? 'was' : 'were'} a laggard in this event — review sizing.
                  </span>
                </div>
              )}

              <div className="mb-2">
                <div className="font-sans text-[11px] font-semibold text-ink-primary">{entry.event_label}</div>
                <div className="font-sans text-[10px] text-ink-tertiary">{formatDateRange(entry.start_date, entry.end_date)}</div>
                <p className="font-sans text-[10px] text-ink-tertiary mt-0.5 leading-relaxed">{entry.event_description}</p>
              </div>

              <div className="grid grid-cols-2 gap-2 mt-2 border-t border-paper-rule pt-2">
                <div>
                  <div className="font-sans text-[9px] font-semibold uppercase tracking-wider text-signal-pos mb-1">
                    Leaders
                  </div>
                  {entry.leaders.length === 0 ? (
                    <p className="font-sans text-[10px] text-ink-tertiary">No data</p>
                  ) : (
                    entry.leaders.map((l, i) => (
                      <div key={l.sector_name} className="flex items-center justify-between gap-2 mb-0.5">
                        <span className="font-sans text-[11px] text-ink-secondary truncate">
                          {i + 1}. {l.sector_name}
                        </span>
                        <span className="font-mono text-[10px] text-signal-pos tabular-nums flex-shrink-0">
                          {l.avg_rs >= 0 ? '+' : ''}{(l.avg_rs * 100).toFixed(1)}%
                        </span>
                      </div>
                    ))
                  )}
                </div>
                <div>
                  <div className="font-sans text-[9px] font-semibold uppercase tracking-wider text-signal-neg mb-1">
                    Laggards
                  </div>
                  {entry.laggards.length === 0 ? (
                    <p className="font-sans text-[10px] text-ink-tertiary">No data</p>
                  ) : (
                    entry.laggards.map((l, i) => {
                      const isAtRisk = currentOverweightSectors.includes(l.sector_name)
                      return (
                        <div key={l.sector_name} className="flex items-center justify-between gap-2 mb-0.5">
                          <span
                            className="font-sans text-[11px] truncate"
                            style={{
                              color:      isAtRisk ? '#f59e0b' : undefined,
                              fontWeight: isAtRisk ? 600     : undefined,
                            }}
                          >
                            {i + 1}. {l.sector_name}
                          </span>
                          <span className="font-mono text-[10px] text-signal-neg tabular-nums flex-shrink-0">
                            {l.avg_rs >= 0 ? '+' : ''}{(l.avg_rs * 100).toFixed(1)}%
                          </span>
                        </div>
                      )
                    })
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
