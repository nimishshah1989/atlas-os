// frontend/src/lib/queries/v6/stocks-landscape.ts
//
// Query layer for Page 05 Stocks — Landscape extension.
// Sources: atlas.mv_stock_landscape (747 rows, refreshed nightly)
//
// Three exported functions:
//   getStocksLandscape()  — full 747-row dataset for bubble chart + six picks
//   getMatrixCells()      — server-side GROUP BY for the 24-cell count matrix
//   getHeroStories()      — 4 narrative blocks (fresh BUYs, AVOIDs, high-conf, exits)

import 'server-only'
import sql from '@/lib/db'

// ---------------------------------------------------------------------------
// Shared row type from mv_stock_landscape
// ---------------------------------------------------------------------------

export type LandscapeRow = {
  instrument_id: string
  symbol: string
  company_name: string | null
  sector: string | null
  industry: string | null
  cap_tier: 'Large' | 'Mid' | 'Small'
  // Returns stored as ratio form (e.g. -0.04 = -4%). Multiply by 100 for display.
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  // RS also ratio form vs Nifty500
  rs_1m_nifty500: string | null
  rs_3m_nifty500: string | null
  // Composite score: numeric range roughly -10 to +10
  composite_score: string | null
  conviction_tier: string | null
  confidence_label: string | null
  action: 'BUY' | 'WATCH' | 'AVOID' | null
  bubble_quadrant: string | null
  liquidity_proxy_cr: string | null
  close_price: string | null
  matrix_tenure_dominant: string | null
  matrix_action_sign: string | null
  cell_id: string | null
  cell_ic: string | null
  cell_tenure: string | null
  cell_action: string | null
  cell_fire_date: string | null
  // composite_trajectory_30d is JSONB: [{date: string, score: number}]
  composite_trajectory_30d: Array<{ date: string; score: number }> | null
  refreshed_at: string | null
  // The market-data date the snapshot reflects (e.g. 2026-05-29 Friday), as
  // opposed to refreshed_at which is the wall-clock instant the MV cron ran.
  as_of_date: string | null
}

// ---------------------------------------------------------------------------
// getStocksLandscape — all columns needed for bubble chart + six picks
// Row count invariant: assert > 0 before returning
// ---------------------------------------------------------------------------

export async function getStocksLandscape(): Promise<LandscapeRow[]> {
  const rows = await sql<LandscapeRow[]>`
    SELECT
      instrument_id::text,
      symbol,
      company_name,
      sector,
      industry,
      cap_tier,
      ret_1m::text,
      ret_3m::text,
      ret_6m::text,
      ret_12m::text,
      rs_1m_nifty500::text,
      rs_3m_nifty500::text,
      composite_score::text,
      conviction_tier,
      confidence_label,
      action,
      bubble_quadrant,
      liquidity_proxy_cr::text,
      close_price::text,
      matrix_tenure_dominant,
      matrix_action_sign,
      cell_id::text,
      cell_ic::text,
      cell_tenure,
      cell_action,
      cell_fire_date::text,
      composite_trajectory_30d,
      refreshed_at::text,
      as_of_date::text
    FROM atlas.mv_stock_landscape
    ORDER BY composite_score DESC NULLS LAST
  `
  return rows
}

// ---------------------------------------------------------------------------
// MatrixCellAgg — aggregated for the 24-cell count matrix
// ---------------------------------------------------------------------------

export type MatrixCellAgg = {
  cap_tier: 'Large' | 'Mid' | 'Small'
  // tenure: '1m' | '3m' | '6m' | '12m'
  tenure: string
  // action_sign: 'POS' | 'NEG'
  action_sign: string
  count: number
  avg_ic: string | null
}

// Group by cap_tier × matrix_tenure_dominant × matrix_action_sign.
// Only rows with non-null tenure/action_sign qualify (a row may have NULLs if
// the instrument has no active cell firing).
export async function getMatrixCells(): Promise<MatrixCellAgg[]> {
  const rows = await sql<Array<{
    cap_tier: string
    tenure: string
    action_sign: string
    count: string
    avg_ic: string | null
  }>>`
    SELECT
      cap_tier,
      matrix_tenure_dominant AS tenure,
      matrix_action_sign     AS action_sign,
      COUNT(*)::text                                   AS count,
      AVG(cell_ic) FILTER (WHERE cell_ic IS NOT NULL)::text AS avg_ic
    FROM atlas.mv_stock_landscape
    WHERE
      matrix_tenure_dominant IS NOT NULL
      AND matrix_action_sign IS NOT NULL
    GROUP BY cap_tier, matrix_tenure_dominant, matrix_action_sign
    ORDER BY cap_tier, matrix_tenure_dominant, matrix_action_sign
  `

  return rows.map(r => ({
    cap_tier: r.cap_tier as 'Large' | 'Mid' | 'Small',
    tenure: r.tenure,
    action_sign: r.action_sign,
    count: parseInt(r.count, 10),
    avg_ic: r.avg_ic,
  }))
}

