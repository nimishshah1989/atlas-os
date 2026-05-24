// frontend/src/components/v6/CellMatrix.tsx
//
// 3×8 grid hero (Large/Mid/Small rows × 4 tenures × 2 directions = 8 cols).
// Each cell renders best-rule IC, fric-adj excess (annualized %), gate-pass.
// Click → navigates to /matrix/<cell_id>. Empty cells (gate_pass == 0) are
// rendered in the empty style and not clickable.

import Link from 'next/link'
import type { CellDefinition, Tier, Tenure, Direction } from '@/lib/api/v1'
import { icTier, icTierClasses, formatIC, formatFricAdj, formatGatePass } from '@/lib/format-cell'

const TIERS: Tier[] = ['Large', 'Mid', 'Small']
const COLUMNS: { tenure: Tenure; direction: Direction; label: string }[] = [
  { tenure: '1m',  direction: 'POSITIVE', label: '1m POS' },
  { tenure: '1m',  direction: 'NEGATIVE', label: '1m NEG' },
  { tenure: '3m',  direction: 'POSITIVE', label: '3m POS' },
  { tenure: '3m',  direction: 'NEGATIVE', label: '3m NEG' },
  { tenure: '6m',  direction: 'POSITIVE', label: '6m POS' },
  { tenure: '6m',  direction: 'NEGATIVE', label: '6m NEG' },
  { tenure: '12m', direction: 'POSITIVE', label: '12m POS' },
  { tenure: '12m', direction: 'NEGATIVE', label: '12m NEG' },
]

type Props = {
  cells: CellDefinition[]
  /** Cell IDs to highlight as "lit today". */
  highlight?: string[]
  /** Show row/column legend in the header strip. */
  showLegend?: boolean
}

function findCell(cells: CellDefinition[], tier: Tier, tenure: Tenure, direction: Direction): CellDefinition | undefined {
  return cells.find(c => c.tier === tier && c.tenure === tenure && c.direction === direction)
}

function MatrixCell({
  cell,
  highlighted,
}: { cell: CellDefinition | undefined; highlighted: boolean }) {
  if (!cell) {
    return (
      <div className="h-[68px] w-full border border-paper-rule rounded-[2px] bg-paper-rule/15 text-ink-tertiary flex items-center justify-center font-mono text-[10px]">
        —
      </div>
    )
  }
  const clickable = cell.n_gate_pass > 0
  const tier = icTier(cell.best_rule_ic != null ? Math.abs(cell.best_rule_ic) : null)
  const cls = icTierClasses(clickable ? tier : 'empty')
  const ring = highlighted ? 'ring-1 ring-teal' : ''
  const inner = (
    <div className={`h-[68px] w-full border rounded-[2px] flex flex-col items-center justify-center px-1 ${cls} ${ring} ${clickable ? 'hover:brightness-105' : ''} transition-all`}>
      <div className="font-mono text-[14px] font-semibold leading-none tabular-nums">
        {cell.best_rule_ic != null ? formatIC(cell.best_rule_ic) : '—'}
      </div>
      <div className="font-mono text-[10px] tabular-nums opacity-80 mt-0.5">
        {formatFricAdj(cell.best_rule_fric_adj_ann)}
      </div>
      <div className="font-mono text-[9px] tabular-nums opacity-70 mt-0.5">
        {formatGatePass(cell.n_gate_pass, cell.n_candidates)}
      </div>
    </div>
  )
  if (!clickable) return inner
  return (
    <Link
      href={`/matrix/${encodeURIComponent(cell.cell_id)}`}
      title={`${cell.cell_id} — ${cell.best_archetype ?? 'no rule'} — ${cell.reason}`}
      className="block"
    >
      {inner}
    </Link>
  )
}

export function CellMatrix({ cells, highlight = [], showLegend = true }: Props) {
  return (
    <div className="border border-paper-rule rounded-[2px] bg-paper p-4">
      {showLegend && (
        <div className="flex items-center justify-between mb-3">
          <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">
            Each cell: best-rule IC · fric-adj excess (ann) · gate-pass / candidates
          </div>
          <div className="flex items-center gap-3 font-mono text-[10px] text-ink-tertiary">
            <span className="inline-flex items-center gap-1">
              <span className="inline-block w-2.5 h-2.5 bg-signal-pos/15 border border-signal-pos/40 rounded-[2px]" />
              IC ≥ 0.05
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="inline-block w-2.5 h-2.5 bg-teal/10 border border-teal/30 rounded-[2px]" />
              0.02–0.05
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="inline-block w-2.5 h-2.5 bg-signal-warn/10 border border-signal-warn/30 rounded-[2px]" />
              0–0.02
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="inline-block w-2.5 h-2.5 bg-signal-neg/10 border border-signal-neg/30 rounded-[2px]" />
              IC &lt; 0
            </span>
          </div>
        </div>
      )}
      <div className="grid grid-cols-[64px_repeat(8,1fr)] gap-1.5">
        {/* Header row */}
        <div />
        {COLUMNS.map(col => (
          <div
            key={col.label}
            className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary text-center pb-1"
          >
            {col.label}
          </div>
        ))}
        {/* 3 data rows */}
        {TIERS.map(tier => (
          <RowFragment key={tier} tier={tier} cells={cells} highlight={highlight} />
        ))}
      </div>
    </div>
  )
}

function RowFragment({
  tier,
  cells,
  highlight,
}: {
  tier: Tier
  cells: CellDefinition[]
  highlight: string[]
}) {
  return (
    <>
      <div className="font-sans text-[11px] font-semibold text-ink-secondary uppercase tracking-wider flex items-center">
        {tier}
      </div>
      {COLUMNS.map(col => {
        const cell = findCell(cells, tier, col.tenure, col.direction)
        const cid = cell?.cell_id ?? ''
        return (
          <MatrixCell
            key={`${tier}-${col.label}`}
            cell={cell}
            highlighted={highlight.includes(cid)}
          />
        )
      })}
    </>
  )
}
