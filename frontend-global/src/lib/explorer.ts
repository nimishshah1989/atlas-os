// src/lib/explorer.ts — the explorer's pure pieces: URL state, facets with counts, sort, search.
// The page loads every row once; everything here runs in the browser over that list. Facets are
// URL state (a screen is shareable): `?exchange=NYSE&exchange=NASDAQ&sp500=all&sort=-listed&q=app`.

export type SortDir = 'asc' | 'desc'
export type SortState = { key: string; dir: SortDir }

/** `any`: checkboxes, OR within the group. `one`: a radio with an implicit "all" option.
 *  `flag`: ONE checkbox, off by default — off shows only the rows whose value is not `on`, and
 *  ticking it lets them back in. That is the shape of "geared funds are not on this board unless
 *  you ask for them": the default hides nothing that the reader has not been told about, and the
 *  count beside the box says how many rows the tick would add. */
export type FacetGroup<R> = {
  key: string
  label: string
  kind: 'any' | 'one' | 'flag' | 'min' | 'max'
  value: (r: R) => string
  /** Display names for values that are tokens rather than words (e.g. `none`, `member`). A `flag`
   *  group names its single `on` option; a `one` group may rename the implicit `all`. */
  labels?: Record<string, string>
  /** Display names for values not known ahead of time (a peer group, a country). */
  format?: (value: string) => string
  /** `min` / `max` groups: the value the threshold compares, in the row's own unit. Null never
   *  passes — see `Threshold`. */
  numeric?: (r: R) => number | null
  /** `one`, `min` and `max` groups: the radio's values (fixed by design, not scanned from rows) … */
  options?: string[]
  /** … and the one selected when the URL says nothing. */
  default?: string
}

/** A `flag` group's only value: the rows the default view leaves out. */
export const ON = 'on'

/** `min` / `max`: a THRESHOLD rail rather than a set of buckets. Its options are numbers in the
 *  row's own unit, ascending, and picking one keeps the rows at or beyond it — "traded value at
 *  least $10M a day", "volatility at most 25 percent a year". Buckets would answer a different
 *  question ("which funds are between 10 and 25?"), which is not how anyone screens: an FM sets a
 *  floor on liquidity and a ceiling on risk and reads what survives.
 *
 *  A row whose number is MISSING never passes a threshold. An unmeasured fund is not a calm one
 *  (rule #0), and letting nulls through a "volatility at most 15 percent" filter would put the
 *  funds nobody has measured at the top of the safest screen. */
export type Threshold = { kind: 'min' | 'max'; numeric: (r: unknown) => number | null }

export type ExplorerState = { q: string; facets: Record<string, string[]>; sort: SortState }

export const ALL = 'all'

/** `one`, `min` and `max` are all single-choice rails with an implicit "all". */
const single = (kind: FacetGroup<unknown>['kind']) => kind === 'one' || kind === 'min' || kind === 'max'

const defaultSelection = <R>(g: FacetGroup<R>): string[] => (single(g.kind) ? [g.default ?? ALL] : [])

export function parseState<R>(params: URLSearchParams, groups: FacetGroup<R>[], defaultSort: SortState): ExplorerState {
  const facets: Record<string, string[]> = {}
  for (const g of groups) {
    const given = params.getAll(g.key).filter(Boolean)
    if (!params.has(g.key)) facets[g.key] = defaultSelection(g)
    else if (single(g.kind)) facets[g.key] = given[0] === ALL || g.options?.includes(given[0]) ? [given[0]] : defaultSelection(g)
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
  // Checked before the empty-selection shortcut: an unticked flag FILTERS, it does not pass all.
  if (g.kind === 'flag') return sel.includes(ON) || g.value(r) !== ON
  if (sel.length === 0) return true
  if (g.kind === 'min' || g.kind === 'max') {
    if (sel[0] === ALL) return true
    const limit = Number(sel[0])
    const v = g.numeric?.(r)
    if (v == null || !Number.isFinite(v) || !Number.isFinite(limit)) return false
    return g.kind === 'min' ? v >= limit : v <= limit
  }
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
    const threshold = g.kind === 'min' || g.kind === 'max'
    for (const r of rows) {
      if (!matchesQuery(r, state.q)) continue
      if (!groups.every((o) => o === g || passes(r, o, state.facets[o.key] ?? []))) continue
      total += 1
      if (threshold) {
        // CUMULATIVE: a threshold's count is how many rows it would KEEP, which is the number the
        // reader is choosing between. Counting rows per exact value would print the size of a
        // bucket nobody selected.
        for (const opt of g.options ?? []) if (passes(r, g, [opt])) counts[opt] = (counts[opt] ?? 0) + 1
      } else {
        const v = g.value(r)
        counts[v] = (counts[v] ?? 0) + 1
      }
    }
    if (single(g.kind)) counts[ALL] = total
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
