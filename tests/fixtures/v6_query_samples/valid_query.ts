// Fixture: valid query referencing tables that exist in migrations.
// Used by test_v6_data_availability_audit.py Case 1.

import sql from '@/lib/db'

export async function getStocksForDate(snapshotDate: string) {
  const rows = await sql`
    SELECT
      u.instrument_id::text AS iid,
      u.symbol,
      m.ret_1m::text AS ret_1m
    FROM atlas.atlas_universe_stocks u
    LEFT JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = u.instrument_id
     AND m.date = ${snapshotDate}
    WHERE u.effective_to IS NULL
  `
  return rows
}
