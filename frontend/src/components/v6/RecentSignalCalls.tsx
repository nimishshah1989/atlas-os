'use client'

// frontend/src/components/v6/RecentSignalCalls.tsx
//
// C.17 — Recent signal_calls strip for /v6/today.
//
// Displays last 20 signal_call events in a sortable table.
// Cols: ticker | cell | action | entry_date | confidence
// Each row links to /v6/stocks/[iid]
// Empty-state: "No signal_calls in the last 7 days"
//
// Sort state is client-side (no re-fetch on sort).

import { useState, useMemo } from 'react'
import Link from 'next/link'
import type { SignalCallEvent } from '@/lib/queries/v6/recent_signal_calls'

// ---------------------------------------------------------------------------
// Prop types
// ---------------------------------------------------------------------------

export interface RecentSignalCallsProps {
  calls: SignalCallEvent[]
}

// ---------------------------------------------------------------------------
// Sort types
// ---------------------------------------------------------------------------

type SortCol = 'ticker' | 'cell_name' | 'action' | 'entry_date' | 'confidence'
type SortDir = 'asc' | 'desc'

// ---------------------------------------------------------------------------
// Action pill
// ---------------------------------------------------------------------------

function ActionPill({ action }: { action: 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE' }) {
  const cls =
    action === 'POSITIVE'
      ? 'bg-signal-pos/15 text-signal-pos'
      : action === 'NEGATIVE'
        ? 'bg-signal-neg/15 text-signal-neg'
        : 'bg-paper-deep text-ink-secondary'
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-medium uppercase tracking-wide ${cls}`}
    >
      {action}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Sort header button
// ---------------------------------------------------------------------------

function SortTh({
  col,
  label,
  activeCol,
  dir,
  onSort,
  className = '',
}: {
  col: SortCol
  label: string
  activeCol: SortCol
  dir: SortDir
  onSort: (col: SortCol) => void
  className?: string
}) {
  const isActive = activeCol === col
  return (
    <th
      className={`px-3 py-2 text-left font-sans text-[10px] font-medium uppercase tracking-wider text-ink-tertiary cursor-pointer select-none hover:text-ink-primary transition-colors ${className}`}
      onClick={() => onSort(col)}
      aria-sort={isActive ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      {label}
      {isActive && (
        <span className="ml-1 text-teal">{dir === 'asc' ? '↑' : '↓'}</span>
      )}
    </th>
  )
}

// ---------------------------------------------------------------------------
// Confidence formatter — string Decimal 0..1 → percentage string
// ---------------------------------------------------------------------------

function fmtConf(raw: string): string {
  const n = parseFloat(raw)
  if (Number.isNaN(n)) return '—'
  return `${Math.round(n * 100)}%`
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function RecentSignalCalls({ calls }: RecentSignalCallsProps) {
  const [sortCol, setSortCol] = useState<SortCol>('entry_date')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  function handleSort(col: SortCol) {
    if (col === sortCol) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortCol(col)
      setSortDir('desc')
    }
  }

  const sorted = useMemo(() => {
    return [...calls].sort((a, b) => {
      let cmp = 0
      switch (sortCol) {
        case 'ticker':
          cmp = a.ticker.localeCompare(b.ticker)
          break
        case 'cell_name':
          cmp = a.cell_name.localeCompare(b.cell_name)
          break
        case 'action':
          cmp = a.action.localeCompare(b.action)
          break
        case 'entry_date':
          cmp = a.entry_date.localeCompare(b.entry_date)
          break
        case 'confidence':
          cmp = parseFloat(a.confidence_unconditional) - parseFloat(b.confidence_unconditional)
          break
      }
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [calls, sortCol, sortDir])

  if (calls.length === 0) {
    return (
      <div className="border border-paper-rule rounded-[2px] bg-paper px-4 py-6">
        <p className="font-sans text-xs text-ink-tertiary text-center">
          No signal_calls in the last 7 days
        </p>
      </div>
    )
  }

  return (
    <div className="border border-paper-rule rounded-[2px] bg-paper overflow-x-auto">
      <table className="w-full min-w-[600px]">
        <thead className="border-b border-paper-rule">
          <tr>
            <SortTh col="ticker" label="Ticker" activeCol={sortCol} dir={sortDir} onSort={handleSort} className="pl-4" />
            <SortTh col="cell_name" label="Cell" activeCol={sortCol} dir={sortDir} onSort={handleSort} />
            <SortTh col="action" label="Action" activeCol={sortCol} dir={sortDir} onSort={handleSort} />
            <SortTh col="entry_date" label="Entry date" activeCol={sortCol} dir={sortDir} onSort={handleSort} />
            <SortTh col="confidence" label="Confidence" activeCol={sortCol} dir={sortDir} onSort={handleSort} className="pr-4" />
          </tr>
        </thead>
        <tbody className="divide-y divide-paper-rule">
          {sorted.map(call => (
            <tr
              key={call.signal_call_id}
              className="hover:bg-paper-rule/10 transition-colors"
            >
              <td className="px-3 py-2 pl-4">
                <Link
                  href={`/v6/stocks/${call.instrument_id}`}
                  className="font-mono text-sm font-semibold text-ink-primary hover:text-teal hover:underline"
                  aria-label={`View stock ${call.ticker}`}
                >
                  {call.ticker}
                </Link>
              </td>
              <td className="px-3 py-2">
                <Link
                  href={`/v6/cells/${encodeURIComponent(call.cell_id)}`}
                  className="font-sans text-xs text-ink-secondary hover:text-teal hover:underline"
                >
                  {call.cell_name}
                </Link>
              </td>
              <td className="px-3 py-2">
                <ActionPill action={call.action} />
              </td>
              <td className="px-3 py-2 font-mono text-xs tabular-nums text-ink-secondary">
                {call.entry_date}
              </td>
              <td className="px-3 py-2 pr-4 font-mono text-xs tabular-nums text-right text-ink-primary">
                {fmtConf(call.confidence_unconditional)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default RecentSignalCalls
