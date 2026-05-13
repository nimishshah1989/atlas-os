'use client'
import type { StockRowWithSector } from '@/lib/queries/stocks'
import { optBool, optNum } from './screener-utils'

export function CTSTimingCell({ row }: { row: StockRowWithSector }) {
  const score = optNum(row, 'cts_conviction_score')
  const actionReady = optBool(row, 'cts_action_confidence')
  const isPpc = optBool(row, 'is_ppc')
  const isNpc = optBool(row, 'is_npc')
  const stg = optNum(row, 'stage')
  const scoreInt = score != null ? Math.round(score) : null

  // Derive bi-directional timing grade
  type CTSGrade = '+A' | '+B' | '—' | '−B' | '−A'
  let grade: CTSGrade = '—'
  if (stg != null) {
    if (stg === 4) grade = '−A'
    else if (stg === 3 && isNpc) grade = '−A'
    else if (stg === 3) grade = '−B'
    else if (stg === 2 && actionReady) grade = '+A'
    else if (stg === 2 && scoreInt != null && scoreInt >= 40) grade = '+B'
    else if (stg === 2) grade = '+B' // Stage 2 always at minimum a watch
    // Stage 1 stays '—'
  }

  const GRADE_STYLES: Record<CTSGrade, { badge: string; label: string; sub: string }> = {
    '+A': { badge: 'bg-teal text-white',                           label: '+A', sub: 'Buy · Act now' },
    '+B': { badge: 'bg-teal/10 text-teal border border-teal/40',  label: '+B', sub: 'Buy · Watch' },
    '—':  { badge: 'bg-paper-rule/30 text-ink-tertiary',           label: '—',  sub: 'Neutral' },
    '−B': { badge: 'bg-amber-500/10 text-amber-500 border border-amber-500/40', label: '−B', sub: 'Sell · Watch' },
    '−A': { badge: 'bg-signal-neg text-white',                    label: '−A', sub: 'Sell · Act now' },
  }
  const gs = GRADE_STYLES[grade]

  if (stg == null) {
    return <span className="font-mono text-xs text-ink-tertiary">—</span>
  }

  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-1.5">
        <span className={`inline-flex items-center justify-center w-8 h-6 rounded font-mono text-xs font-bold ${gs.badge}`}>
          {gs.label}
        </span>
        <span className="font-sans text-[10px] text-ink-tertiary whitespace-nowrap">{gs.sub}</span>
      </div>
      {scoreInt != null && (
        <div className="flex items-center gap-1.5 pl-0.5">
          <div className="relative w-14 h-1 bg-paper-rule rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${grade === '+A' || grade === '+B' ? 'bg-teal/50' : grade === '−A' || grade === '−B' ? 'bg-signal-neg/50' : 'bg-paper-rule'}`}
              style={{ width: `${Math.max(scoreInt, 4)}%` }}
            />
          </div>
          <span className="font-mono text-[10px] text-ink-tertiary tabular-nums">{scoreInt}</span>
          {(isPpc || isNpc) && (
            <span className={`font-mono text-[10px] font-semibold ${isPpc ? 'text-signal-pos' : 'text-signal-neg'}`}>
              {isPpc ? 'PPC' : 'NPC'}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
