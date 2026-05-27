'use client'

// frontend/src/components/v6/DiffSinceYesterdayPanel.tsx
//
// D.1 + D.12 — "Diff since yesterday" header strip for /v6/today.
//
// Sections:
//   Header banner: "N cells active today (+M since yesterday) · K drift_warn · X signal_calls overnight"
//   Drift_warn count chip (D.12): clickable to /methodology#drift-warn-section
//   Section 1: New cells firing
//   Section 2: Cells gone dormant
//   Section 3: Held iids flipped overnight
//   Empty-state: "No changes since yesterday's snapshot"
//
// drift_status enum literals per migration 080: {healthy, drift_warn, deprecated}

import Link from 'next/link'
import type { MatrixDiff, CellSummary } from '@/lib/queries/v6/matrix_diff'
import type { BookDiff, StockFlip } from '@/lib/queries/v6/book_diff'

// ---------------------------------------------------------------------------
// Prop types
// ---------------------------------------------------------------------------

export interface DiffSinceYesterdayPanelProps {
  matrixDiff: MatrixDiff
  bookDiff: BookDiff
  /** Total cells active today (from signal_calls count) */
  activeCellsToday: number
  /** Total signal_calls fired overnight */
  signalCallsOvernight: number
  /** Count of cells in drift_warn (D.12) */
  driftWarnCount: number
}

// ---------------------------------------------------------------------------
// Action badge — compact state-change chip
// ---------------------------------------------------------------------------

function ActionBadge({ action }: { action: 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE' | null }) {
  if (action === null) return <span className="font-sans text-[10px] text-ink-tertiary">—</span>
  const cls =
    action === 'POSITIVE'
      ? 'bg-signal-pos/15 text-signal-pos'
      : action === 'NEGATIVE'
        ? 'bg-signal-neg/15 text-signal-neg'
        : 'bg-paper-deep text-ink-secondary'
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-medium uppercase tracking-wide ${cls}`}>
      {action}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Cell row
// ---------------------------------------------------------------------------

function CellRow({ cell }: { cell: CellSummary }) {
  // Compose human-readable name: "Large 6m POSITIVE" instead of raw UUID.
  // The /v6/cells/[cell_id] route accepts both formats.
  const composedName = `${cell.cap_tier} ${cell.tenure} ${cell.action}`
  return (
    <li className="flex items-center gap-2 py-1">
      <Link
        href={`/v6/cells/${encodeURIComponent(composedName.replace(/ /g, '-'))}`}
        className="font-sans text-xs font-medium text-ink-primary hover:text-teal hover:underline flex-1 min-w-0 truncate"
      >
        {composedName}
      </Link>
      <ActionBadge action={cell.action} />
      <span className="font-sans text-[10px] text-ink-tertiary whitespace-nowrap">
        {cell.date_changed}
      </span>
    </li>
  )
}

// ---------------------------------------------------------------------------
// Flip row
// ---------------------------------------------------------------------------

function FlipRow({ flip }: { flip: StockFlip }) {
  return (
    <li className="flex items-center gap-2 py-1">
      <Link
        href={`/v6/stocks/${flip.instrument_id}`}
        className="font-mono text-xs font-semibold text-ink-primary hover:text-teal hover:underline w-20 shrink-0"
      >
        {flip.ticker}
      </Link>
      <div className="flex items-center gap-1">
        <ActionBadge action={flip.yesterday_action} />
        <span className="font-sans text-[10px] text-ink-tertiary">→</span>
        <ActionBadge action={flip.today_action} />
      </div>
      <span className="font-sans text-[10px] text-ink-tertiary ml-auto">{flip.date_changed}</span>
    </li>
  )
}

// ---------------------------------------------------------------------------
// DriftWarnChip (D.12)
// ---------------------------------------------------------------------------

function DriftWarnChip({ count }: { count: number }) {
  if (count === 0) return null
  return (
    <Link
      href="/methodology#drift-warn-section"
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-[2px] bg-signal-warn/20 text-signal-warn text-[11px] font-sans font-medium hover:bg-signal-warn/30 transition-colors whitespace-nowrap"
      aria-label={`${count} cells in drift_warn status — click to view methodology`}
    >
      {count} {count === 1 ? 'cell' : 'cells'} in drift_warn
    </Link>
  )
}

// ---------------------------------------------------------------------------
// Section heading
// ---------------------------------------------------------------------------

function SectionHead({ children }: { children: React.ReactNode }) {
  return (
    <div className="font-sans text-[10px] font-medium uppercase tracking-wider text-ink-tertiary mb-1 mt-3">
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function DiffSinceYesterdayPanel({
  matrixDiff,
  bookDiff,
  activeCellsToday,
  signalCallsOvernight,
  driftWarnCount,
}: DiffSinceYesterdayPanelProps) {
  const newFiring = matrixDiff.new_cells_firing
  const dormant = matrixDiff.cells_dormant
  const flipped = bookDiff.held_iids_flipped

  const delta = newFiring.length - dormant.length
  const deltaStr =
    delta > 0 ? `+${delta}` : delta < 0 ? `${delta}` : '±0'

  const hasChanges = newFiring.length > 0 || dormant.length > 0 || flipped.length > 0

  return (
    <div className="border-b border-paper-rule bg-paper px-6 py-4">
      {/* Header row */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <span className="font-sans text-sm font-medium text-ink-primary">
          {activeCellsToday} cells active today
          {newFiring.length > 0 && (
            <span className="text-signal-pos"> ({deltaStr} since yesterday)</span>
          )}
        </span>
        <span className="text-ink-tertiary text-sm">·</span>
        <span className="font-sans text-sm text-ink-secondary">
          {signalCallsOvernight} signal_calls overnight
        </span>
        <span className="text-ink-tertiary text-sm">·</span>
        <DriftWarnChip count={driftWarnCount} />
      </div>

      {/* Body */}
      {!hasChanges ? (
        <p className="font-sans text-xs text-ink-tertiary mt-2">
          No changes since yesterday&rsquo;s snapshot
        </p>
      ) : (
        <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-8">
          {/* Column 1: new firing + dormant */}
          <div>
            {newFiring.length > 0 && (
              <>
                <SectionHead>New cells firing ({newFiring.length})</SectionHead>
                <ul className="divide-y divide-paper-rule">
                  {newFiring.map(c => <CellRow key={c.cell_id} cell={c} />)}
                </ul>
              </>
            )}
            {dormant.length > 0 && (
              <>
                <SectionHead>Cells gone dormant ({dormant.length})</SectionHead>
                <ul className="divide-y divide-paper-rule">
                  {dormant.map(c => <CellRow key={c.cell_id} cell={c} />)}
                </ul>
              </>
            )}
          </div>

          {/* Column 2: held iids flipped */}
          {flipped.length > 0 && (
            <div>
              <SectionHead>Held positions flipped ({flipped.length})</SectionHead>
              <ul className="divide-y divide-paper-rule">
                {flipped.map(f => <FlipRow key={f.instrument_id} flip={f} />)}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default DiffSinceYesterdayPanel
