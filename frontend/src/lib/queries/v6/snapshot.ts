// frontend/src/lib/queries/v6/snapshot.ts
//
// Shared helper: returns the most recent snapshot_date available across the
// v6 scorecard / conviction tables. All v6 pages anchor to a single
// snapshot date so user reads the same as-of consistently.

import 'server-only'
import sql from '@/lib/db'

export type LatestSnapshot = {
  /** ISO date string e.g. "2026-05-22" */
  snapshot_date: string
}

/**
 * Resolve the most recent snapshot_date across the v6 surfaces.
 *
 * We coalesce across scorecard_daily / conviction_daily / etf_scorecard /
 * fund_scorecard to handle the case where one writer runs late — we still
 * want a usable as-of for the surfaces that DID land.
 *
 * Falls back to CURRENT_DATE if nothing has landed (fresh DB).
 */
export async function getLatestSnapshotDate(): Promise<string> {
  const rows = await sql<{ d: string | null }[]>`
    SELECT GREATEST(
      (SELECT MAX(snapshot_date) FROM atlas.atlas_conviction_daily),
      (SELECT MAX(snapshot_date) FROM atlas.atlas_etf_scorecard),
      (SELECT MAX(snapshot_date) FROM atlas.atlas_fund_scorecard),
      (SELECT MAX(date)          FROM atlas.atlas_scorecard_daily),
      (SELECT MAX(date)          FROM atlas.atlas_market_regime_daily),
      (SELECT MAX(date)          FROM atlas.atlas_sector_states_daily)
    )::text AS d
  `
  return rows[0]?.d ?? new Date().toISOString().slice(0, 10)
}
