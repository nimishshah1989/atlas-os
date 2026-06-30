// frontend/src/components/v6/stocks/Matrix24Cell.tsx
// Page 05 · 24-cell count matrix
// 3 rows (Large / Mid / Small) × 8 cols (1m POS/NEG · 3m POS/NEG · 6m POS/NEG · 12m POS/NEG)
// Each cell shows count + avg IC from mv_stock_landscape grouping.
// Color intensity based on count: strong ≥ 15, medium ≥ 8, weak > 0.
// Server component (pure rendering, no client state).

import type { MatrixCellAgg } from '@/lib/queries/v6/stocks-landscape'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

const TIERS = ['Large', 'Mid', 'Small'] as const
const TENURES = ['1m', '3m', '6m', '12m'] as const
const SIGNS = ['POS', 'NEG'] as const

type CapTier = (typeof TIERS)[number]
type Tenure = (typeof TENURES)[number]
type ActionSign = (typeof SIGNS)[number]

type ColSpec = { tenure: Tenure; sign: ActionSign; label: string }

const COLUMNS: ColSpec[] = [
  { tenure: '1m',  sign: 'POS', label: '1m POS' },
  { tenure: '1m',  sign: 'NEG', label: '1m NEG' },
  { tenure: '3m',  sign: 'POS', label: '3m POS' },
  { tenure: '3m',  sign: 'NEG', label: '3m NEG' },
  { tenure: '6m',  sign: 'POS', label: '6m POS' },
  { tenure: '6m',  sign: 'NEG', label: '6m NEG' },
  { tenure: '12m', sign: 'POS', label: '12m POS' },
  { tenure: '12m', sign: 'NEG', label: '12m NEG' },
]

// ---------------------------------------------------------------------------
// Cell color logic (exported for tests)
// ---------------------------------------------------------------------------

export type CellVariant =
  | 'pos-strong'
  | 'pos'
  | 'pos-weak'
  | 'neg-strong'
  | 'neg'
  | 'neg-weak'
  | 'empty'

export function getCellVariant(count: number, sign: ActionSign): CellVariant {
  if (count === 0) return 'empty'
  if (sign === 'POS') {
    if (count >= 15) return 'pos-strong'
    if (count >= 8)  return 'pos'
    return 'pos-weak'
  }
  // NEG
  if (count >= 15) return 'neg-strong'
  if (count >= 8)  return 'neg'
  return 'neg-weak'
}

function cellBg(variant: CellVariant): string {
  const map: Record<CellVariant, string> = {
    'pos-strong': 'bg-signal-pos/42 text-paper',
    'pos':        'bg-signal-pos/22',
    'pos-weak':   'bg-signal-pos/10',
    'neg-strong': 'bg-signal-neg/42 text-paper',
    'neg':        'bg-signal-neg/22',
    'neg-weak':   'bg-signal-neg/10',
    'empty':      'bg-paper-soft text-ink-quaternary',
  }
  return map[variant]
}

function icColor(variant: CellVariant): string {
  if (variant === 'pos-strong' || variant === 'neg-strong') return 'text-paper/85'
  return 'text-ink-tertiary'
}

export function fmtIc(v: string | null): string {
  if (v === null) return 'unknown'
  const n = parseFloat(v)
  if (isNaN(n)) return 'unknown'
  // Display as .062 format (3 decimal places without leading zero)
  return `.${Math.round(Math.abs(n) * 1000).toString().padStart(3, '0')}`
}

// ---------------------------------------------------------------------------
// Cell lookup
// ---------------------------------------------------------------------------

