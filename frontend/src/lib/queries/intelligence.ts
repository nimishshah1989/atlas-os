// frontend/src/lib/queries/intelligence.ts
// Morning dashboard — aggregates regime, brief, sector rotation, breakouts,
// deterioration watch, and RS leaders into a single parallel-fetch call.
import 'server-only'
import sql from '@/lib/db'

// ── Types ────────────────────────────────────────────────────────────────────

export type RegimeSummary = {
  date: Date
  regime_state: string
  deployment_multiplier: string | null
  india_vix: string | null
  pct_above_ema_50: string | null
  ad_ratio: string | null
  mcclellan_oscillator: string | null
  net_new_highs: number | null
}

export type BriefSummary = {
  as_of_date: Date
  regime_state: string
  narrative: string
  key_themes: string[]
}

export type SectorSnapshotRow = {
  sector_name: string
  rrg_quadrant: string | null
}

export type BreakoutRow = {
  symbol: string
  sector: string | null
  prior_rs_state: string | null
  new_rs_state: string | null
}

export type RSLeaderSnapshotRow = {
  symbol: string
  sector: string | null
  rs_state: string | null
  rs_pctile_3m: string | null
}

export type IntelligenceDashboardData = {
  regime: RegimeSummary | null
  brief: BriefSummary | null
  sectors: SectorSnapshotRow[]
  breakouts: BreakoutRow[]
  deterioration: BreakoutRow[]
  rsLeaders: RSLeaderSnapshotRow[]
}

// ── Query ────────────────────────────────────────────────────────────────────

export async function getIntelligenceDashboard(): Promise<IntelligenceDashboardData> {
  const [regimeRows, briefRows, sectorRows, breakoutRows, detRows, rsRows] =
    await Promise.all([
      sql<RegimeSummary[]>`
        SELECT
          date,
          regime_state,
          deployment_multiplier::text  AS deployment_multiplier,
          india_vix::text              AS india_vix,
          pct_above_ema_50::text       AS pct_above_ema_50,
          ad_ratio::text               AS ad_ratio,
          mcclellan_oscillator::text   AS mcclellan_oscillator,
          net_new_highs
        FROM atlas.mv_current_market_regime
        LIMIT 1
      `,
      sql<BriefSummary[]>`
        SELECT
          as_of_date,
          regime_state,
          narrative,
          key_themes
        FROM atlas.atlas_daily_briefs
        ORDER BY as_of_date DESC
        LIMIT 1
      `,
      sql<SectorSnapshotRow[]>`
        SELECT sector_name, rrg_quadrant
        FROM atlas.mv_sector_rotation_state
        ORDER BY rs_pctile_cross_sector DESC NULLS LAST
      `,
      sql<BreakoutRow[]>`
        SELECT
          symbol,
          sector,
          prior_rs_state,
          new_rs_state
        FROM atlas.mv_breakout_candidates
        ORDER BY rs_pctile_3m DESC NULLS LAST
        LIMIT 5
      `,
      sql<BreakoutRow[]>`
        SELECT
          symbol,
          sector,
          prior_rs_state,
          new_rs_state
        FROM atlas.mv_deterioration_watch
        ORDER BY rs_pctile_3m DESC NULLS LAST
        LIMIT 5
      `,
      sql<RSLeaderSnapshotRow[]>`
        SELECT
          symbol,
          sector,
          rs_state,
          rs_pctile_3m::text AS rs_pctile_3m
        FROM atlas.mv_rs_leaders_daily
        WHERE rs_state IN ('Leader', 'Strong')
        ORDER BY rs_pctile_3m DESC NULLS LAST
        LIMIT 8
      `,
    ])

  return {
    regime:      regimeRows[0] ?? null,
    brief:       briefRows[0] ?? null,
    sectors:     sectorRows,
    breakouts:   breakoutRows,
    deterioration: detRows,
    rsLeaders:   rsRows,
  }
}
