// src/components/ui/DecileChip.tsx — a peer decile, 1 (weakest) to 10 (strongest), on the muted
// ramp shared with India (`--decile-N` in globals.css, theme-scoped). Deciles only.
//
// The decile is CUT ON READ within the peer group (src/lib/queries/scores.ts) — never stored — so
// this chip is always a statement about a population on a date, and the tooltip says which.
// The number is printed inside the chip: the colour is the second channel, never the only one.
import { decileColour, isLeader, LEADER_DECILE } from '@/lib/scores'

export function DecileChip({
  decile,
  title,
  className = '',
}: {
  decile: number | string | null | undefined
  /** What population this decile was cut in — "ranked 4 of 34 in Equity · Sector". */
  title?: string
  className?: string
}) {
  const colour = decileColour(decile)
  if (colour === null) {
    return (
      <span className={`num text-meta text-ink-3 ${className}`} title={title}>
        —
      </span>
    )
  }
  const n = Math.round(Number(decile))
  const leader = isLeader(n)
  return (
    <span
      className={`decile-chip num ${className}`}
      style={{ backgroundColor: colour }}
      aria-label={`Decile ${n} of 10${leader ? `, Leader (top decile)` : ''}${title ? `, ${title}` : ''}`}
      title={title ?? `Decile ${n} of 10`}
      data-decile={n}
      data-leader={leader ? '' : undefined}
    >
      {n}
    </span>
  )
}

/** The word beside the chip. Leader = top decile within the peer group, the same cut India's
 *  v_stock_leader makes within cap cohort — so "leader" means one thing on both boards. */
export function LeaderMark({ decile }: { decile: number | null | undefined }) {
  if (!isLeader(decile)) return null
  return (
    <span className="text-meta font-medium text-ink" title={`Top decile (${LEADER_DECILE} of 10) within its peer group`}>
      Leader
    </span>
  )
}