function findCell(
  cells: MatrixCellAgg[],
  tier: CapTier,
  tenure: Tenure,
  sign: ActionSign,
): MatrixCellAgg | undefined {
  return cells.find(
    c => c.cap_tier === tier && c.tenure === tenure && c.action_sign === sign,
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function Matrix24Cell({ cells }: { cells: MatrixCellAgg[] }) {
  // Compute skew read: find the strongest cell
  const strongest = cells.reduce<MatrixCellAgg | null>((best, c) => {
    if (!best || c.count > best.count) return c
    return best
  }, null)

  return (
    <div className="bg-paper border border-paper-rule rounded-sm p-5">
      <div className="flex items-baseline justify-between mb-3">
        <div className="font-serif text-[18px] text-ink-primary">
          24-cell matrix · firing tonight
        </div>
        <div className="flex gap-[6px] items-center">
          <span className="px-[10px] py-[4px] text-[11px] border rounded-sm font-medium bg-accent text-paper border-accent">
            Counts
          </span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="tbl-centered w-full border-collapse text-[12px]" aria-label="24-cell methodology matrix">
          <thead>
            <tr>
              <th className="text-left pl-[10px] pb-[6px] pt-[6px] font-sans text-[9px] tracking-[0.14em] uppercase text-ink-tertiary font-semibold bg-paper-soft border-b border-ink-rule" />
              {COLUMNS.map((col, i) => {
                const isSep = i % 2 === 1 && i < COLUMNS.length - 1
                return (
                  <th
                    key={col.label}
                    className={`pb-[6px] pt-[6px] font-sans text-[9px] tracking-[0.14em] uppercase text-ink-tertiary font-semibold bg-paper-soft border-b border-ink-rule text-center ${isSep ? 'border-l border-l-ink-rule' : ''}`}
                  >
                    {col.label}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {TIERS.map(tier => (
              <tr key={tier}>
                <td className="py-[10px] pl-3 pr-2 text-left font-sans font-medium text-ink-primary text-[12.5px] border-b border-paper-rule">
                  {tier}
                </td>
                {COLUMNS.map((col, i) => {
                  const cell = findCell(cells, tier, col.tenure, col.sign)
                  const isSep = i % 2 === 1 && i < COLUMNS.length - 1
                  return (
                    <td
                      key={col.label}
                      className={`p-0 border-b border-paper-rule text-center font-mono ${isSep ? 'border-l border-l-ink-rule' : ''}`}
                    >
                      <MatrixCellInner cell={cell} sign={col.sign} />
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Skew read */}
      {strongest && (
        <div className="mt-3 p-[10px] bg-paper-soft border border-paper-rule rounded-sm font-sans text-[11.5px] text-ink-secondary leading-relaxed">
          <strong>Skew read:</strong> Strongest cell tonight is{' '}
          <strong>
            {strongest.cap_tier} {strongest.tenure} {strongest.action_sign} ({strongest.count}, IC{' '}
            {fmtIc(strongest.avg_ic)})
          </strong>
          . {strongest.action_sign === 'POS'
            ? `${strongest.cap_tier}-tier is concentrating BUYs at the ${strongest.tenure} tenure.`
            : `${strongest.cap_tier}-tier is concentrating AVOIDs at the ${strongest.tenure} tenure.`}
        </div>
      )}

      <div className="mt-[10px] pt-2 border-t border-paper-rule font-sans text-[11px] text-ink-tertiary leading-relaxed">
        <strong className="text-ink-secondary">Click any cell</strong> to see constituent names firing in that (cap × tenure × state) bucket.
      </div>
    </div>
  )
}

// Inline cell rendering (avoids passing complex props through td element)
function MatrixCellInner({
  cell,
  sign,
}: {
  cell: MatrixCellAgg | undefined
  sign: ActionSign
}) {
  const count = cell?.count ?? 0
  const variant = getCellVariant(count, sign)
  const bg = cellBg(variant)
  const ic = icColor(variant)

  return (
    <div
      className={`px-1 py-[10px] ${bg}`}
      data-testid="matrix-cell"
      data-variant={variant}
      data-count={count}
    >
      <div className="font-mono text-[14px] font-semibold leading-none">
        {count > 0 ? count : '·'}
      </div>
      {count > 0 && (
        <div className={`font-mono text-[9px] mt-[2px] tracking-[0.05em] ${ic}`}>
          IC {fmtIc(cell?.avg_ic ?? null)}
        </div>
      )}
    </div>
  )
}
