// Fixture: query referencing a table that does NOT exist in migrations.
// Used by test_v6_data_availability_audit.py Case 2.

import sql from '@/lib/db'

export async function getMissingData(snapshotDate: string) {
  const rows = await sql`
    SELECT s.some_column
    FROM atlas.atlas_nonexistent_table_xyz s
    LEFT JOIN atlas.atlas_universe_stocks u
      ON u.instrument_id = s.instrument_id
    WHERE s.date = ${snapshotDate}
  `
  return rows
}
