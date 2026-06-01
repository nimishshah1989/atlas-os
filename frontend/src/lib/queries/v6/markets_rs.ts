// frontend/src/lib/queries/v6/markets_rs.ts
//
// Data layer for /markets-rs (Page 03 — Markets Relative Strength).
// Source: atlas.mv_markets_rs_grid — 9 rows, pre-computed nightly.
//
// Exports:
//   getMarketsRsPage()   — full page data (grid + hero readouts)
//   deriveHeroReadouts() — pure fn for testing
//   deriveIndiaRsGrade() — pure fn for testing

import 'server-only'
import sql from '@/lib/db'
import { toNumber } from '@/lib/v6/decimal'

// ---------------------------------------------------------------------------
// Raw DB row
// ---------------------------------------------------------------------------

type MvRow = {
  rank_order: number
  baseline_name: string
  latest_close_inr: string | null
  ret_1w: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  rank_1w: number | null
  rank_1m: number | null
  rank_3m: number | null
  rank_6m: number | null
  rank_12m: number | null
  as_of_date: string | null
  refreshed_at: string | null
}

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type MarketsRsRow = {
  rank_order: number
  baseline_name: string
  latest_close_inr: number | null
  ret_1w: number | null
  ret_1m: number | null
  ret_3m: number | null
  ret_6m: number | null
  ret_12m: number | null
  rank_1w: number | null
  rank_1m: number | null
  rank_3m: number | null
  rank_6m: number | null
  rank_12m: number | null
  as_of_date: string | null
}

export type IndiaRsGrade = 'A' | 'B' | 'C' | 'D'

export type HeroReadouts = {
  /** Baseline with rank_1w === 1 */
  today_leader: string | null
  /** Nifty 500's rank_1m out of 9 */
  india_rank_1m: number | null
  /** (Nifty 100 ret_3m - avg(Midcap150, Smallcap250) ret_3m) × 100 in pp */
  large_vs_midsmall_spread_3m_pp: number | null
  /** A/B/C/D from Nifty 500 avg(rank_1m, rank_3m, rank_6m) */
  india_rs_grade: IndiaRsGrade | null
}

export type MarketsRsPageData = {
  grid: MarketsRsRow[]
  hero: HeroReadouts
  as_of_date: string | null
}

// ---------------------------------------------------------------------------
// Per-baseline staleness (data-honesty)
// ---------------------------------------------------------------------------

/**
 * A baseline lagging the freshest by more than this many calendar days is
 * flagged stale in the grid. The normal US/global 1-day timezone lag
 * (NSE closes a day ahead of S&P 500 / MSCI World) stays unflagged; the
 * weeks-stale MSCI EM proxy gets a visible marker so it is never read as
 * current.
 */
export const MARKETS_RS_STALE_THRESHOLD_DAYS = 7

/**
 * Calendar-day lag of a baseline's as_of_date behind the freshest baseline.
 * Returns null when either date is missing or unparseable (explicit NULL
 * handling — never silently treat a missing date as fresh).
 */
export function baselineStalenessDays(
  rowAsOf: string | null,
  freshestAsOf: string | null,
): number | null {
  if (!rowAsOf || !freshestAsOf) return null
  const a = Date.parse(rowAsOf)
  const b = Date.parse(freshestAsOf)
  if (Number.isNaN(a) || Number.isNaN(b)) return null
  return Math.round((b - a) / 86_400_000)
}

// ---------------------------------------------------------------------------
// Grade derivation (exported for unit tests)
// ---------------------------------------------------------------------------

/**
 * Derive India RS Grade from Nifty 500's ranks on 3 windows.
 * A = top-3 rank avg ≤ 2.5 (Nifty 500 consistently in top 3)
 * B = ≤ 4.5
 * C = ≤ 6.5
 * D = > 6.5
 * Returns null if any input is null (explicit NULL handling).
 */
export function deriveIndiaRsGrade(
  rank_1m: number | null,
  rank_3m: number | null,
  rank_6m: number | null,
): IndiaRsGrade | null {
  if (rank_1m == null || rank_3m == null || rank_6m == null) return null
  const avg = (rank_1m + rank_3m + rank_6m) / 3
  if (avg <= 2.5) return 'A'
  if (avg <= 4.5) return 'B'
  if (avg <= 6.5) return 'C'
  return 'D'
}

