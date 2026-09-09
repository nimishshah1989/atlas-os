'use client'
// src/components/explorer/PeerStrip.tsx — the answer to "there are thousands of them".
//
// Five thousand funds is not a list a person reads; two dozen groups is. The strip puts every peer
// group above the table with its count, biggest first, so the first thing the eye does is choose a
// job — sector funds, country funds, Treasuries — and only then read the ranking inside it.
// Clicking a chip sets the peer-group facet; clicking it again clears it. It is the same URL state
// the rail writes, so the two controls can never disagree.
//
// The Unclassified group is a chip like any other. About a fifth of fund names match no strategy
// rule, and a work queue that is visible gets worked; one that is hidden becomes a silent default
// bucket, which is how a taxonomy stops meaning anything.
import { ChipButton } from '@/components/ui/Chip'
import { formatNum } from '@/lib/format'

export function PeerStrip({
  values,
  counts,
  selected,
  onToggle,
  label,
}: {
  /** Every group the list takes, in the order the explorer computed (most frequent first). */
  values: string[]
  counts: Record<string, number>
  selected: string[]
  onToggle: (value: string) => void
  label: (value: string) => string
}) {
  if (values.length === 0) return null
  return (
    <div className="mb-3 flex flex-wrap items-center gap-1.5" role="group" aria-label="Peer groups">
      {values.map((v) => {
        const n = counts[v] ?? 0
        const on = selected.includes(v)
        return (
          <ChipButton
            key={v}
            pressed={on}
            onClick={() => onToggle(v)}
            title={`${label(v)} — ${formatNum(n)} in view${on ? '. Click to clear.' : '. Click to show only these.'}`}
          >
            <span>{label(v)}</span>
            <span className="num text-ink-3">{formatNum(n)}</span>
          </ChipButton>
        )
      })}
    </div>
  )
}
