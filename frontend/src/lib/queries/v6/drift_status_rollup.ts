// frontend/src/lib/queries/v6/drift_status_rollup.ts
//
// D.12 — drift_warn rollup count for DiffSinceYesterdayPanel header chip.
//
// Source: atlas.atlas_cell_definitions.drift_status
// Enum literal: 'drift_warn' per migration 080 DRIFT_STATUS enum
//   {healthy, drift_warn, deprecated}
//
// Returns a plain count. An empty atlas_cell_definitions table returns 0 (no error).

import 'server-only'
import sql from '@/lib/db'

type CountRow = { cnt: string | number }

/**
 * Returns the count of cells currently in drift_warn status.
 *
 * Uses corrected enum literal 'drift_warn' per migration 080
 * (NOT 'drift_confirmed' or 'clean' as earlier design docs implied).
 *
 * Returns 0 when the table is empty or no cells are in drift_warn.
 */
export async function getDriftWarnCount(): Promise<number> {
  const rows = await sql<CountRow[]>`
    SELECT COUNT(*)::text AS cnt
    FROM atlas.atlas_cell_definitions
    WHERE drift_status = 'drift_warn'
  `
  const raw = rows[0]?.cnt
  if (raw == null) return 0
  const n = typeof raw === 'string' ? parseInt(raw, 10) : raw
  return Number.isNaN(n) ? 0 : n
}