// ---------------------------------------------------------------------------
// Hero readout derivation (exported for unit tests)
// ---------------------------------------------------------------------------

export function deriveHeroReadouts(grid: MarketsRsRow[]): HeroReadouts {
  if (grid.length === 0) {
    return {
      today_leader: null,
      india_rank_1m: null,
      large_vs_midsmall_spread_3m_pp: null,
      india_rs_grade: null,
    }
  }

  // Today's leader: rank_1w === 1
  const leader = grid.find(r => r.rank_1w === 1) ?? null
  const today_leader = leader?.baseline_name ?? null

  // India vs world: Nifty 500 rank on 1m
  const nifty500 = grid.find(r => r.baseline_name === 'Nifty 500') ?? null
  const india_rank_1m = nifty500?.rank_1m ?? null

  // Within India: large-cap (Nifty 100) vs avg(Midcap150, Smallcap250) on 3m
  const nifty100 = grid.find(r => r.baseline_name === 'Nifty 100') ?? null
  const midcap = grid.find(r => r.baseline_name === 'Nifty Midcap 150') ?? null
  const smallcap = grid.find(r => r.baseline_name === 'Nifty Smallcap 250') ?? null

  let large_vs_midsmall_spread_3m_pp: number | null = null
  if (
    nifty100?.ret_3m != null &&
    midcap?.ret_3m != null &&
    smallcap?.ret_3m != null
  ) {
    const midSmallAvg = (midcap.ret_3m + smallcap.ret_3m) / 2
    large_vs_midsmall_spread_3m_pp = (nifty100.ret_3m - midSmallAvg) * 100
  }

  // India RS Grade: from Nifty 500
  const india_rs_grade = deriveIndiaRsGrade(
    nifty500?.rank_1m ?? null,
    nifty500?.rank_3m ?? null,
    nifty500?.rank_6m ?? null,
  )

  return {
    today_leader,
    india_rank_1m,
    large_vs_midsmall_spread_3m_pp,
    india_rs_grade,
  }
}

// ---------------------------------------------------------------------------
// Main query function
// ---------------------------------------------------------------------------

export async function getMarketsRsPage(): Promise<MarketsRsPageData> {
  const rows = await sql<MvRow[]>`
    SELECT
      rank_order,
      baseline_name,
      latest_close_inr::text    AS latest_close_inr,
      ret_1w::text              AS ret_1w,
      ret_1m::text              AS ret_1m,
      ret_3m::text              AS ret_3m,
      ret_6m::text              AS ret_6m,
      ret_12m::text             AS ret_12m,
      rank_1w,
      rank_1m,
      rank_3m,
      rank_6m,
      rank_12m,
      as_of_date::text          AS as_of_date,
      refreshed_at::text        AS refreshed_at
    FROM atlas.mv_markets_rs_grid
    ORDER BY rank_order
  `

  const grid: MarketsRsRow[] = rows.map(r => ({
    rank_order:       r.rank_order,
    baseline_name:    r.baseline_name,
    latest_close_inr: toNumber(r.latest_close_inr),
    ret_1w:           toNumber(r.ret_1w),
    ret_1m:           toNumber(r.ret_1m),
    ret_3m:           toNumber(r.ret_3m),
    ret_6m:           toNumber(r.ret_6m),
    ret_12m:          toNumber(r.ret_12m),
    rank_1w:          r.rank_1w,
    rank_1m:          r.rank_1m,
    rank_3m:          r.rank_3m,
    rank_6m:          r.rank_6m,
    rank_12m:         r.rank_12m,
    as_of_date:       r.as_of_date ?? null,
  }))

  const hero = deriveHeroReadouts(grid)
  // Freshest (max) baseline date — ISO YYYY-MM-DD sorts lexicographically.
  // Never the first row: a lagging baseline (e.g. MSCI EM proxy) must not
  // determine the page's "as of" stamp.
  const as_of_date = grid.reduce<string | null>(
    (max, r) =>
      r.as_of_date != null && (max == null || r.as_of_date > max)
        ? r.as_of_date
        : max,
    null,
  )

  return { grid, hero, as_of_date }
}
