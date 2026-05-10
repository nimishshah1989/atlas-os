'use client'
import type { SectorSnapshot, DaysInStateRow } from '@/lib/queries/sectors'

type TransitionEvent = {
  sector_name: string
  from_state: string
  to_state: string
  days_in_current: number
}

type Props = {
  sectors: SectorSnapshot[]
  daysInState: DaysInStateRow[]
  previousSectors?: SectorSnapshot[]
}

const STATE_COLOR: Record<string, string> = {
  Overweight:  'text-signal-pos',
  Neutral:     'text-signal-warn',
  Underweight: 'text-signal-neg',
  Avoid:       'text-signal-neg',
}

export function StateTransitionCard({ sectors, daysInState, previousSectors }: Props) {
  const daysMap = new Map(daysInState.map(d => [d.sector_name, d.days_in_state]))

  const transitions: TransitionEvent[] = []
  if (previousSectors) {
    const prevMap = new Map(previousSectors.map(s => [s.sector_name, s.sector_state]))
    for (const s of sectors) {
      const prev = prevMap.get(s.sector_name)
      if (prev && prev !== s.sector_state) {
        transitions.push({
          sector_name: s.sector_name,
          from_state: prev,
          to_state: s.sector_state,
          days_in_current: daysMap.get(s.sector_name) ?? 0,
        })
      }
    }
  }

  return (
    <div className="bg-paper border-b border-paper-rule px-6 py-3">
      {transitions.length === 0 ? (
        <p className="font-sans text-xs text-ink-tertiary">
          No sector transitions in the past 30 days.
        </p>
      ) : (
        <div className="flex flex-wrap gap-x-6 gap-y-1.5">
          {transitions.map(t => (
            <span key={t.sector_name} className="inline-flex items-center gap-1.5">
              <span className="font-sans text-xs font-medium text-teal">
                {t.sector_name}
              </span>
              <span className="font-sans text-xs text-ink-secondary">
                <span className={STATE_COLOR[t.from_state] ?? 'text-ink-secondary'}>
                  {t.from_state}
                </span>
                {' → '}
                <span className={STATE_COLOR[t.to_state] ?? 'text-ink-secondary'}>
                  {t.to_state}
                </span>
              </span>
              <span className="font-mono text-[10px] text-ink-tertiary">
                ({t.days_in_current}d)
              </span>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
