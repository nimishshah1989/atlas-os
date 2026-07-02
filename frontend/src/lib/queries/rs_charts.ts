// src/lib/queries/rs_charts.ts
// Cap-tier relative-strength series — each tier index ÷ Nifty 500, daily, from
// atlas_foundation.index_prices. Powers the RS charts on the Sectors page
// (small/mid/micro-cap + juniorBeES vs Nifty 500). Native fs; no atlas dependency.
import 'server-only'
import sql from '@/lib/db'

export type CapTierRSRow = {
  date: string
  sc: string | null      // Nifty Smallcap 250 ÷ Nifty 500
  mc: string | null      // Nifty Midcap 150 ÷ Nifty 500
  micro: string | null   // Nifty Microcap 250 ÷ Nifty 500
  junior: string | null  // Nifty Next 50 (juniorBeES) ÷ Nifty 500
}

export async function getCapTierRS(years = 10): Promise<CapTierRSRow[]> {
  return sql<CapTierRSRow[]>`
    SELECT to_char(n.date, 'YYYY-MM-DD') AS date,
           (sc.close / n.close)::text AS sc,
           (mc.close / n.close)::text AS mc,
           (mi.close / n.close)::text AS micro,
           (jr.close / n.close)::text AS junior
    FROM atlas_foundation.index_prices n
    LEFT JOIN atlas_foundation.index_prices sc ON sc.date = n.date AND sc.index_code = 'NIFTY SMLCAP 250'
    LEFT JOIN atlas_foundation.index_prices mc ON mc.date = n.date AND mc.index_code = 'NIFTY MIDCAP 150'
    LEFT JOIN atlas_foundation.index_prices mi ON mi.date = n.date AND mi.index_code = 'NIFTY MICROCAP250'
    LEFT JOIN atlas_foundation.index_prices jr ON jr.date = n.date AND jr.index_code = 'NIFTY NEXT 50'
    WHERE n.index_code = 'NIFTY 500' AND n.close > 0 AND n.date >= NOW() - (${years} || ' years')::INTERVAL
    ORDER BY n.date ASC
  `
}
