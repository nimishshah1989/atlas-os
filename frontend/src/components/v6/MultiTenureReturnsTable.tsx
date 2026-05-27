'use client'

// frontend/src/components/v6/MultiTenureReturnsTable.tsx
//
// Compact 6-tenure returns table. Renders one row per instrument.
// Each return cell is colour-thresholded via signal-* tokens.
//
// Data contract: MultiTenureReturns[] from lib/queries/v6/multi_tenure_returns
// Display: signedPct() for formatted strings; toNumber() ONLY at the
//          threshold-check site (never for display or currency).

import type { MultiTenureReturns } from '@/lib/queries/v6/multi_tenure_returns'
import { signedPct, toNumber } from '@/lib/v6/decimal'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type TenureKey = 'ret_1d' | 'ret_1w' | 'ret_1m' | 'ret_3m' | 'ret_6m' | 'ret_12m'

export interface MultiTenureReturnsTableProps {
  /** Batch — one row per iid + symbol */
  rows: MultiTenureReturns[]
  /** Optional: emphasise one row with bg-paper-deep + ring-2 ring-signal-pos */
  highlightIid?: string
  /** Which return columns to show (default: all 6) */
  showColumns?: TenureKey[]
  className?: string
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ALL_COLUMNS: TenureKey[] = [
  'ret_1d',
  'ret_1w',
  'ret_1m',
  'ret_3m',
  'ret_6m',
  'ret_12m',
]

const COLUMN_LABELS: Record<TenureKey, string> = {
  ret_1d: '1d',
  ret_1w: '1w',
  ret_1m: '1m',
  ret_3m: '3m',
  ret_6m: '6m',
  ret_12m: '12m',
}

const EM_DASH = '—'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Determine the Tailwind text colour class for a return value string. */
function returnColorClass(value: string | null): string {
  if (value == null) return 'text-ink-tertiary'
  // toNumber only at the threshold-check site — not used for display
  let n: number | null
  try {
    n = toNumber(value)
  } catch {
    return 'text-ink-tertiary'
  }
  if (n === null) return 'text-ink-tertiary'
  if (n > 0) return 'text-signal-pos'
  if (n < 0) return 'text-signal-neg'
  return 'text-ink-tertiary'
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function MultiTenureReturnsTable({
  rows,
  highlightIid,
  showColumns = ALL_COLUMNS,
  className = '',
}: MultiTenureReturnsTableProps) {
  const colCount = showColumns.length + 1 // +1 for ticker column

  return (
    <div className={['overflow-auto', className].filter(Boolean).join(' ')}>
      <table
        role="table"
        className="w-full text-sm font-mono border-separate border-spacing-0"
      >
        {/* ── Sticky header ───────────────────────────────────────────── */}
        <thead>
          <tr role="row" className="sticky top-0 z-10 bg-paper">
            <th
              role="columnheader"
              scope="col"
              className="py-2 pl-3 pr-4 text-left text-xs font-semibold text-ink-tertiary uppercase tracking-wide border-b border-ink-tertiary/20 whitespace-nowrap"
            >
              Ticker
            </th>
            {showColumns.map((key) => (
              <th
                key={key}
                role="columnheader"
                scope="col"
                className="py-2 px-3 text-right text-xs font-semibold text-ink-tertiary uppercase tracking-wide border-b border-ink-tertiary/20 whitespace-nowrap"
              >
                {COLUMN_LABELS[key]}
              </th>
            ))}
          </tr>
        </thead>

        {/* ── Body ────────────────────────────────────────────────────── */}
        <tbody>
          {rows.length === 0 ? (
            <tr role="row">
              <td
                role="cell"
                colSpan={colCount}
                className="py-6 text-center text-sm text-ink-tertiary"
              >
                No return data available
              </td>
            </tr>
          ) : (
            rows.map((row) => {
              const isHighlighted = highlightIid != null && row.iid === highlightIid
              const rowClass = isHighlighted
                ? 'bg-paper-deep ring-2 ring-inset ring-signal-pos'
                : 'hover:bg-paper-deep/50'

              // Derive a display ticker: iid is a UUID; fall back to iid[:8]
              // In practice callers will pass rows that include a symbol field,
              // but the base type only has iid. We display the iid short-form
              // until a symbol prop is available.
              const ticker = row.iid.slice(0, 8).toUpperCase()

              return (
                <tr key={row.iid} role="row" className={rowClass}>
                  {/* Ticker cell */}
                  <td
                    role="cell"
                    className="py-2 pl-3 pr-4 text-left text-xs font-semibold text-ink-primary whitespace-nowrap"
                    aria-label={`${ticker} ticker`}
                  >
                    {ticker}
                  </td>

                  {/* Return cells */}
                  {showColumns.map((key) => {
                    const value = row[key]
                    const colorClass = returnColorClass(value)
                    const display = value != null ? signedPct(value) : EM_DASH
                    const label = `${ticker} ${COLUMN_LABELS[key]}: ${display}`

                    return (
                      <td
                        key={key}
                        role="cell"
                        className={[
                          'py-2 px-3 text-right text-xs tabular-nums',
                          colorClass,
                        ].join(' ')}
                        aria-label={label}
                      >
                        {display}
                      </td>
                    )
                  })}
                </tr>
              )
            })
          )}
        </tbody>
      </table>
    </div>
  )
}

export default MultiTenureReturnsTable
