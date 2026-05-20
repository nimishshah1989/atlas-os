// frontend/src/lib/queries/regime-scorecard.ts
// Bottom-up signal scorecard + worklist counts for the regime homepage.
// All 4 signals trace to real computed DB columns — no fabrication.
//
// Signal sources:
//   trend         → atlas.atlas_stock_state_daily: % in stage_2a/2b/2c (latest date, v2.0-validated)
//   breadth       → atlas.atlas_market_regime_daily: pct_above_ema_50 (latest row)
//                   NOTE: breadth is passed in from the caller (page.tsx already fetches it)
//   momentum      → atlas.atlas_stock_state_daily: stage_2 count diff over 5 trading days
//   participation → atlas.atlas_sector_metrics_daily: avg(1 - leadership_concentration) latest date
//
// Worklist sources:
//   sectorsEnteredFavour → atlas_sector_signal_unified: sector_state newly Overweight today vs yesterday
//   freshBreakouts       → atlas.mv_breakout_candidates (count)
//   deterioration        → atlas.mv_deterioration_watch (count + symbols)

import 'server-only'
import sql from '@/lib/db'
import type { ScorecardTile, ScorecardData } from '@/components/regime/SignalScorecard'
import type { WorklistData } from '@/components/regime/TodayWorklist'

export type RegimeScorecardResult = {
  scorecard: ScorecardData
  worklist: WorklistData
}

// ── Individual query helpers ──────────────────────────────────────────────────

async function getTrendPct(): Promise<number | null> {
  const rows = await sql<{ stage2_pct: string | null }[]>`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_stock_state_daily
      WHERE classifier_version = 'v2.0-validated'
    )
    SELECT
      ROUND(
        COUNT(*) FILTER (WHERE state IN ('stage_2a','stage_2b','stage_2c'))::numeric
        / NULLIF(COUNT(*), 0),
        4
      )::text AS stage2_pct
    FROM atlas.atlas_stock_state_daily
    WHERE date = (SELECT d FROM latest)
      AND classifier_version = 'v2.0-validated'
  `
  const raw = rows[0]?.stage2_pct
  return raw != null ? parseFloat(raw) : null
}

async function getMomentumNet(): Promise<number | null> {
  // Count stage-2 stocks on the latest date minus count on 5 trading days ago.
  // Uses a subquery to find the 5th-most-recent distinct date.
  const rows = await sql<{ net_inflow: number | null }[]>`
    WITH dates AS (
      SELECT DISTINCT date
      FROM atlas.atlas_stock_state_daily
      WHERE classifier_version = 'v2.0-validated'
      ORDER BY date DESC
      LIMIT 6
    ),
    today_count AS (
      SELECT COUNT(*) AS cnt
      FROM atlas.atlas_stock_state_daily
      WHERE date = (SELECT date FROM dates ORDER BY date DESC LIMIT 1)
        AND classifier_version = 'v2.0-validated'
        AND state IN ('stage_2a','stage_2b','stage_2c')
    ),
    old_count AS (
      SELECT COUNT(*) AS cnt
      FROM atlas.atlas_stock_state_daily
      WHERE date = (SELECT date FROM dates ORDER BY date ASC LIMIT 1)
        AND classifier_version = 'v2.0-validated'
        AND state IN ('stage_2a','stage_2b','stage_2c')
    )
    SELECT (today_count.cnt - old_count.cnt)::int AS net_inflow
    FROM today_count, old_count
  `
  const raw = rows[0]?.net_inflow
  return raw != null ? raw : null
}

async function getParticipationBreadth(): Promise<number | null> {
  const rows = await sql<{ avg_breadth: string | null }[]>`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_sector_metrics_daily
    )
    SELECT
      ROUND(
        AVG(1 - leadership_concentration),
        4
      )::text AS avg_breadth
    FROM atlas.atlas_sector_metrics_daily
    WHERE date = (SELECT d FROM latest)
      AND leadership_concentration IS NOT NULL
  `
  const raw = rows[0]?.avg_breadth
  return raw != null ? parseFloat(raw) : null
}

async function getSectorsEnteredFavour(): Promise<number> {
  const rows = await sql<{ cnt: number }[]>`
    WITH latest_two AS (
      SELECT DISTINCT date
      FROM atlas.atlas_sector_signal_unified
      ORDER BY date DESC
      LIMIT 2
    ),
    today_date   AS (SELECT date FROM latest_two ORDER BY date DESC LIMIT 1),
    yest_date    AS (SELECT date FROM latest_two ORDER BY date ASC  LIMIT 1),
    today_rows   AS (
      SELECT sector FROM atlas.atlas_sector_signal_unified
      WHERE date = (SELECT date FROM today_date) AND sector_state = 'Overweight'
    ),
    yest_rows    AS (
      SELECT sector FROM atlas.atlas_sector_signal_unified
      WHERE date = (SELECT date FROM yest_date) AND sector_state = 'Overweight'
    )
    SELECT COUNT(*)::int AS cnt
    FROM today_rows t
    WHERE t.sector NOT IN (SELECT sector FROM yest_rows)
  `
  return rows[0]?.cnt ?? 0
}

