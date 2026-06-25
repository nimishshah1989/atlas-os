'use client'
// frontend/src/components/v6/sectors/TopPicksPanel.tsx
// Top-10 picks panel for Page 04a sector deep-dive.
// Source: mv_sector_deepdive.top_picks_top10 JSONB array.
// Only includes stocks with positive composite_score. Each row → /stocks/<symbol>.

import Link from 'next/link'
import type { TopPickRow } from '@/lib/queries/v6/sectors'

// ── Action chip ───────────────────────────────────────────────────────────────

function ActionChip({ action }: { action: string | null }) {
  if (!action) return null
  const cls =
    action === 'POSITIVE' ? 'bg-sig-pos text-surface-base'
    : action === 'NEGATIVE' ? 'bg-sig-neg text-surface-base'
    : 'bg-sig-warn/15 text-sig-warn border border-sig-warn/30'
  const label = action === 'POSITIVE' ? 'BUY' : action === 'NEGATIVE' ? 'AVOID' : 'WATCH'
  return (
    <span className={`font-num text-[9px] font-bold uppercase tracking-[0.12em] px-[6px] py-[2px] rounded-tile ${cls}`}>
      {label}
    </span>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function TopPicksPanel({ picks }: { picks: TopPickRow[] }) {
  if (picks.length === 0) {
    return (
      <div
        className="flex items-center justify-center h-20 bg-surface-panel border border-edge-hair rounded-panel shadow-panel text-txt-3 font-sans text-sm"
        role="status"
      >
        No top picks — no stocks with positive composite score.
      </div>
    )
  }

  return (
    <div
      className="bg-surface-panel border border-edge-hair rounded-panel shadow-panel overflow-hidden"
      data-testid="top-picks-panel"
      aria-label="Top picks by composite score"
    >
      <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-edge-hair">
        {picks.map((pick, idx) => {
          const score = pick.composite_score != null
            ? `${pick.composite_score >= 0 ? '+' : ''}${pick.composite_score.toFixed(1)}`
            : '—'
          const scoreColor = (pick.composite_score ?? 0) >= 0 ? 'text-sig-pos' : 'text-sig-neg'

          return (
            <Link
              key={pick.symbol}
              href={`/stocks/${encodeURIComponent(pick.symbol)}`}
              className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-surface-raised transition-colors no-underline"
              data-testid={`top-pick-${pick.symbol}`}
            >
              {/* Rank */}
              <span className="font-num text-[11px] tabular-nums text-txt-3 w-4 shrink-0 text-right">
                {idx + 1}
              </span>

              {/* Symbol + name */}
              <div className="flex-1 min-w-0">
                <span className="font-num text-[13px] font-semibold text-brand">
                  {pick.symbol}
                </span>
                {pick.company_name && (
                  <div className="text-[10px] text-txt-3 truncate">{pick.company_name}</div>
                )}
              </div>

              {/* Score */}
              <div className="text-right shrink-0">
                <div className={`font-num text-[15px] font-semibold tabular-nums ${scoreColor}`}>{score}</div>
                <div className="text-[9px] text-txt-3 uppercase tracking-wider mt-0.5">score</div>
              </div>

              {/* Band + action */}
              <div className="flex flex-col items-center gap-1 shrink-0">
                {pick.confidence_band && (
                  <span className="font-num text-[10px] text-txt-3">{pick.confidence_band}</span>
                )}
                <ActionChip action={pick.action} />
              </div>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
