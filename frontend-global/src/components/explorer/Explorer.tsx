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
import { PeerStrip } from './PeerStrip'

type Props<R> = {
  rows: readonly R[]
  columns: Column<R>[]
  groups: FacetGroup<R>[]
  defaultSort: SortState
  rowKey: (r: R) => string
  /** The plural noun in the count line: "5,656 ETFs". */
  noun: string
  empty: ReactNode
  /** The facet whose values also render as a chip strip above the table — the grouping a reader
   *  chooses BEFORE reading a ranking. Omitted, there is no strip. */
  stripKey?: string
  /** A second way of reading the SAME filtered rows, offered beside the table. The picture is the
   *  faster read for "what is worth looking at"; the table is the read for "what exactly". Both
   *  are the same set, so a filter narrows both and neither can show something the other hides. */
  chart?: (shown: readonly R[]) => ReactNode
}

export function Explorer<R extends { symbol: string; name: string | null }>({ rows, columns, groups, defaultSort, rowKey, noun, empty, stripKey, chart }: Props<R>) {
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

  // `view` rides alongside the facet state rather than inside it: it changes nothing about WHICH
  // rows are shown, only how they are drawn, so it must not take part in "have you filtered?".
  const view = chart && params.get('view') === 'chart' ? 'chart' : 'table'

  function write(next: ExplorerState, nextView: 'table' | 'chart' = view) {
    const qs = serialiseState(next, groups, defaultSort)
    const p = new URLSearchParams(qs)
    if (nextView === 'chart') p.set('view', 'chart')
    const out = p.toString()
    window.history.replaceState(null, '', out ? `${pathname}?${out}` : pathname)
  }

  const defaults = parseState(new URLSearchParams(), groups, defaultSort).facets
  const filtered = groups.some((g) => String(state.facets[g.key]) !== String(defaults[g.key]))
  const total = rows.length
  const line =
    shown.length === total
      ? `${formatNum(total)} ${noun}`
      : `${formatNum(shown.length)} of ${formatNum(total)} ${noun}${state.q ? ` match “${state.q}”` : ''}`

  const strip = groups.find((g) => g.key === stripKey)

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
        {strip && (
          <PeerStrip
            values={values[strip.key] ?? []}
            counts={counts[strip.key] ?? {}}
            selected={state.facets[strip.key] ?? []}
            label={(v) => strip.labels?.[v] ?? strip.format?.(v) ?? v}
            onToggle={(v) => {
              const sel = state.facets[strip.key] ?? []
              write({ ...state, facets: { ...state.facets, [strip.key]: sel.includes(v) ? [] : [v] } })
            }}
          />
        )}
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-body text-ink-2" role="status" data-testid="count" data-total={total} data-shown={shown.length}>
            {line}
          </p>
          {chart && (
            <div className="seg" role="group" aria-label="How to read these rows">
              {(['table', 'chart'] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  className={`text-meta${view === v ? ' on' : ''}`}
                  aria-pressed={view === v}
                  onClick={() => write(state, v)}
                >
                  {v === 'table' ? 'Table' : 'Map'}
                </button>
              ))}
            </div>
          )}
        </div>
        {view === 'chart' && chart ? (
          chart(shown)
        ) : (
          <DataTable rows={shown} columns={columns} rowKey={rowKey} sort={state.sort} onSort={(sort) => write({ ...state, sort })} empty={empty} />
        )}
      </div>
    </div>
  )
}
