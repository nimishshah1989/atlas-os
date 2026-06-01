'use client'
// frontend/src/components/v6/CellMatrix.tsx — C.14
// 3×8 grid hero. GradeChip, drift chip, held overlay, failed-gate microcopy.
// allow-large: grid hero + 3-variant microcopy requires full type/render logic

import { useRouter } from 'next/navigation'
import { GradeChip, type Grade } from '@/components/v6/GradeChip'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { toNumber } from '@/lib/v6/decimal'
import type { MatrixCell, CapTier, Tenure, CellState, DriftStatus } from '@/lib/queries/v6/cells'

const TIERS: CapTier[] = ['Large', 'Mid', 'Small']
const COLUMNS: { tenure: Tenure; action: CellState; label: string }[] = [
  { tenure: '1m',  action: 'POSITIVE', label: '1m POS' },
  { tenure: '1m',  action: 'NEGATIVE', label: '1m NEG' },
  { tenure: '3m',  action: 'POSITIVE', label: '3m POS' },
  { tenure: '3m',  action: 'NEGATIVE', label: '3m NEG' },
  { tenure: '6m',  action: 'POSITIVE', label: '6m POS' },
  { tenure: '6m',  action: 'NEGATIVE', label: '6m NEG' },
  { tenure: '12m', action: 'POSITIVE', label: '12m POS' },
  { tenure: '12m', action: 'NEGATIVE', label: '12m NEG' },
]

export type CellMatrixProps = {
  cells: MatrixCell[]
  heldIidSet?: Set<string>
  showLegend?: boolean
}

function deriveGrade(cell: MatrixCell): Grade {
  if (cell.n_gate_pass === 0) return 'failed-gate'
  const conf = toNumber(cell.confidence_unconditional) ?? 0
  if (conf >= 0.20) return 'AAA'
  if (conf >= 0.15) return 'AA'
  if (conf >= 0.10) return 'A'
  if (conf >= 0.05) return 'BBB'
  if (conf >= 0.02) return 'BB'
  return 'B'
}

// Failed-gate microcopy: (n_gate_pass=0, n_candidates>0) → "No rule survived"
// (n_gate_pass=0, n_candidates=0) → "No candidates tested"
// (empty rule_dsl) → "Insufficient data"
function failedGateCopy(cell: MatrixCell): string {
  // n_candidates null-equivalent: 0 with null confidence means no data loaded
  const confIsNull = cell.confidence_unconditional === '0' &&
    cell.rule_dsl != null &&
    Object.keys(cell.rule_dsl).length === 0

  if (confIsNull || cell.n_candidates === 0) {
    // Distinguish: were candidates loaded at all?
    if (cell.n_candidates === 0 && !confIsNull) return 'No candidates tested'
    return 'Insufficient data'
  }
  // n_gate_pass=0, n_candidates>0
  return 'No rule survived'
}

function fmtConf(s: string): string {
  const n = toNumber(s)
  if (n === null) return '—'
  return `${(n * 100).toFixed(1)}%`
}

function fmtExcess(s: string | null): string {
  if (s == null) return '—'
  const n = toNumber(s)
  if (n === null) return '—'
  const pct = n * 100
  const sign = pct >= 0 ? '+' : ''
  return `${sign}${pct.toFixed(1)}%`
}

function DriftChip({ status }: { status: DriftStatus }): React.ReactElement | null {
  if (status === 'healthy') return null
  const cls = status === 'drift_warn'
    ? 'bg-signal-warn/20 text-signal-warn'
    : 'bg-signal-neg/20 text-signal-neg'
  const label = status === 'drift_warn' ? 'DRIFT' : 'DEPRECATED'
  return (
    <span
      role="status"
      aria-label={`drift status: ${status}`}
      className={`inline-flex items-center font-sans text-[9px] font-semibold uppercase rounded-[2px] px-[5px] py-[2px] leading-none ${cls}`}
      style={{ letterSpacing: '0.10em' }}
    >
      {label}
    </span>
  )
}

