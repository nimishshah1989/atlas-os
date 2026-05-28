'use client'
// frontend/src/components/v6/sectors/TopPicksPanel.tsx
// Top-10 picks panel for Page 04a sector deep-dive.
// Source: mv_sector_deepdive.top_picks_top10 JSONB array.
// Only includes stocks with positive composite_score.

import Link from 'next/link'
import type { TopPickRow } from '@/lib/queries/v6/sectors'

// ── Action chip ───────────────────────────────────────────────────────────────

function ActionChip({ action }: { action: string | null }) {
  if (!action) return null
  const cls =
    action === 'POSITIVE' ? 'bg-signal-pos text-paper'
    : action === 'NEGATIVE' ? 'bg-signal-neg text-paper'
    : 'bg-signal-warn/15 text-signal-warn border border-signal-warn/30'
  const label = action === 'POSITIVE' ? 'BUY' : action === 'NEGATIVE' ? 'AVOID' : 'WATCH'
  return (
    <span className={`font-sans text-[9px] font-bold uppercase tracking-[0.12em] px-[6px] py-[2px] rounded-[2px] ${cls}`}>
      {label}
    </span>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function TopPicksPanel({ picks }: { picks: TopPickRow[] }) {
  if (picks.length === 0) {
    return (
      <div
        className="flex items-center justify-center h-20 bg-paper border border-paper-rule rounded-[2px] text-ink-tertiary font-sans text-sm"
        role="status"
      >
        No top picks — no stocks with positive composite score.
      </div>
    )
  }

  return (
    <div
      className="bg-paper border border-paper-rule rounded-[2px] overflow-hidden"
      data-testid="top-picks-panel"
      aria-label="Top picks by composite score"
    >
      <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-paper-rule">
        {picks.map((pick, idx) => {
          const score = pick.composite_score != null
            ? `${pick.composite_score >= 0 ? '+' : ''}${pick.composite_score.toFixed(1)}`
            : '—'
          const scoreColor = (pick.composite_score ?? 0) >= 0 ? 'text-signal-pos' : 'text-signal-neg'

          return (
            <div
              key={pick.symbol}
              className="flex items-center gap-3 px-4 py-3 hover:bg-paper-soft/60 transition-colors"
              data-testid={`top-pick-${pick.symbol}`}
            >
              {/* Rank */}
              <span className="font-mono text-[11px] text-ink-tertiary w-4 shrink-0 text-right">
                {idx + 1}
              </span>

              {/* Symbol + name */}
              <div className="flex-1 min-w-0">
                <Link
                  href={`/stocks/${encodeURIComponent(pick.symbol)}`}
                  className="font-mono text-[13px] font-semibold text-teal hover:underline"
                >
                  {pick.symbol}
                </Link>
                {pick.company_name && (
                  <div className="text-[10px] text-ink-tertiary truncate">{pick.company_name}</div>
                )}
              </div>

              {/* Score */}
              <div className="text-right shrink-0">
                <div className={`font-mono text-[15px] font-semibold ${scoreColor}`}>{score}</div>
                <div className="text-[9px] text-ink-tertiary uppercase tracking-wider mt-0.5">score</div>
              </div>

              {/* Band + action */}
              <div className="flex flex-col items-center gap-1 shrink-0">
                {pick.confidence_band && (
                  <span className="font-mono text-[10px] text-ink-tertiary">{pick.confidence_band}</span>
                )}
                <ActionChip action={pick.action} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
