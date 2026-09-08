// src/lib/explorer.ts — the explorer's pure pieces: URL state, facets with counts, sort, search.
// The page loads every row once; everything here runs in the browser over that list. Facets are
// URL state (a screen is shareable): `?exchange=NYSE&exchange=NASDAQ&sp500=all&sort=-listed&q=app`.

export type SortDir = 'asc' | 'desc'
export type SortState = { key: string; dir: SortDir }

/** `any`: checkboxes, OR within the group. `one`: a radio with an implicit "all" option. */
export type FacetGroup<R> = {
  key: string
  label: string
  kind: 'any' | 'one'
  value: (r: R) => string
  /** Display names for values that are tokens rather than words (e.g. `none`, `member`). */
  labels?: Record<string, string>
  /** `one` groups only: the radio's values (fixed by design, not scanned from rows) … */
  options?: string[]
  /** … and the one selected when the URL says nothing. */
  default?: string
}

export type ExplorerState = { q: string; facets: Record<string, string[]>; sort: SortState }

export const ALL = 'all'

const defaultSelection = <R>(g: FacetGroup<R>): string[] => (g.kind === 'one' ? [g.default ?? ALL] : [])

export function parseState<R>(params: URLSearchParams, groups: FacetGroup<R>[], defaultSort: SortState): ExplorerState {
  const facets: Record<string, string[]> = {}
  for (const g of groups) {
    const given = params.getAll(g.key).filter(Boolean)
    if (!params.has(g.key)) facets[g.key] = defaultSelection(g)
    else if (g.kind === 'one') facets[g.key] = given[0] === ALL || g.options?.includes(given[0]) ? [given[0]] : defaultSelection(g)
    else facets[g.key] = given
  }
  const sortParam = params.get('sort')
  const sort: SortState = sortParam
    ? sortParam.startsWith('-')
      ? { key: sortParam.slice(1), dir: 'desc' }
      : { key: sortParam, dir: 'asc' }
    : defaultSort
  return { q: params.get('q') ?? '', facets, sort }
}

/** The query string (without "?") for everything that differs from the defaults; "" when nothing does. */
export function serialiseState<R>(state: ExplorerState, groups: FacetGroup<R>[], defaultSort: SortState): string {
  const p = new URLSearchParams()
  for (const g of groups) {
    const sel = state.facets[g.key] ?? []
    const def = defaultSelection(g)
    if (sel.length === def.length && sel.every((v, i) => v === def[i])) continue
    sel.forEach((v) => p.append(g.key, v))
  }
  if (state.sort.key !== defaultSort.key || state.sort.dir !== defaultSort.dir) {
    p.set('sort', `${state.sort.dir === 'desc' ? '-' : ''}${state.sort.key}`)
  }
  if (state.q) p.set('q', state.q)
  return p.toString()
}

// ── search ──────────────────────────────────────────────────────────────────

// Symbols compare with dashes read as dots, so Stooq's BRK-B finds instrument_master's BRK.B.
const normSymbol = (s: string) => s.toLowerCase().replace(/-/g, '.')

export function matchesQuery(r: { symbol: string; name: string | null }, q: string): boolean {
  const needle = q.trim().toLowerCase()
  if (!needle) return true
  return normSymbol(r.symbol).startsWith(normSymbol(needle)) || (r.name?.toLowerCase().includes(needle) ?? false)
}

// ── facets ──────────────────────────────────────────────────────────────────

function passes<R>(r: R, g: FacetGroup<R>, sel: string[]): boolean {
  if (sel.length === 0) return true
  if (g.kind === 'one') return sel[0] === ALL || g.value(r) === sel[0]
  return sel.includes(g.value(r))
}

type Named = { symbol: string; name: string | null }

/** Rows matching the query and every group. */
export function applyFilters<R extends Named>(rows: readonly R[], state: ExplorerState, groups: FacetGroup<R>[]): R[] {
  return rows.filter((r) => matchesQuery(r, state.q) && groups.every((g) => passes(r, g, state.facets[g.key] ?? [])))
}

/** Per group, how many rows each value would show: counted under the query and the OTHER groups'
 *  selections, so choosing a value never hides its alternatives. `one` groups also count `all`. */
export function facetCounts<R extends Named>(rows: readonly R[], state: ExplorerState, groups: FacetGroup<R>[]): Record<string, Record<string, number>> {
  const out: Record<string, Record<string, number>> = {}
  for (const g of groups) {
    const counts: Record<string, number> = {}
    let total = 0
    for (const r of rows) {
      if (!matchesQuery(r, state.q)) continue
      if (!groups.every((o) => o === g || passes(r, o, state.facets[o.key] ?? []))) continue
      const v = g.value(r)
      counts[v] = (counts[v] ?? 0) + 1
      total += 1
    }
    if (g.kind === 'one') counts[ALL] = total
    out[g.key] = counts
  }
  return out
}

/** Every value a group takes over the full list, most frequent first (the `none` token last) —
 *  the rail's option list, fixed so options do not reorder as the counts move. */
export function facetValues<R>(rows: readonly R[], g: FacetGroup<R>): string[] {
  const counts: Record<string, number> = {}
  for (const r of rows) {
    const v = g.value(r)
    counts[v] = (counts[v] ?? 0) + 1
  }
  const last = (v: string) => (v === 'none' ? 1 : 0)
  return Object.keys(counts).sort((a, b) => last(a) - last(b) || counts[b] - counts[a] || a.localeCompare(b))
}

// ── sort ────────────────────────────────────────────────────────────────────

const collator = new Intl.Collator('en', { sensitivity: 'base', numeric: true })

/** A sorted copy. Nulls go last whichever the direction; ties keep the incoming order. */
export function sortRows<R>(rows: readonly R[], sort: SortState, sortValue: (r: R, key: string) => string | number | null): R[] {
  const keyed = rows.map((r, i) => ({ r, i, v: sortValue(r, sort.key) }))
  const sign = sort.dir === 'desc' ? -1 : 1
  keyed.sort((a, b) => {
    if (a.v == null || b.v == null) return a.v == null ? (b.v == null ? a.i - b.i : 1) : -1
    const c = typeof a.v === 'number' && typeof b.v === 'number' ? a.v - b.v : collator.compare(String(a.v), String(b.v))
    return c === 0 ? a.i - b.i : c * sign
  })
  return keyed.map((k) => k.r)
}
