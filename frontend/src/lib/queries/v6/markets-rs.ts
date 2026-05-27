// frontend/src/lib/queries/v6/markets-rs.ts
//
// Reads atlas.mv_markets_rs_grid (9 baselines × 5 time windows of return + rank).
// Derives 4 hero readouts (today's leader, India vs world, within India, India RS grade).
//
// MV refreshed nightly via pg_cron (Phase D) — REFRESH CONCURRENTLY supported.

import 'server-only'
import sql from '@/lib/db'

export type RsBaselineRow = {
  rank_order: number
  baseline_name: string
  latest_close_inr: number | null
  as_of_date: string | null
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
}

export type MarketsRsHero = {
  today_leader: string | null
  india_rank_1m: number | null
  large_vs_midsmall_spread_3m: number | null
  india_rs_grade: 'A' | 'B' | 'C' | 'D' | null
}

export type MarketsRsPage = {
  as_of_date: string | null
  baselines: RsBaselineRow[]
  hero: MarketsRsHero
}

type Row = {
  rank_order: number
  baseline_name: string
  latest_close_inr: string | null
  as_of_date: string | null
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
}

function toNumber(s: string | null): number | null {
  if (s == null) return null
  const n = Number(s)
  return Number.isFinite(n) ? n : null
}

export async function getMarketsRsPage(): Promise<MarketsRsPage> {
  const rows = await sql<Row[]>`
    SELECT
      rank_order, baseline_name,
      latest_close_inr::text AS latest_close_inr,
      as_of_date::text       AS as_of_date,
      ret_1w::text  AS ret_1w,
      ret_1m::text  AS ret_1m,
      ret_3m::text  AS ret_3m,
      ret_6m::text  AS ret_6m,
      ret_12m::text AS ret_12m,
      rank_1w, rank_1m, rank_3m, rank_6m, rank_12m
    FROM atlas.mv_markets_rs_grid
    ORDER BY rank_order
  `

  const baselines: RsBaselineRow[] = rows.map(r => ({
    rank_order: r.rank_order,
    baseline_name: r.baseline_name,
    latest_close_inr: toNumber(r.latest_close_inr),
    as_of_date: r.as_of_date,
    ret_1w:  toNumber(r.ret_1w),
    ret_1m:  toNumber(r.ret_1m),
    ret_3m:  toNumber(r.ret_3m),
    ret_6m:  toNumber(r.ret_6m),
    ret_12m: toNumber(r.ret_12m),
    rank_1w: r.rank_1w,
    rank_1m: r.rank_1m,
    rank_3m: r.rank_3m,
    rank_6m: r.rank_6m,
    rank_12m: r.rank_12m,
  }))

  const leader1w = baselines.find(b => b.rank_1w === 1)?.baseline_name ?? null
  const nifty500 = baselines.find(b => b.baseline_name === 'Nifty 500')
  const nifty100 = baselines.find(b => b.baseline_name === 'Nifty 100')
  const midcap   = baselines.find(b => b.baseline_name === 'Nifty Midcap 150')
  const smallcap = baselines.find(b => b.baseline_name === 'Nifty Smallcap 250')

  let spread_3m: number | null = null
  if (nifty100?.ret_3m != null && midcap?.ret_3m != null && smallcap?.ret_3m != null) {
    spread_3m = (nifty100.ret_3m - (midcap.ret_3m + smallcap.ret_3m) / 2) * 100
  }

  let grade: 'A' | 'B' | 'C' | 'D' | null = null
  if (nifty500?.rank_1m != null && nifty500?.rank_3m != null && nifty500?.rank_6m != null) {
    const avg = (nifty500.rank_1m + nifty500.rank_3m + nifty500.rank_6m) / 3
    if      (avg <= 2.5) grade = 'A'
    else if (avg <= 4.5) grade = 'B'
    else if (avg <= 6.5) grade = 'C'
    else                 grade = 'D'
  }

  return {
    as_of_date: baselines[0]?.as_of_date ?? null,
    baselines,
    hero: {
      today_leader: leader1w,
      india_rank_1m: nifty500?.rank_1m ?? null,
      large_vs_midsmall_spread_3m: spread_3m,
      india_rs_grade: grade,
    },
  }
}
