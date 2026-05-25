// frontend/src/components/v6/CellHero.tsx
//
// Hero strip for /v6/cells/[cell_id].
//
// Displays: cell name · grade chip · IC · fric-adj · BH-FDR q (or "—") ·
//           predicted_excess · drift_status chip
//
// Sources: atlas_cell_definitions (via getCellById), atlas_signal_calls (predicted_excess)
// LOC budget: ≤300

'use client'

import React from 'react'
import { GradeChip } from '@/components/v6/GradeChip'
import type { Grade } from '@/components/v6/GradeChip'
import { formatPct } from '@/lib/v6/decimal'
import type { Cell, DriftStatus } from '@/lib/queries/v6/cells'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Map IC value (0..1) to a rough letter grade. */
function icToGrade(ic: string | null | undefined): Grade {
  if (ic == null) return 'failed-gate'
  const n = parseFloat(ic)
  if (!Number.isFinite(n)) return 'failed-gate'
  if (n >= 0.12) return 'AAA'
  if (n >= 0.09) return 'AA'
  if (n >= 0.06) return 'A'
  if (n >= 0.04) return 'BBB'
  if (n >= 0.02) return 'BB'
  if (n >= 0.01) return 'B'
  return 'failed-gate'
}

function DriftChip({ status }: { status: DriftStatus }): React.ReactElement | null {
  if (status === 'healthy') return null

  const config = {
    drift_warn: { label: 'Drift Warning', classes: 'bg-signal-warn/20 text-signal-warn' },
    deprecated: { label: 'Deprecated', classes: 'bg-paper-deep text-ink-tertiary' },
  } as const

  const c = config[status as 'drift_warn' | 'deprecated']
  if (!c) return null

  return (
    <span
      role="status"
      aria-label={`Cell drift status: ${c.label}`}
      className={[
        'inline-flex items-center px-2 py-0.5 rounded-[2px] text-[11px] font-sans font-semibold uppercase',
        'tracking-[0.08em]',
        c.classes,
      ].join(' ')}
    >
      {c.label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// StatPill — compact labeled number
// ---------------------------------------------------------------------------

interface StatPillProps {
  label: string
  value: string
  valueClassName?: string
}

function StatPill({ label, value, valueClassName = '' }: StatPillProps): React.ReactElement {
  return (
    <div className="flex flex-col gap-0.5 min-w-[80px]">
      <span className="text-[10px] font-sans font-medium uppercase tracking-[0.08em] text-ink-tertiary leading-none">
        {label}
      </span>
      <span
        className={['text-[15px] font-mono font-semibold tabular-nums leading-tight text-ink-primary', valueClassName].filter(Boolean).join(' ')}
      >
        {value}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// CellHero
// ---------------------------------------------------------------------------

export interface CellHeroProps {
  cell: Cell
  /** Human-readable label derived from cap_tier + tenure + action */
  cellLabel: string
}

export function CellHero({ cell, cellLabel }: CellHeroProps): React.ReactElement {
  const grade = icToGrade(cell.confidence_unconditional)

  const icDisplay = cell.confidence_unconditional
    ? (parseFloat(cell.confidence_unconditional) * 100).toFixed(2) + ' IC'
    : '—'

  const fricDisplay = cell.friction_adjusted_excess
    ? formatPct(cell.friction_adjusted_excess)
    : '—'

  const predictedDisplay = cell.predicted_excess
    ? formatPct(cell.predicted_excess)
    : '—'

  const bhFdrDisplay = cell.bh_fdr_q ?? '—'

  return (
    <header
      className="bg-paper border-b border-paper-rule px-6 py-5"
      aria-label={`Cell detail: ${cellLabel}`}
    >
      {/* Breadcrumb */}
      <nav className="text-[11px] font-sans text-ink-tertiary mb-3" aria-label="Breadcrumb">
        <a href="/matrix" className="hover:text-teal transition-colors">Matrix</a>
        <span className="mx-1.5 text-ink-tertiary/60">›</span>
        <span className="text-ink-secondary">{cellLabel}</span>
      </nav>

      {/* Title row */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <h1 className="text-xl font-sans font-semibold text-ink-primary leading-tight">
          {cellLabel}
        </h1>
        <GradeChip grade={grade} size="md" />
        <DriftChip status={cell.drift_status} />
      </div>

      {/* Tier / tenure / action tags */}
      <div className="flex flex-wrap gap-2 mb-5">
        <span className="px-2 py-0.5 rounded-[2px] bg-paper-deep text-ink-secondary text-[11px] font-sans font-medium">
          {cell.cap_tier}
        </span>
        <span className="px-2 py-0.5 rounded-[2px] bg-paper-deep text-ink-secondary text-[11px] font-sans font-medium">
          {cell.tenure}
        </span>
        <span
          className={[
            'px-2 py-0.5 rounded-[2px] text-[11px] font-sans font-semibold',
            cell.action === 'POSITIVE' ? 'bg-signal-pos/20 text-signal-pos' :
            cell.action === 'NEGATIVE' ? 'bg-signal-neg/20 text-signal-neg' :
            'bg-paper-deep text-ink-secondary',
          ].join(' ')}
        >
          {cell.action}
        </span>
      </div>

      {/* Stats row */}
      <div
        className="flex flex-wrap gap-6 divide-x divide-paper-rule"
        role="group"
        aria-label="Cell statistics"
      >
        <StatPill label="IC" value={icDisplay} />
        <div className="pl-6">
          <StatPill label="Fric-adj excess" value={fricDisplay} />
        </div>
        <div className="pl-6">
          <StatPill
            label="Predicted excess"
            value={predictedDisplay}
            valueClassName={
              cell.predicted_excess && parseFloat(cell.predicted_excess) > 0
                ? 'text-signal-pos'
                : cell.predicted_excess && parseFloat(cell.predicted_excess) < 0
                ? 'text-signal-neg'
                : ''
            }
          />
        </div>
        <div className="pl-6">
          <StatPill label="BH-FDR q" value={bhFdrDisplay} />
        </div>
      </div>
    </header>
  )
}

export default CellHero
