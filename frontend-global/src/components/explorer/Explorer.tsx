'use client'
// src/components/explorer/Explorer.tsx — facet rail + count line + the DataTable over a list the
// page loaded once. All state (query, facets, sort) is the URL, read with useSearchParams and
// written with history.replaceState (which Next syncs back into the router, without a request),
// so a screen is a shareable address. The top bar's search box writes the same `q`.
import { usePathname, useSearchParams } from 'next/navigation'
import { useMemo, type ReactNode } from 'react'
import {
  applyFilters,
  facetCounts,
  facetValues,
  parseState,
  serialiseState,
  sortRows,
  type ExplorerState,
  type FacetGroup,
  type SortState,
} from '@/lib/explorer'
import { formatNum } from '@/lib/format'
import { DataTable, type Column } from './DataTable'
import { FacetRail } from './FacetRail'

type Props<R> = {
  rows: readonly R[]
  columns: Column<R>[]
  groups: FacetGroup<R>[]
  defaultSort: SortState
  rowKey: (r: R) => string
  /** The plural noun in the count line: "5,656 ETFs". */
  noun: string
  empty: ReactNode
}

export function Explorer<R extends { symbol: string; name: string | null }>({ rows, columns, groups, defaultSort, rowKey, noun, empty }: Props<R>) {
  const params = useSearchParams()
  const pathname = usePathname()
  const state = useMemo(() => parseState(params, groups, defaultSort), [params, groups, defaultSort])
  const values = useMemo(() => Object.fromEntries(groups.map((g) => [g.key, facetValues(rows, g)])), [rows, groups])
  const counts = useMemo(() => facetCounts(rows, state, groups), [rows, state, groups])
  const byKey = useMemo(() => new Map(columns.map((c) => [c.key, c])), [columns])
  const shown = useMemo(
    () => sortRows(applyFilters(rows, state, groups), state.sort, (r, key) => byKey.get(key)?.sortValue(r) ?? null),
    [rows, state, groups, byKey],
  )

  function write(next: ExplorerState) {
    const qs = serialiseState(next, groups, defaultSort)
    window.history.replaceState(null, '', qs ? `${pathname}?${qs}` : pathname)
  }

  const defaults = parseState(new URLSearchParams(), groups, defaultSort).facets
  const filtered = groups.some((g) => String(state.facets[g.key]) !== String(defaults[g.key]))
  const total = rows.length
  const line =
    shown.length === total
      ? `${formatNum(total)} ${noun}`
      : `${formatNum(shown.length)} of ${formatNum(total)} ${noun}${state.q ? ` match “${state.q}”` : ''}`

  return (
    <div className="explorer">
      <FacetRail
        groups={groups}
        values={values}
        counts={counts}
        selected={state.facets}
        onChange={(key, sel) => write({ ...state, facets: { ...state.facets, [key]: sel } })}
        onClear={filtered ? () => write({ ...state, facets: defaults }) : undefined}
      />
      <div className="min-w-0">
        <p className="mb-2 text-body text-ink-2" role="status" data-testid="count" data-total={total} data-shown={shown.length}>
          {line}
        </p>
        <DataTable rows={shown} columns={columns} rowKey={rowKey} sort={state.sort} onSort={(sort) => write({ ...state, sort })} empty={empty} />
      </div>
    </div>
  )
}