type BreakoutRow = { symbol: string; cnt: number }

async function getBreakoutCandidates(limit = 10): Promise<BreakoutRow[]> {
  const rows = await sql<{ symbol: string }[]>`
    SELECT symbol
    FROM atlas.mv_breakout_candidates
    ORDER BY rs_pctile_3m DESC NULLS LAST
    LIMIT ${limit}
  `
  return rows.map((r, i) => ({ symbol: r.symbol, cnt: i }))
}

async function getBreakoutCount(): Promise<number> {
  const rows = await sql<{ cnt: number }[]>`
    SELECT COUNT(*)::int AS cnt FROM atlas.mv_breakout_candidates
  `
  return rows[0]?.cnt ?? 0
}

type DeteriorationRow = { symbol: string }

async function getDeteriorationWatch(limit = 10): Promise<DeteriorationRow[]> {
  return sql<DeteriorationRow[]>`
    SELECT symbol
    FROM atlas.mv_deterioration_watch
    ORDER BY rs_pctile_3m DESC NULLS LAST
    LIMIT ${limit}
  `
}

async function getDeteriorationCount(): Promise<number> {
  const rows = await sql<{ cnt: number }[]>`
    SELECT COUNT(*)::int AS cnt FROM atlas.mv_deterioration_watch
  `
  return rows[0]?.cnt ?? 0
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Fetches all 4 bottom-up scorecard signals + the 3-count worklist in parallel.
 * The `breadthRaw` param is passed in from the caller (already fetched from
 * atlas_market_regime_daily.pct_above_ema_50 via getCurrentRegime()) to avoid
 * a duplicate DB round-trip.
 */
export async function getRegimeScorecard(
  breadthRaw: string | null,
): Promise<RegimeScorecardResult> {
  const [
    trendPct,
    momentumNet,
    participationBreadth,
    sectorsEntered,
    breakoutCount,
    breakoutRows,
    deteriorationCount,
    deteriorationRows,
  ] = await Promise.all([
    getTrendPct(),
    getMomentumNet(),
    getParticipationBreadth(),
    getSectorsEnteredFavour(),
    getBreakoutCount(),
    getBreakoutCandidates(10),
    getDeteriorationCount(),
    getDeteriorationWatch(10),
  ])

  const breadthParsed = breadthRaw != null ? parseFloat(breadthRaw) : null

  const trendTile: ScorecardTile = {
    label: 'Trend',
    value: trendPct != null ? `${(trendPct * 100).toFixed(0)}%` : null,
    rawValue: trendPct,
    source: 'atlas_stock_state_daily: % in stage_2a/2b/2c, v2.0-validated, latest date',
  }

  const breadthTile: ScorecardTile = {
    label: 'Breadth',
    value: breadthParsed != null ? `${(breadthParsed * 100).toFixed(0)}%` : null,
    rawValue: breadthParsed,
    source: 'atlas_market_regime_daily: pct_above_ema_50, latest date',
  }

  const momentumTile: ScorecardTile = {
    label: 'Momentum',
    value: momentumNet != null ? (momentumNet > 0 ? `+${momentumNet}` : `${momentumNet}`) : null,
    rawValue: momentumNet,
    source: 'atlas_stock_state_daily: stage_2 count today minus count 5 trading days ago',
  }

  const participationTile: ScorecardTile = {
    label: 'Participation',
    value: participationBreadth != null ? `${(participationBreadth * 100).toFixed(0)}%` : null,
    rawValue: participationBreadth,
    source: 'atlas_sector_metrics_daily: avg(1 - leadership_concentration), latest date',
  }

  const worklist: WorklistData = {
    sectorsEnteredFavour: sectorsEntered,
    freshBreakouts:       breakoutCount,
    breakoutSymbols:      breakoutRows.map((r) => r.symbol),
    deterioratingCount:   deteriorationCount,
    deterioratingSymbols: deteriorationRows.map((r) => r.symbol),
  }

  return {
    scorecard: {
      trend:         trendTile,
      breadth:       breadthTile,
      momentum:      momentumTile,
      participation: participationTile,
    },
    worklist,
  }
}
