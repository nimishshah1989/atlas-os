'use client'
import { useState } from 'react'
import type { SectorStateRow } from '@/lib/queries/sectors'

const STATES = ['Overweight', 'Neutral', 'Underweight', 'Avoid'] as const
type State = (typeof STATES)[number]

const STATE_COLOR: Record<string, string> = {
  Overweight:  '#22c55e',
  Neutral:     '#f59e0b',
  Underweight: '#ef4444',
  Avoid:       '#7c2d12',
}

function dateOf(d: Date | string): string {
  return d instanceof Date ? d.toISOString().slice(0, 10) : String(d).slice(0, 10)
}

function formatDate(d: Date | string): string {
  const dt = new Date(dateOf(d))
  return dt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function SectorDrawerStateStats({
  history,
  range,
}: {
  history: SectorStateRow[]
  range: string
}) {
  const [tip, setTip] = useState<{ text: string; x: number; y: number } | null>(null)

  if (history.length === 0) {
    return (
      <div className="font-sans text-xs text-ink-tertiary py-2">
        No state history available for this range.
      </div>
    )
  }

  const total = history.length
  const counts: Record<State, number> = { Overweight: 0, Neutral: 0, Underweight: 0, Avoid: 0 }
  for (const row of history) {
    if ((STATES as readonly string[]).includes(row.sector_state)) {
      counts[row.sector_state as State] += 1
    }
  }

  const last = history[history.length - 1]
  let streak = 0
  for (let i = history.length - 1; i >= 0; i--) {
    if (history[i].sector_state === last.sector_state) streak += 1
    else break
  }

  let transitions = 0
  for (let i = 1; i < history.length; i++) {
    if (history[i].sector_state !== history[i - 1].sector_state) transitions += 1
  }

  return (
    <div className="space-y-3 pb-4 border-b border-paper-rule">
      <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">
        State Distribution — {range}
      </div>

      {/* Stacked bar */}
      <div className="flex h-6 w-full overflow-hidden rounded-sm border border-paper-rule">
        {STATES.map(s => {
          const pct = (counts[s] / total) * 100
          if (pct === 0) return null
          return (
            <div
              key={s}
              className="flex items-center justify-center font-sans text-[10px] font-semibold text-white"
              style={{ width: `${pct}%`, background: STATE_COLOR[s] }}
              title={`${s}: ${pct.toFixed(0)}%`}
            >
              {pct >= 12 ? `${pct.toFixed(0)}%` : ''}
            </div>
          )
        })}
      </div>

      {/* Compact legend — dot · label · pct · days */}
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {STATES.map(s => {
          const c = counts[s]
          if (c === 0) return null
          const pct = (c / total) * 100
          return (
            <span key={s} className="flex items-center gap-1.5 font-sans text-[11px]">
              <span className="inline-block w-2 h-2 rounded-full flex-shrink-0" style={{ background: STATE_COLOR[s] }} />
              <span className="text-ink-secondary">{s}</span>
              <span className="font-mono text-ink-tertiary">{pct.toFixed(0)}%</span>
              <span className="text-ink-tertiary/60">({c}d)</span>
            </span>
          )
        })}
      </div>

      {/* Streak + transitions */}
      <div className="flex items-center gap-4 pt-1">
        <div className="font-sans text-[11px] text-ink-secondary">
          Current run: <span className="font-mono font-semibold text-ink-primary">{streak}d</span>{' '}
          <span className="text-ink-tertiary">in {last.sector_state}</span>
        </div>
        <div className="font-sans text-[11px] text-ink-secondary">
          Transitions: <span className="font-mono font-semibold text-ink-primary">{transitions}</span>
        </div>
      </div>

      {/* Timeline strip — hoverable */}
      <div>
        <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1.5">Timeline</div>
        <div className="flex w-full h-5 overflow-hidden rounded-sm border border-paper-rule">
          {history.map((row, i) => {
            // compute run length ending at this index
            let runLen = 1
            for (let j = i - 1; j >= 0; j--) {
              if (history[j].sector_state === row.sector_state) runLen++
              else break
            }
            return (
              <div
                key={i}
                className="flex-1 min-w-[1px] cursor-crosshair"
                style={{ background: STATE_COLOR[row.sector_state] ?? '#94a3b8' }}
                onMouseEnter={e => {
                  const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
                  setTip({
                    text: `${formatDate(row.date)} · ${row.sector_state} · ${runLen}d in state`,
                    x: r.left + r.width / 2,
                    y: r.top - 6,
                  })
                }}
                onMouseLeave={() => setTip(null)}
              />
            )
          })}
        </div>
        <div className="flex justify-between mt-1 font-sans text-[10px] text-ink-tertiary">
          <span>{dateOf(history[0].date)}</span>
          <span>{dateOf(history[history.length - 1].date)}</span>
        </div>
      </div>

      {/* Tooltip portal */}
      {tip && (
        <div
          className="fixed z-[9999] pointer-events-none -translate-x-1/2 -translate-y-full px-2 py-1 rounded-[2px] border border-paper-rule bg-paper shadow-sm font-sans text-[11px] text-ink-primary whitespace-nowrap"
          style={{ left: tip.x, top: tip.y }}
        >
          {tip.text}
        </div>
      )}
    </div>
  )
}
