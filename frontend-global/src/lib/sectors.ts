// src/lib/sectors.ts — the sector board's SHARED SHAPE: one row type for all three levels, and
// no I/O (the grid is a client component; the query module is `server-only`).
//
// ONE ROW TYPE FOR SECTOR, THEME AND FUND, DELIBERATELY. The FM: "we have a main sector, then
// subsector performance, and then, within that, the ETF… those kinds of consistent drill-down
// views can be built as we have it in atlas as well." Atlas India's SectorHeatmapV4 expands a
// sector IN PLACE into its constituents, rendered in the SAME columns, so the reader never loses
// their place and never has to re-learn a column. Three levels here, same idea: a column means
// the same thing at every depth, which is only guaranteed if there is literally one row type.
//
// WHAT A ROLL-UP IS. At the fund level every figure is that fund's own. At the theme and sector
// levels every figure is the MEDIAN of the members below it, never a mean and never AUM-weighted:
// a theme with one $30bn fund and nine $50m ones is not that one fund. `n_scored` is carried
// beside every median so a median of three is never read as a verdict.
//
// WHAT THE LEVELS ACTUALLY ARE, measured rather than assumed. `taxonomy_sector` seeds three
// levels — 11 GICS sectors, 33 sub-sectors, 32 themes — but every theme's `parent_id` is a level-1
// SECTOR, and nothing writes `sub_sector_id` on any fund. So the real chain is sector → theme →
// fund, and this file says so rather than rendering a middle level nobody populated.

/** The relative-strength windows every level is summarised over, shortest first. */
export const SECTOR_WINDOWS = ['3m', '6m', '12m'] as const
export type SectorWindow = (typeof SECTOR_WINDOWS)[number]

/** Which depth a row sits at. The grid renders all three identically and indents by depth. */
export type SectorLevel = 'sector' | 'theme' | 'fund'

export type SectorNode = {
  level: SectorLevel
  /** `taxonomy_sector.id` for a sector or theme; the ticker for a fund. Unique within the tree. */
  id: string
  name: string
  /** A fund's ticker — null above the leaf. */
  symbol: string | null
  /** Members BELOW this node: themes for a sector, funds for a theme, 0 for a fund. */
  n_children: number
  /** Distinct funds under this node (1 at the leaf) — the denominator behind `n_scored`. */
  n_funds: number
  /** How many of those carry a composite. Every median below is over exactly these. */
  n_scored: number
  aum_usd: string | null
  /** 0–100. The member median above the leaf; the fund's own composite at it. */
  composite: string | null
  /** Share of MEASURED members above their own 200-day EMA, 0–1. Null where nothing is old
   *  enough to have a 200-day line — which is not the same as nothing being above it. */
  above_ema200_frac: string | null
  /** Median member relative strength vs SPY, ADR-0002 relative form, as a fraction. */
  rs: Record<SectorWindow, string | null>
  /** 1 = strongest, among the SIBLINGS at this node's own level. A sector is ranked against the
   *  other ten sectors, a theme against the other themes IN ITS SECTOR, a fund against the other
   *  funds carrying ITS theme — so a rank never silently changes population when a row expands. */
  rank: number | null
  /** How many siblings carry a composite — the denominator of `rank`. */
  n_ranked: number
  /** The strongest scored fund anywhere under this node, for the "what would I buy" column. */
  top_symbol: string | null
  top_name: string | null
  /** Children, already ranked. Empty at the leaf. */
  children: SectorNode[]
}

export type SectorTree = {
  /** The session every figure is anchored on, or null when nothing is scored. */
  date: string | null
  rows: SectorNode[]
  /** Classified, in-universe funds whose name states no theme. They belong to no sector here,
   *  and the board says how many rather than quietly ranking a partial universe. */
  n_unthemed: number
}

// ── the pure half: ordering, and what a column is worth ─────────────────────

/** What the board can be sorted by. Every key reads the SAME field at all three levels, which is
 *  the whole point of one row type. */
export type SortKey = 'name' | 'composite' | 'breadth' | 'aum' | SectorWindow

export function valueOf(n: SectorNode, k: SortKey): number | string | null {
  if (k === 'name') return n.name
  if (k === 'composite') return n.composite == null ? null : Number(n.composite)
  if (k === 'breadth') return n.above_ema200_frac == null ? null : Number(n.above_ema200_frac)
  if (k === 'aum') return n.aum_usd == null ? null : Number(n.aum_usd)
  const v = n.rs[k]
  return v == null ? null : Number(v)
}

/** Sort every level by the same key, so a choice made at the top holds all the way down — a
 *  drill-down whose children re-order by a different rule is two tables wearing one header.
 *
 *  A ROW WITH NO VALUE SORTS LAST IN BOTH DIRECTIONS. Ascending by score, a theme nobody has
 *  scored must not lead the board: "unmeasured" is not "lowest" (rule #0). This is the same
 *  stance the fund tables take when they put unranked funds below the ranked block.
 *
 *  Pure and total: it returns a new tree and never mutates the one it was given, because the
 *  cached query result is shared by every request the `eod` tag serves. */
export function sortTree(rows: readonly SectorNode[], key: SortKey, dir: 1 | -1): SectorNode[] {
  const cmp = (a: SectorNode, b: SectorNode) => {
    const x = valueOf(a, key)
    const y = valueOf(b, key)
    if (x == null && y == null) return a.name.localeCompare(b.name)
    if (x == null) return 1
    if (y == null) return -1
    if (typeof x === 'string' || typeof y === 'string') {
      return String(x).localeCompare(String(y)) * dir
    }
    return (x - y) * dir
  }
  return rows
    .map((r) => ({ ...r, children: sortTree(r.children, key, dir) }))
    .sort(cmp)
}

/** The score range of a set of siblings — the population a heat tint is cut against. Null when
 *  nothing in the set is scored, so the caller renders no colour rather than a flat one. */
export function scoreSpan(rows: readonly SectorNode[]): { best: number; worst: number } | null {
  const v = rows.map((r) => r.composite).filter((c): c is string => c != null).map(Number)
  if (v.length === 0) return null
  return { best: Math.max(...v), worst: Math.min(...v) }
}
