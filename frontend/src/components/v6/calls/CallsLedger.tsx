'use client'
// allow-large: full-featured data table with filter/sort/virtualization — splitting would break encapsulation

// frontend/src/components/v6/calls/CallsLedger.tsx
//
// Full call ledger table for /calls (Page 08 — Calls Performance).
// Displays all 587 signal_call rows from mv_calls_performance.
//
// Features:
//   - Client-side filtering by status (all/in_flight/closed) and direction
//   - Client-side search by symbol, company_name, or cell label
//   - Sortable column headers with aria-sort (M3)
//   - @tanstack/react-virtual for row virtualization when >200 rows (I2)
//   - Plain <tbody> for <=200 rows (test-friendly, same row content)
//   - Status from MV status column directly (I1 — not synthesized from exit_date)
//   - ActionBadge for direction (I3 — reused component)
//   - fmtSignedPct for sign-aware formatting (C2)
//   - Realized excess column shows real data (not — for all rows)

import { useState, useMemo, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import type { CallRow } from '@/lib/queries/v6/calls'
import { fmtSignedPct } from '@/lib/format-number'
import { formatIST } from '@/lib/format-date'
import { ActionBadge } from '@/components/v6/shared/ActionBadge'

interface CallsLedgerProps {
  calls: CallRow[]
}

type SortCol =
  | 'symbol'
  | 'cell_label'
  | 'cap_tier'
  | 'tenure'
  | 'entry_date'
  | 'days_in_position'
  | 'predicted_excess'
  | 'realized_excess_pct'
type SortDir = 'asc' | 'desc'
type StatusFilter = 'all' | 'in_flight' | 'closed'
type DirectionFilter = 'all' | 'BUY' | 'AVOID'

/** I1: status comes directly from MV, not synthesized from exit_date */
function StatusChip({ status }: { status: string }) {
  const isOpen = status === 'in_flight'
  const cls = isOpen
    ? 'bg-signal-info/20 text-signal-info border border-signal-info/30'
    : 'bg-paper-deep text-ink-4 border border-paper-rule'
  return (
    <span className={`text-[9px] font-bold uppercase tracking-[0.12em] px-1.5 py-0.5 rounded-[2px] ${cls}`}>
      {isOpen ? 'IN FLIGHT' : 'CLOSED'}
    </span>
  )
}

function pctClass(val: number | null): string {
  if (val === null) return 'text-ink-4'
  return val >= 0 ? 'text-signal-pos' : 'text-signal-neg'
}

function SortTh({
  col,
  label,
  unit,
  activeCol,
  dir,
  onClick,
  align = 'center',
  groupSep = false,
}: {
  col: SortCol
  label: string
  unit?: string
  activeCol: SortCol
  dir: SortDir
  onClick: (col: SortCol) => void
  align?: 'left' | 'center'
  groupSep?: boolean
}) {
  const isActive = activeCol === col
  // M3: aria-sort on sortable headers (pattern from RecentSignalCalls.tsx:77)
  const ariaSort = isActive ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'
  return (
    <th
      className={`px-2 py-[9px] text-[9px] font-semibold uppercase tracking-[0.13em] text-ink-4 bg-paper-soft border-b border-ink-rule cursor-pointer select-none ${align === 'left' ? 'text-left pl-[14px]' : 'text-center'} ${groupSep ? 'border-l border-paper-rule' : ''}`}
      onClick={() => onClick(col)}
      aria-sort={ariaSort}
    >
      {label}
      {isActive ? (dir === 'desc' ? ' ↓' : ' ↑') : ''}
      {unit && (
        <span className="block text-[8px] text-ink-4 font-mono tracking-[0.04em] normal-case mt-0.5">
          {unit}
        </span>
      )}
    </th>
  )
}

/** Shared row content — used by both plain <tr> and virtual div rendering */
function RowCells({ row }: { row: CallRow }) {
  return (
    <>
      {/* Symbol · Company */}
      <td className="px-[14px] py-2 border-b border-paper-rule text-left">
        <div className="flex flex-col gap-[1px]">
          {/* M4: MV always has symbol — no signal_call_id fallback needed */}
          <span className="font-mono font-semibold text-ink-primary text-[11.5px] tracking-[0.02em]">
            {row.symbol}
          </span>
          {row.company_name && (
            <span className="text-[10px] text-ink-4 truncate max-w-[160px]">{row.company_name}</span>
          )}
        </div>
      </td>
      {/* Status — I1: from MV status column directly */}
      <td className="px-2 py-2 border-b border-paper-rule text-center">
        <StatusChip status={row.status} />
      </td>
      {/* Cell */}
      <td className="px-2 py-2 border-b border-paper-rule text-center font-mono text-[11.5px] text-ink-secondary">
        {row.cell_label}
      </td>
      {/* Tier */}
      <td className="px-2 py-2 border-b border-paper-rule text-center font-mono text-[11.5px] text-ink-secondary">
        {row.cap_tier}
      </td>
      {/* Tenure */}
      <td className="px-2 py-2 border-b border-paper-rule text-center font-mono text-[11.5px] text-ink-secondary">
        {row.tenure}
      </td>
      {/* Direction — I3: ActionBadge reuse */}
      <td className="px-2 py-2 border-b border-paper-rule text-center">
        <ActionBadge action={row.action} />
      </td>
      {/* Opened */}
      <td className="px-2 py-2 border-b border-paper-rule border-l border-paper-rule text-center font-mono text-[11.5px] text-ink-secondary">
        {formatIST(row.entry_date)}
      </td>
      {/* Days */}
      <td className="px-2 py-2 border-b border-paper-rule text-center font-mono text-[11.5px] text-ink-secondary">
        {row.days_in_position}d
      </td>
      {/* Pred ex — C2: sign-aware */}
      <td
        className={`px-2 py-2 border-b border-paper-rule border-l border-paper-rule text-center font-mono text-[11.5px] font-semibold ${pctClass(row.predicted_excess)}`}
      >
        {fmtSignedPct(row.predicted_excess)}
      </td>
      {/* Realized ex — C2: sign-aware, real data */}
      <td
        className={`px-2 py-2 border-b border-paper-rule border-l border-paper-rule text-center font-mono text-[11.5px] font-semibold ${pctClass(row.realized_excess_pct)}`}
      >
        {fmtSignedPct(row.realized_excess_pct)}
      </td>
      {/* Hit */}
      <td className="px-2 py-2 border-b border-paper-rule border-l border-paper-rule text-center font-mono text-[12px]">
        {row.is_hit == null ? (
          <span className="text-ink-4">—</span>
        ) : row.is_hit ? (
          <span className="text-signal-pos font-semibold">✓</span>
        ) : (
          <span className="text-signal-neg font-semibold">✗</span>
        )}
      </td>
    </>
  )
}

// Virtualization threshold — use plain tbody below this, virtual scroll above
const VIRTUAL_THRESHOLD = 200
const ROW_HEIGHT = 44

function VirtualBody({ rows }: { rows: CallRow[] }) {
  const parentRef = useRef<HTMLDivElement>(null)
  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 20,
  })

  return (
    <div
      ref={parentRef}
      className="overflow-y-auto"
      style={{ height: Math.min(rows.length * ROW_HEIGHT, 600) }}
    >
      <div style={{ height: rowVirtualizer.getTotalSize(), position: 'relative' }}>
        {rowVirtualizer.getVirtualItems().map((virtualRow) => {
          const row = rows[virtualRow.index]
          return (
            <table
              key={row.signal_call_id}
              className="w-full border-collapse text-[12px]"
              style={{
                position: 'absolute',
                top: virtualRow.start,
                left: 0,
                right: 0,
              }}
            >
              <tbody>
                <tr className="hover:[&>td]:bg-paper-soft cursor-pointer">
                  <RowCells row={row} />
                </tr>
              </tbody>
            </table>
          )
        })}
      </div>
    </div>
  )
}

