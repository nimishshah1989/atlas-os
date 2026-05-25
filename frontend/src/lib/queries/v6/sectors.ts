// frontend/src/lib/queries/v6/sectors.ts
//
// Direct Supabase query for the v6 Sectors page.
//
// Joins:
//   atlas_sector_states_daily   ← sector_state ("Overweight"/"Avoid" etc.)
//   atlas_sector_metrics_daily  ← ret_1m / 3m / 6m + participation_rs / breadth
//
// Returns ScreenSector[] consumed by /v6/sectors and /v6/sectors/[name].
// Rank is computed in-app by ordering on participation_rs desc.

import 'server-only'
import sql from '@/lib/db'
import type { ScreenSector } from '@/lib/api/v1'

type Row = {
  sector_name: string
  sector_state: string
  bottomup_state: string | null
  topdown_state: string | null
  bottomup_rs_state: string | null
  bottomup_momentum_state: string | null
  participation_rs_pct: string | null
  bottomup_ret_1m: string | null
  bottomup_ret_3m: string | null
  bottomup_rs_3m_nifty500: string | null
  participation_50: string | null
  constituent_count: number | null
}

/**
 * Return all sectors for a snapshot_date, ranked by participation_rs_pct desc.
 *
 * The page expects ScreenSector — we fill in v6.x placeholders for
 * rrg_quadrant, cells_favored_today and days_in_state (those are not yet
 * surfaced from the new sector pipeline).
 */
export async function getSectorsForDate(snapshotDate: string): Promise<ScreenSector[]> {
  const rows = await sql<Row[]>`
    SELECT
      s.sector_name,
      s.sector_state,
      s.bottomup_state,
      s.topdown_state,
      s.bottomup_rs_state,
      s.bottomup_momentum_state,
      s.participation_rs_pct::text   AS participation_rs_pct,
      m.bottomup_ret_1m::text        AS bottomup_ret_1m,
      m.bottomup_ret_3m::text        AS bottomup_ret_3m,
      m.bottomup_rs_3m_nifty500::text AS bottomup_rs_3m_nifty500,
      m.participation_50::text       AS participation_50,
      m.constituent_count
    FROM atlas.atlas_sector_states_daily s
    LEFT JOIN atlas.atlas_sector_metrics_daily m
      ON m.sector_name = s.sector_name
     AND m.date        = s.date
    WHERE s.date = ${snapshotDate}
    ORDER BY
      CASE s.sector_state
        WHEN 'Overweight'  THEN 0
        WHEN 'Neutral'     THEN 1
        WHEN 'Underweight' THEN 2
        WHEN 'Avoid'       THEN 3
        ELSE 4
      END,
      s.participation_rs_pct DESC NULLS LAST
  `

  return rows.map((r, idx): ScreenSector => ({
    sector_iid: r.sector_name,
    sector_name: r.sector_name,
    rank: idx + 1,
    rank_change: 0,
    days_in_state: 0,
    sector_state: r.sector_state,
    breadth_pct_stage_2: r.participation_50 != null ? Number(r.participation_50) / 100 : null,
    vol_regime: r.bottomup_momentum_state ?? 'Normal',
    rs_pct_cross_sector: r.bottomup_rs_3m_nifty500 != null
      ? Number(r.bottomup_rs_3m_nifty500)
      : null,
    ret_1m: r.bottomup_ret_1m != null ? Number(r.bottomup_ret_1m) : null,
    ret_3m: r.bottomup_ret_3m != null ? Number(r.bottomup_ret_3m) : null,
    rrg_quadrant: null,
    cells_favored_today: [],
  }))
}
