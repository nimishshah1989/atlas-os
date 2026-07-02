// Fund rank-history read layer — atlas_foundation.fund_rank_daily (built nightly by
// scripts/foundation/build_fund_rank_history.py). One compact per-fund series powers the
// daily-slice bar, the "rank stable X days" badge and the 30d/90d rank-swing columns on the
// funds table. Derived stats are computed from the SAME slices via the pure helpers in
// lib/v6/rankHistory.ts, so the bar and the badges can never disagree.
import 'server-only'
import sql from '@/lib/db'
import { stableDays, rankSwing, pctBand, type RankSlice } from '@/lib/v6/rankHistory'

export type FundRankHistory = {
  slices: RankSlice[]
  latestRank: number | null
  latestSize: number | null
  band: string | null
  stableDays: number
  swing30: number | null
  swing90: number | null
}

// Map keyed by mstar_id. Funds with no history (new / no holdings) are simply absent.
export async function getFundRankHistory(): Promise<Map<string, FundRankHistory>> {
  // Last ~180 trading days only — enough for the 90-day swing + a long slice bar, and bounds the
  // serialized payload as the daily history grows.
  const rows = (await sql`
    SELECT mstar_id,
      json_agg(json_build_object('d', to_char(date,'YYYY-MM-DD'), 'r', cat_rank, 's', cat_size)
               ORDER BY date) AS slices
    FROM atlas_foundation.fund_rank_daily
    WHERE date >= (SELECT max(date) - INTERVAL '180 days' FROM atlas_foundation.fund_rank_daily)
    GROUP BY mstar_id
  `) as unknown as { mstar_id: string; slices: RankSlice[] }[]

  const out = new Map<string, FundRankHistory>()
  for (const r of rows) {
    const slices = (r.slices ?? []).filter((s) => s.r != null)
    if (slices.length === 0) continue
    const last = slices[slices.length - 1]
    out.set(r.mstar_id, {
      slices,
      latestRank: last.r,
      latestSize: last.s,
      band: pctBand(last.r, last.s),
      stableDays: stableDays(slices),
      swing30: rankSwing(slices, 30),
      swing90: rankSwing(slices, 90),
    })
  }
  return out
}
