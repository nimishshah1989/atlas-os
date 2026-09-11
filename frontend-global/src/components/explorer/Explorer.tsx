'use client'
// src/components/explorer/Explorer.tsx — peer strip + filter bar + count line + the DataTable over a
// list the page loaded once. All state (query, facets, sort) is the URL, read with useSearchParams and
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
import { FacetBar } from './FacetBar'
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
  /** Named column sets the reader chooses between — the same rows, a different question. The
   *  chosen one rides in the URL as `cols`, so a view is an address like every other bit of state
   *  here. Absent, `columns` is the only set and no switch is drawn. */
  columnSets?: { key: string; label: string; note: string; columns: Column<R>[] }[]
  /** A second way of reading the SAME filtered rows, offered beside the table. The picture is the
   *  faster read for "what is worth looking at"; the table is the read for "what exactly". Both
   *  are the same set, so a filter narrows both and neither can show something the other hides. */
  chart?: (shown: readonly R[]) => ReactNode
}

export function Explorer<R extends { symbol: string; name: string | null }>({ rows, columns, groups, defaultSort, rowKey, noun, empty, stripKey, columnSets, chart }: Props<R>) {
  const params = useSearchParams()
  const pathname = usePathname()
  const state = useMemo(() => parseState(params, groups, defaultSort), [params, groups, defaultSort])
  const values = useMemo(() => Object.fromEntries(groups.map((g) => [g.key, facetValues(rows, g)])), [rows, groups])
  const counts = useMemo(() => facetCounts(rows, state, groups), [rows, state, groups])
  // Which columns are on screen. An unknown `cols` value falls back to the first set rather than
  // rendering nothing — a stale bookmark should show the board, not a blank one.
  const colsParam = params.get('cols')
  const set = columnSets?.find((c) => c.key === colsParam) ?? columnSets?.[0]
  const shownColumns = set?.columns ?? columns
  const byKey = useMemo(() => new Map(shownColumns.map((c) => [c.key, c])), [shownColumns])
  const shown = useMemo(
    () => sortRows(applyFilters(rows, state, groups), state.sort, (r, key) => byKey.get(key)?.sortValue(r) ?? null),
    [rows, state, groups, byKey],
  )

  // `view` rides alongside the facet state rather than inside it: it changes nothing about WHICH
  // rows are shown, only how they are drawn, so it must not take part in "have you filtered?".
  const view = chart && params.get('view') === 'chart' ? 'chart' : 'table'

  function write(next: ExplorerState, nextView: 'table' | 'chart' = view, nextCols = set?.key) {
    const qs = serialiseState(next, groups, defaultSort)
    const p = new URLSearchParams(qs)
    if (nextView === 'chart') p.set('view', 'chart')
    // The first set is the default, so it stays out of the address: a URL should carry the
    // choices someone made, not the ones they did not.
    if (nextCols && columnSets && nextCols !== columnSets[0].key) p.set('cols', nextCols)
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
        {/* The filters sit BETWEEN the groups and the rows: choose a job, narrow it, read the ranking. */}
        <FacetBar
          groups={groups}
          values={values}
          counts={counts}
          selected={state.facets}
          onChange={(key, sel) => write({ ...state, facets: { ...state.facets, [key]: sel } })}
          onClear={filtered ? () => write({ ...state, facets: defaults }) : undefined}
          omit={stripKey}
        />
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-body text-ink-2" role="status" data-testid="count" data-total={total} data-shown={shown.length}>
            {line}
          </p>
          <div className="flex flex-wrap items-center gap-2">
          {view === 'table' && columnSets && columnSets.length > 1 && (
            <div className="seg" role="group" aria-label="Which columns to show">
              {columnSets.map((c) => (
                <button
                  key={c.key}
                  type="button"
                  className={`text-meta${set?.key === c.key ? ' on' : ''}`}
                  aria-pressed={set?.key === c.key}
                  title={c.note}
                  onClick={() => write(state, view, c.key)}
                >
                  {c.label}
                </button>
              ))}
            </div>
          )}
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
        </div>
        {view === 'chart' && chart ? (
          chart(shown)
        ) : (
          <DataTable rows={shown} columns={shownColumns} rowKey={rowKey} sort={state.sort} onSort={(sort) => write({ ...state, sort })} empty={empty} />
        )}
      </div>
    </div>
  )
}