// ---------------------------------------------------------------------------
// HeroStories — 4 narrative blocks
// ---------------------------------------------------------------------------

export type HeroStock = {
  symbol: string
  company_name: string | null
  sector: string | null
  cap_tier: string
  composite_score: string | null
  rs_3m_nifty500: string | null
  action: string | null
  confidence_label: string | null
  matrix_tenure_dominant: string | null
  matrix_action_sign: string | null
}

export type HeroStories = {
  freshBuys: HeroStock[]
  freshAvoids: HeroStock[]
  highConfBuys: HeroStock[]
  exitCandidates: HeroStock[]
  stats: {
    totalUniverse: number
    buyCount: number
    watchCount: number
    avoidCount: number
    highConfBuyCount: number
  }
}

export async function getHeroStories(): Promise<HeroStories> {
  const [freshBuys, freshAvoids, highConf, exits, stats] = await Promise.all([
    // Fresh BUYs: top composite BUYs
    sql<HeroStock[]>`
      SELECT
        symbol, company_name, sector, cap_tier,
        composite_score::text AS composite_score,
        rs_3m_nifty500::text AS rs_3m_nifty500,
        action, confidence_label,
        matrix_tenure_dominant, matrix_action_sign
      FROM atlas.mv_stock_landscape
      WHERE action = 'BUY'
      ORDER BY composite_score DESC NULLS LAST
      LIMIT 5
    `,
    // Fresh AVOIDs: worst composite first
    sql<HeroStock[]>`
      SELECT
        symbol, company_name, sector, cap_tier,
        composite_score::text AS composite_score,
        rs_3m_nifty500::text AS rs_3m_nifty500,
        action, confidence_label,
        matrix_tenure_dominant, matrix_action_sign
      FROM atlas.mv_stock_landscape
      WHERE action = 'AVOID'
      ORDER BY composite_score ASC NULLS LAST
      LIMIT 5
    `,
    // High conviction BUYs: confidence_label = 'industry_grade' or 'high_confidence'
    sql<HeroStock[]>`
      SELECT
        symbol, company_name, sector, cap_tier,
        composite_score::text AS composite_score,
        rs_3m_nifty500::text AS rs_3m_nifty500,
        action, confidence_label,
        matrix_tenure_dominant, matrix_action_sign
      FROM atlas.mv_stock_landscape
      WHERE
        action = 'BUY'
        AND confidence_label IN ('industry_grade', 'high_confidence', 'tier_1')
      ORDER BY composite_score DESC NULLS LAST
      LIMIT 5
    `,
    // Exit candidates: BUY or WATCH with falling composite (composite_score < 2)
    sql<HeroStock[]>`
      SELECT
        symbol, company_name, sector, cap_tier,
        composite_score::text AS composite_score,
        rs_3m_nifty500::text AS rs_3m_nifty500,
        action, confidence_label,
        matrix_tenure_dominant, matrix_action_sign
      FROM atlas.mv_stock_landscape
      WHERE
        action IN ('BUY', 'WATCH')
        AND composite_score < 2
      ORDER BY composite_score ASC NULLS LAST
      LIMIT 5
    `,
    // Summary stats
    sql<Array<{ action: string | null; count: string; high_conf: string }>>`
      SELECT
        action,
        COUNT(*)::text AS count,
        COUNT(*) FILTER (
          WHERE confidence_label IN ('industry_grade', 'high_confidence', 'tier_1')
        )::text AS high_conf
      FROM atlas.mv_stock_landscape
      GROUP BY action
    `,
  ])

  // Build stats
  let totalUniverse = 0
  let buyCount = 0
  let watchCount = 0
  let avoidCount = 0
  let highConfBuyCount = 0

  for (const s of stats) {
    const n = parseInt(s.count, 10)
    totalUniverse += n
    if (s.action === 'BUY') {
      buyCount = n
      highConfBuyCount = parseInt(s.high_conf, 10)
    } else if (s.action === 'WATCH') {
      watchCount = n
    } else if (s.action === 'AVOID') {
      avoidCount = n
    }
  }

  // Fallback: high conf from actual filtered query if fresh query returned 0
  const hcFromQuery = highConf.length
  if (highConfBuyCount === 0 && hcFromQuery > 0) {
    highConfBuyCount = hcFromQuery
  }

  return {
    freshBuys,
    freshAvoids,
    highConfBuys: highConf,
    exitCandidates: exits,
    stats: { totalUniverse, buyCount, watchCount, avoidCount, highConfBuyCount },
  }
}