// Tile uses overlay-button pattern: nav <button> covers the div, InfoTooltip
// sits above it via z-index to avoid illegal nested <button> elements.
function MatrixTile({
  cell,
  nHeld,
  onNavigate,
}: {
  cell: MatrixCell | undefined
  nHeld: number
  onNavigate: (cellId: string) => void
}): React.ReactElement {
  if (!cell) {
    return (
      <div
        className="h-[100px] w-full border border-paper-rule rounded-[2px] bg-paper-rule/10 flex items-center justify-center"
        aria-hidden="true"
      >
        <span className="font-mono text-[10px] text-ink-tertiary">—</span>
      </div>
    )
  }

  const grade = deriveGrade(cell)
  const isFailed = grade === 'failed-gate'
  const microcopy = isFailed ? failedGateCopy(cell) : null

  // ARIA label per spec
  const ariaLabel = [
    `${cell.cap_tier} ${cell.tenure} ${cell.action}:`,
    `grade ${grade},`,
    `drift ${cell.drift_status},`,
    `${nHeld} held`,
  ].join(' ')

  const tileColor = isFailed
    ? 'border-paper-rule bg-paper-deep'
    : 'border-paper-rule bg-paper hover:bg-paper-deep/60'

  const isNegative = cell.action === 'NEGATIVE'

  return (
    /* Wrapper div — relative context for overlay button + held badge */
    <div
      className={`relative h-[100px] w-full border rounded-[2px] flex flex-col gap-0.5 p-2 ${tileColor} group`}
    >
      {/* Navigation button — full overlay, behind InfoTooltip */}
      <button
        type="button"
        className="absolute inset-0 rounded-[2px] focus:outline-none focus-visible:ring-2 focus-visible:ring-teal z-0"
        aria-label={ariaLabel}
        onClick={() => onNavigate(cell.cell_id)}
      />

      {/* Tile content — positioned above nav button via z-10 */}
      <div className="relative z-10 flex flex-col gap-0.5 h-full pointer-events-none">
        {/* Top row: cell_id label + grade chip */}
        <div className="flex items-start justify-between gap-1">
          <span className="font-sans text-[9px] uppercase tracking-wider text-ink-tertiary leading-tight truncate">
            {cell.cap_tier} · {cell.tenure} · {cell.action.charAt(0)}
          </span>
          <GradeChip grade={grade} size="sm" />
        </div>

        {/* Metrics row */}
        {isFailed ? (
          <div className="flex-1 flex items-center justify-center">
            <span className="font-sans text-[10px] text-ink-tertiary text-center leading-tight">
              {microcopy}
            </span>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-1 font-mono text-[10px] tabular-nums text-ink-primary">
              <span>{fmtConf(cell.confidence_unconditional)}</span>
              <span className="text-ink-tertiary">·</span>
              <span>{fmtExcess(cell.friction_adjusted_excess)}</span>
            </div>
            {cell.predicted_excess != null && (
              <div className="font-mono text-[9px] tabular-nums text-ink-secondary">
                pred {fmtExcess(cell.predicted_excess)}
              </div>
            )}
          </>
        )}

        {/* Bottom row: drift chip + NEGATIVE caveat tooltip */}
        <div className="flex items-center gap-1 mt-auto pointer-events-auto">
          <DriftChip status={cell.drift_status} />
          {isNegative && !isFailed && (
            <InfoTooltip
              content="NEGATIVE cells are back-tested on surviving stocks only. Survivorship bias applies."
              translation="Past signal may be overstated for avoid calls."
            />
          )}
        </div>
      </div>

      {/* Held-count overlay — top-right corner badge (above nav button) */}
      {nHeld > 0 && (
        <span
          aria-label={`${nHeld} held`}
          className="absolute top-1.5 right-1.5 z-10 inline-flex items-center justify-center min-w-[18px] h-[18px] rounded-full bg-teal text-paper font-sans text-[9px] font-semibold leading-none px-1"
        >
          {nHeld}
        </span>
      )}
    </div>
  )
}

function TierRow({
  tier,
  cells,
  heldCounts,
  onNavigate,
}: {
  tier: CapTier
  cells: MatrixCell[]
  heldCounts: Record<string, number>
  onNavigate: (cellId: string) => void
}): React.ReactElement {
  return (
    <>
      <div className="font-sans text-[11px] font-semibold text-ink-secondary uppercase tracking-wider flex items-center">
        {tier}
      </div>
      {COLUMNS.map((col) => {
        const cell = cells.find(
          (c) => c.cap_tier === tier && c.tenure === col.tenure && c.action === col.action,
        )
        const nHeld = cell ? (heldCounts[cell.cell_id] ?? 0) : 0
        return (
          <MatrixTile
            key={`${tier}-${col.label}`}
            cell={cell}
            nHeld={nHeld}
            onNavigate={onNavigate}
          />
        )
      })}
    </>
  )
}

export function CellMatrix({
  cells,
  heldIidSet = new Set(),
  showLegend = true,
}: CellMatrixProps): React.ReactElement {
  const router = useRouter()

  if (cells.length === 0) {
    return (
      <div className="border border-paper-rule rounded-[2px] bg-paper p-8 text-center">
        <span className="font-sans text-sm text-ink-tertiary">Matrix data unavailable</span>
      </div>
    )
  }

  void heldIidSet  // reserved for v6.1 client-side enrichment

  const heldCounts: Record<string, number> = Object.fromEntries(
    cells.map((c) => [c.cell_id, c.n_held_firing]),
  )

  function handleNavigate(cellId: string): void {
    // Route to stocks screener filtered by cell — /v6/cells/ doesn't exist as a route.
    // cell_id format: "{tier}-{tenure}-{direction}" e.g. "Large-12m-POSITIVE"
    // The stocks screener accepts a cell query param for column filtering.
    router.push(`/stocks?cell=${encodeURIComponent(cellId)}`)
  }

  return (
    <div className="border border-paper-rule rounded-[2px] bg-paper p-4">
      {showLegend && (
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">
            conf · fric-adj · pred excess · drift status
          </div>
          <div className="flex items-center gap-3 font-mono text-[10px] text-ink-tertiary">
            <span className="inline-flex items-center gap-1">
              <span className="inline-block w-2.5 h-2.5 bg-signal-pos/15 border border-signal-pos/40 rounded-[2px]" />
              AAA–A (conf ≥10%)
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="inline-block w-2.5 h-2.5 bg-signal-warn/10 border border-signal-warn/30 rounded-[2px]" />
              BBB–B
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="inline-block w-2.5 h-2.5 bg-paper-deep border border-paper-rule rounded-[2px]" />
              No signal
            </span>
          </div>
        </div>
      )}

      <div className="grid grid-cols-[64px_repeat(8,1fr)] gap-1.5">
        {/* Column header row */}
        <div />
        {COLUMNS.map((col) => (
          <div
            key={col.label}
            className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary text-center pb-1"
          >
            {col.label}
          </div>
        ))}

        {/* Three tier rows */}
        {TIERS.map((tier) => (
          <TierRow
            key={tier}
            tier={tier}
            cells={cells}
            heldCounts={heldCounts}
            onNavigate={handleNavigate}
          />
        ))}
      </div>
    </div>
  )
}

export default CellMatrix
