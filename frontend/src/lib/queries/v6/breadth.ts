// src/lib/queries/v6/breadth.ts
// Native Nifty-500 breadth series — reads atlas_foundation.breadth_nifty500_daily
// (built from fs.technical_daily; 26y of daily counts above 21/50/200-EMA + momentum).
// Powers the merged Markets Today page: the 3 breadth count charts + the SignalScorecard
// breadth/momentum tiles. No atlas.* dependency.
import 'server-only'
import sql from '@/lib/db'

export type BreadthRow = {
  date: string // 'YYYY-MM-DD'
  n_members: number
  above_21: number
  above_50: number
  above_200: number
  gc_50_200: number // # of N500 stocks with 50-EMA > 200-EMA (golden cross)
  net_new_highs: number
  avg_rsi_14: string | null
  idx_ret_3m: string | null // Nifty 500 INDEX 3-month return (robust price momentum)
}

/** Daily breadth series for the last `years` (default 10) — ASC by date. */
export async function getBreadthSeries(years = 10): Promise<BreadthRow[]> {
  return sql<BreadthRow[]>`
    SELECT to_char(date, 'YYYY-MM-DD') AS date,
           n_members, above_21, above_50, above_200, gc_50_200, net_new_highs,
           avg_rsi_14, idx_ret_3m
    FROM atlas_foundation.breadth_nifty500_daily
    WHERE date >= NOW() - (${years} || ' years')::INTERVAL
    ORDER BY date ASC
  `
}