export function CallsLedger({ calls }: CallsLedgerProps) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [dirFilter, setDirFilter] = useState<DirectionFilter>('all')
  const [search, setSearch] = useState('')
  const [sortCol, setSortCol] = useState<SortCol>('entry_date')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const inFlightCount = useMemo(() => calls.filter((c) => c.status === 'in_flight').length, [calls])
  const closedCount = useMemo(() => calls.filter((c) => c.status === 'closed').length, [calls])
  const buyCount = useMemo(() => calls.filter((c) => c.action_display === 'BUY').length, [calls])
  const avoidCount = useMemo(() => calls.filter((c) => c.action_display === 'AVOID').length, [calls])

  function handleSort(col: SortCol) {
    if (sortCol === col) {
      setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))
    } else {
      setSortCol(col)
      setSortDir('desc')
    }
  }

  const filtered = useMemo(() => {
    let rows = calls
    // I1: filter by status column value, not is_open boolean
    if (statusFilter === 'in_flight') rows = rows.filter((r) => r.status === 'in_flight')
    if (statusFilter === 'closed') rows = rows.filter((r) => r.status === 'closed')
    if (dirFilter === 'BUY') rows = rows.filter((r) => r.action_display === 'BUY')
    if (dirFilter === 'AVOID') rows = rows.filter((r) => r.action_display === 'AVOID')
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      rows = rows.filter(
        (r) =>
          r.symbol.toLowerCase().includes(q) ||
          (r.company_name ?? '').toLowerCase().includes(q) ||
          r.cell_label.toLowerCase().includes(q) ||
          r.signal_call_id.toLowerCase().includes(q),
      )
    }
    return rows
  }, [calls, statusFilter, dirFilter, search])

  const sorted = useMemo(() => {
    const copy = [...filtered]
    copy.sort((a, b) => {
      let av: number | string | null = null
      let bv: number | string | null = null
      if (sortCol === 'symbol') {
        av = a.symbol
        bv = b.symbol
      } else if (sortCol === 'cell_label') {
        av = a.cell_label
        bv = b.cell_label
      } else if (sortCol === 'cap_tier') {
        av = a.cap_tier
        bv = b.cap_tier
      } else if (sortCol === 'tenure') {
        av = a.tenure
        bv = b.tenure
      } else if (sortCol === 'entry_date') {
        av = a.entry_date
        bv = b.entry_date
      } else if (sortCol === 'days_in_position') {
        av = a.days_in_position
        bv = b.days_in_position
      } else if (sortCol === 'predicted_excess') {
        av = a.predicted_excess
        bv = b.predicted_excess
      } else if (sortCol === 'realized_excess_pct') {
        av = a.realized_excess_pct
        bv = b.realized_excess_pct
      }

      if (av === null && bv === null) return 0
      if (av === null) return 1
      if (bv === null) return -1
      const cmp = av < bv ? -1 : av > bv ? 1 : 0
      return sortDir === 'asc' ? cmp : -cmp
    })
    return copy
  }, [filtered, sortCol, sortDir])

  const thProps = { activeCol: sortCol, dir: sortDir, onClick: handleSort }
  const useVirtual = sorted.length > VIRTUAL_THRESHOLD

  return (
    <div>
      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3 px-4 py-3 mb-3 bg-paper border border-paper-rule rounded-[2px]">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-4">Status</span>
          {(
            [
              ['all', `All (${calls.length})`],
              ['in_flight', `In flight (${inFlightCount})`],
              ['closed', `Closed (${closedCount})`],
            ] as [StatusFilter, string][]
          ).map(([val, label]) => (
            <button
              key={val}
              onClick={() => setStatusFilter(val)}
              className={`px-[10px] py-1 text-[11px] border rounded-[2px] font-medium transition-colors ${statusFilter === val ? 'bg-accent text-paper border-accent' : 'bg-paper text-ink-4 border-paper-rule hover:border-ink-rule hover:text-ink-secondary'}`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="w-px h-5 bg-paper-rule mx-1" />

        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-4">Direction</span>
          {(
            [
              ['all', 'All'],
              ['BUY', `BUY (${buyCount})`],
              ['AVOID', `AVOID (${avoidCount})`],
            ] as [DirectionFilter, string][]
          ).map(([val, label]) => (
            <button
              key={val}
              onClick={() => setDirFilter(val)}
              className={`px-[10px] py-1 text-[11px] border rounded-[2px] font-medium transition-colors ${dirFilter === val ? 'bg-accent text-paper border-accent' : 'bg-paper text-ink-4 border-paper-rule hover:border-ink-rule hover:text-ink-secondary'}`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="w-px h-5 bg-paper-rule mx-1" />

        <input
          className="flex-1 min-w-[200px] max-w-[260px] px-[10px] py-1.5 text-[12px] border border-ink-rule rounded-[2px] bg-paper text-ink-primary placeholder:text-ink-4"
          placeholder="Search ticker, company, cell ID…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />

        <span className="ml-auto text-[11px] text-ink-4 font-mono">
          {sorted.length.toLocaleString('en-IN')} rows
        </span>
      </div>

      {/* Table */}
      <div className="bg-paper border border-paper-rule rounded-[2px] overflow-hidden">
        {/* Header */}
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr>
              <SortTh col="symbol" label="Symbol · Company" align="left" {...thProps} />
              <th className="px-2 py-[9px] text-[9px] font-semibold uppercase tracking-[0.13em] text-ink-4 bg-paper-soft border-b border-ink-rule text-center">
                Status
              </th>
              <SortTh col="cell_label" label="Cell" {...thProps} />
              <SortTh col="cap_tier" label="Tier" {...thProps} />
              <SortTh col="tenure" label="Ten." {...thProps} />
              <th className="px-2 py-[9px] text-[9px] font-semibold uppercase tracking-[0.13em] text-ink-4 bg-paper-soft border-b border-ink-rule text-center">
                Dir
              </th>
              <SortTh col="entry_date" label="Opened" groupSep {...thProps} />
              <SortTh col="days_in_position" label="Days" unit="held" {...thProps} />
              <SortTh
                col="predicted_excess"
                label="Pred ex."
                unit="% at call"
                groupSep
                {...thProps}
              />
              <SortTh
                col="realized_excess_pct"
                label="Real ex."
                unit="% realized"
                groupSep
                {...thProps}
              />
              <th className="px-2 py-[9px] text-[9px] font-semibold uppercase tracking-[0.13em] text-ink-4 bg-paper-soft border-b border-ink-rule text-center border-l border-paper-rule">
                Hit
              </th>
            </tr>
          </thead>

          {/* Plain tbody for <=200 rows (test-safe) */}
          {!useVirtual && sorted.length > 0 && (
            <tbody>
              {sorted.map((row) => (
                <tr
                  key={row.signal_call_id}
                  className="hover:[&>td]:bg-paper-soft cursor-pointer"
                >
                  <RowCells row={row} />
                </tr>
              ))}
            </tbody>
          )}
        </table>

        {/* Virtual scroll for >200 rows (I2: all 587 rendered cleanly) */}
        {useVirtual && <VirtualBody rows={sorted} />}

        {sorted.length === 0 && (
          <div className="py-12 text-center text-ink-4 text-sm">
            No calls match the current filter.
          </div>
        )}

        {sorted.length > 0 && (
          <div className="py-2 text-center text-[11px] text-ink-4 border-t border-paper-rule font-mono">
            {sorted.length.toLocaleString('en-IN')} rows
            {useVirtual ? ' · virtual scroll' : ''}
          </div>
        )}
      </div>
    </div>
  )
}
