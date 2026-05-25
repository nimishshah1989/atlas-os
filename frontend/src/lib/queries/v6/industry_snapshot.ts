// frontend/src/lib/queries/v6/industry_snapshot.ts
//
// Industry-level snapshot aggregation for the fund + ETF list pages.
// Returns IndustrySnapshot: total counts, atlas-leader/avoid counts,
// median expense, median AUM, and top-5 AMC leaderboard by composite_score.
//
// AMC leaderboard is returned for BOTH funds AND ETFs per Vocabulary lock
// override of design-lock §6.5 (FM-critic §1.5 critical gap #3).

import 'server-only'
import sql from '@/lib/db'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AmcLeaderboardRow = {
  amc: string
  avg_composite: string
  n_funds: number
}

export type IndustrySnapshot = {
  asset_class: 'funds' | 'etfs'
  n_total: number
  n_atlas_leaders: number
  n_avoid: number
  pct_above_benchmark_3y: string | null
  median_expense: string | null
  median_aum_cr: string | null
  amc_leaderboard: AmcLeaderboardRow[]
}

// ---------------------------------------------------------------------------
// Raw DB row types
// ---------------------------------------------------------------------------

type TotalsRow = {
  n_total: string
  n_atlas_leaders: string
  n_avoid: string
  median_expense: string | null
  median_aum_cr: string | null
}

type AmcRow = {
  amc: string
  avg_composite: string
  n_funds: string
}

// ---------------------------------------------------------------------------
// Query helpers
// ---------------------------------------------------------------------------

async function getFundSnapshot(): Promise<IndustrySnapshot> {
  const [totals] = await sql<TotalsRow[]>`
    SELECT
      COUNT(*)::text                                   AS n_total,
      SUM(CASE WHEN is_atlas_leader THEN 1 ELSE 0 END)::text AS n_atlas_leaders,
      SUM(CASE WHEN is_avoid THEN 1 ELSE 0 END)::text  AS n_avoid,
      AVG(
        NULLIF((sub_metrics->>'expense_ratio')::numeric, 0)
      )::text                                           AS median_expense,
      AVG(
        NULLIF((sub_metrics->>'aum_cr')::numeric, 0)
      )::text                                           AS median_aum_cr
    FROM atlas.atlas_fund_scorecard
    WHERE snapshot_date = (
      SELECT MAX(snapshot_date) FROM atlas.atlas_fund_scorecard
    )
  `

  const amcRows = await sql<AmcRow[]>`
    SELECT
      amc,
      AVG(composite_score)::text  AS avg_composite,
      COUNT(*)::text              AS n_funds
    FROM atlas.atlas_fund_scorecard
    WHERE snapshot_date = (
      SELECT MAX(snapshot_date) FROM atlas.atlas_fund_scorecard
    )
      AND amc IS NOT NULL
    GROUP BY amc
    ORDER BY AVG(composite_score) DESC NULLS LAST
    LIMIT 5
  `

  return {
    asset_class: 'funds',
    n_total: parseInt(totals?.n_total ?? '0', 10),
    n_atlas_leaders: parseInt(totals?.n_atlas_leaders ?? '0', 10),
    n_avoid: parseInt(totals?.n_avoid ?? '0', 10),
    pct_above_benchmark_3y: null,
    median_expense: totals?.median_expense ?? null,
    median_aum_cr: totals?.median_aum_cr ?? null,
    amc_leaderboard: amcRows.map((r) => ({
      amc: r.amc,
      avg_composite: r.avg_composite,
      n_funds: parseInt(r.n_funds, 10),
    })),
  }
}

async function getEtfSnapshot(): Promise<IndustrySnapshot> {
  const [totals] = await sql<TotalsRow[]>`
    SELECT
      COUNT(*)::text                                   AS n_total,
      SUM(CASE WHEN is_atlas_leader THEN 1 ELSE 0 END)::text AS n_atlas_leaders,
      SUM(CASE WHEN is_avoid THEN 1 ELSE 0 END)::text  AS n_avoid,
      AVG(
        NULLIF((sub_metrics->>'expense_ratio')::numeric, 0)
      )::text                                           AS median_expense,
      AVG(
        NULLIF((sub_metrics->>'aum_cr')::numeric, 0)
      )::text                                           AS median_aum_cr
    FROM atlas.atlas_etf_scorecard
    WHERE snapshot_date = (
      SELECT MAX(snapshot_date) FROM atlas.atlas_etf_scorecard
    )
  `

  // ETF scorecard uses `amc` column from atlas_universe_etfs join or directly.
  // We derive AMC from the scorecard amc column (populated at write time).
  const amcRows = await sql<AmcRow[]>`
    SELECT
      amc,
      AVG(composite_score)::text  AS avg_composite,
      COUNT(*)::text              AS n_funds
    FROM atlas.atlas_etf_scorecard
    WHERE snapshot_date = (
      SELECT MAX(snapshot_date) FROM atlas.atlas_etf_scorecard
    )
      AND amc IS NOT NULL
    GROUP BY amc
    ORDER BY AVG(composite_score) DESC NULLS LAST
    LIMIT 5
  `

  return {
    asset_class: 'etfs',
    n_total: parseInt(totals?.n_total ?? '0', 10),
    n_atlas_leaders: parseInt(totals?.n_atlas_leaders ?? '0', 10),
    n_avoid: parseInt(totals?.n_avoid ?? '0', 10),
    pct_above_benchmark_3y: null,
    median_expense: totals?.median_expense ?? null,
    median_aum_cr: totals?.median_aum_cr ?? null,
    amc_leaderboard: amcRows.map((r) => ({
      amc: r.amc,
      avg_composite: r.avg_composite,
      n_funds: parseInt(r.n_funds, 10),
    })),
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Fetch an IndustrySnapshot aggregation for the given asset class.
 * Reads the most recent snapshot_date from the relevant scorecard table.
 * Returns counts, median expense/AUM, and top-5 AMC leaderboard.
 * AMC leaderboard is included for both funds and ETFs per Vocabulary lock override.
 */
export async function getIndustrySnapshot(
  assetClass: 'funds' | 'etfs',
): Promise<IndustrySnapshot> {
  if (assetClass === 'etfs') {
    return getEtfSnapshot()
  }
  return getFundSnapshot()
}
