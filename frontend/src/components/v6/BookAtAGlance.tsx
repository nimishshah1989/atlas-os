'use client'

// frontend/src/components/v6/BookAtAGlance.tsx
//
// D.2 — "Your book at a glance" holdings stats card for /v6/today.
//
// Displays:
//   - Count by conviction state (POSITIVE / NEUTRAL / NEGATIVE)
//   - Count of held iids that flipped overnight
//   - Top 5 biggest movers in the book (from book_diff held_iids_flipped + drift)
//   - CTA: "View calls you haven't acted on" → /v6/screening?filter=unacted
//
// Silent absence: if no held iids (empty book), renders null.
// Empty-state for held book but no flips: shows counts + "nothing to action" copy.

import Link from 'next/link'
import type { BookDiff, StockFlip } from '@/lib/queries/v6/book_diff'

// ---------------------------------------------------------------------------
// Prop types
// ---------------------------------------------------------------------------

export interface BookAtAGlanceProps {
  bookDiff: BookDiff
  /** Held iids grouped by today's conviction verdict. */
  heldByVerdict: {
    positive: number
    neutral: number
    negative: number
  }
}

// ---------------------------------------------------------------------------
// Stat pill
// ---------------------------------------------------------------------------

function StatPill({
  count,
  label,
  colorClass,
}: {
  count: number
  label: string
  colorClass: string
}) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={`font-mono text-sm font-semibold tabular-nums ${colorClass}`}>
        {count}
      </span>
      <span className="font-sans text-xs text-ink-secondary">{label}</span>
    </span>
  )
}

// ---------------------------------------------------------------------------
// Flip mini-row
// ---------------------------------------------------------------------------

function FlipMiniRow({ flip }: { flip: StockFlip }) {
  const fromCls =
    flip.yesterday_action === 'POSITIVE'
      ? 'text-signal-pos'
      : flip.yesterday_action === 'NEGATIVE'
        ? 'text-signal-neg'
        : 'text-ink-tertiary'
  const toCls =
    flip.today_action === 'POSITIVE'
      ? 'text-signal-pos'
      : flip.today_action === 'NEGATIVE'
        ? 'text-signal-neg'
        : 'text-ink-tertiary'

  return (
    <li className="flex items-center gap-2 py-0.5">
      <Link
        href={`/v6/stocks/${flip.instrument_id}`}
        className="font-mono text-xs font-semibold text-ink-primary hover:text-teal hover:underline w-24 shrink-0 truncate"
      >
        {flip.ticker}
      </Link>
      <span className={`font-sans text-[11px] ${fromCls}`}>
        {flip.yesterday_action ?? '—'}
      </span>
      <span className="font-sans text-[10px] text-ink-tertiary">→</span>
      <span className={`font-sans text-[11px] font-medium ${toCls}`}>
        {flip.today_action ?? '—'}
      </span>
    </li>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function BookAtAGlance({ bookDiff, heldByVerdict }: BookAtAGlanceProps) {
  const totalHeld = heldByVerdict.positive + heldByVerdict.neutral + heldByVerdict.negative

  // Silent absence — no book, no widget
  if (totalHeld === 0) return null

  const flipped = bookDiff.held_iids_flipped
  // Take top 5 flips (already ordered by DB query; all are "movers" by definition)
  const top5 = flipped.slice(0, 5)

  return (
    <div className="border border-paper-rule rounded-[2px] bg-paper p-4">
      {/* Card header */}
      <div className="font-sans text-[10px] font-medium uppercase tracking-wider text-ink-tertiary mb-2">
        Your book
      </div>

      {/* Verdict counts */}
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <StatPill count={heldByVerdict.positive} label="POSITIVE" colorClass="text-signal-pos" />
        <span className="text-ink-tertiary text-xs">·</span>
        <StatPill count={heldByVerdict.neutral} label="NEUTRAL" colorClass="text-ink-secondary" />
        <span className="text-ink-tertiary text-xs">·</span>
        <StatPill count={heldByVerdict.negative} label="NEGATIVE" colorClass="text-signal-neg" />
        {flipped.length > 0 && (
          <>
            <span className="text-ink-tertiary text-xs">·</span>
            <span className="font-sans text-xs text-signal-warn">
              {flipped.length} flipped overnight
            </span>
          </>
        )}
      </div>

      {/* Top 5 biggest moves */}
      {top5.length > 0 ? (
        <div className="mb-3">
          <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1">
            Flipped overnight
          </div>
          <ul className="divide-y divide-paper-rule">
            {top5.map(f => (
              <FlipMiniRow key={f.instrument_id} flip={f} />
            ))}
          </ul>
        </div>
      ) : (
        <p className="font-sans text-xs text-ink-tertiary mb-3">
          No positions flipped overnight.
        </p>
      )}

      {/* CTA */}
      <Link
        href="/v6/screening?filter=unacted"
        className="inline-flex items-center gap-1 font-sans text-xs text-teal hover:underline"
      >
        View calls you haven&rsquo;t acted on
        <span className="text-ink-tertiary">→</span>
      </Link>
    </div>
  )
}

export default BookAtAGlance
