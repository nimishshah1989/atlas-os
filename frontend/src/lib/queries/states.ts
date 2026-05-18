// frontend/src/lib/queries/states.ts
// Server-only query module for atlas_stock_state_daily and atlas_state_dwell_statistics.
// All NUMERIC ratio columns are cast to float8 at SELECT time; they are not
// price/AUM columns (no Decimal preservation required at this boundary).
import 'server-only'
import sql from '@/lib/db'

export interface StockState {
  instrument_id: string
  date: string  // ISO date
  state: 'uninvestable' | 'stage_1' | 'stage_2a' | 'stage_2b' | 'stage_2c' | 'stage_3' | 'stage_4'
  prior_state: string | null
  state_since_date: string
  dwell_days: number
  dwell_percentile: number | null
  urgency_score: 'urgent' | 'normal' | 'late' | 'n/a'
  within_state_rank: number | null
  rs_rank_12m: number | null
  close_vs_sma_50: number | null
  close_vs_sma_150: number | null
  close_vs_sma_200: number | null
  sma_200_slope: number | null
  volume_ratio_50d: number | null
  distribution_days: number | null
  classifier_version: string
}

export interface CohortBaseline {
  cohort_key: string
  state: string
  median_dwell_days: number | null
  p25_dwell_days: number | null
  p75_dwell_days: number | null
  p95_dwell_days: number | null
  n_observations: number
}

export interface StateHistoryEntry {
  date: string
  state: string
  dwell_days: number
}

export interface WithinStatePeer {
  instrument_id: string
  symbol: string
  within_state_rank: number
  rs_rank_12m: number
  dwell_days: number
}

/**
 * Latest classification row for this stock. Returns null if no row exists.
 * Reads the most recent classifier_version='v2.0-validated' row.
 */
export async function getStockState(instrumentId: string): Promise<StockState | null> {
  const rows = await sql<StockState[]>`
    SELECT
      instrument_id::text,
      date::text,
      state,
      prior_state,
      state_since_date::text,
      dwell_days,
      dwell_percentile,
      urgency_score,
      within_state_rank,
      rs_rank_12m::float8          AS rs_rank_12m,
      close_vs_sma_50::float8      AS close_vs_sma_50,
      close_vs_sma_150::float8     AS close_vs_sma_150,
      close_vs_sma_200::float8     AS close_vs_sma_200,
      sma_200_slope::float8        AS sma_200_slope,
      volume_ratio_50d::float8     AS volume_ratio_50d,
      distribution_days,
      classifier_version
    FROM atlas.atlas_stock_state_daily
    WHERE instrument_id = ${instrumentId}::uuid
      AND classifier_version = 'v2.0-validated'
    ORDER BY date DESC
    LIMIT 1
  `
  return rows[0] ?? null
}

/**
 * Cohort baseline for the given (cohort_key, state). Returns null if not found.
 * Uses the most recent as_of_date.
 */
export async function getCohortBaseline(
  cohortKey: string,
  state: string,
): Promise<CohortBaseline | null> {
  const rows = await sql<CohortBaseline[]>`
    SELECT
      cohort_key,
      state,
      median_dwell_days,
      p25_dwell_days,
      p75_dwell_days,
      p95_dwell_days,
      n_observations
    FROM atlas.atlas_state_dwell_statistics
    WHERE cohort_key = ${cohortKey}
      AND state = ${state}
    ORDER BY as_of_date DESC
    LIMIT 1
  `
  return rows[0] ?? null
}

/**
 * Determine cohort_key for a stock from atlas_universe_stocks.
 * Returns 'large_cap' if in_nifty_100, 'mid_cap' if in_nifty_500, else 'small_cap'.
 */
export async function getStockCohortKey(instrumentId: string): Promise<string> {
  const rows = await sql<{ in_nifty_100: boolean; in_nifty_500: boolean }[]>`
    SELECT in_nifty_100, in_nifty_500
    FROM atlas.atlas_universe_stocks
    WHERE instrument_id = ${instrumentId}::uuid
    LIMIT 1
  `
  const r = rows[0]
  if (!r) return 'small_cap'
  if (r.in_nifty_100) return 'large_cap'
  if (r.in_nifty_500) return 'mid_cap'
  return 'small_cap'
}

/**
 * Top N stocks in the same state on the same date, ranked by within_state_rank.
 * For the WithinStatePeers component. Default N=30.
 */
export async function getWithinStatePeers(
  state: string,
  asOfDate: string,
  limit = 30,
): Promise<WithinStatePeer[]> {
  return sql<WithinStatePeer[]>`
    SELECT
      s.instrument_id::text,
      u.symbol,
      s.within_state_rank,
      s.rs_rank_12m::float8 AS rs_rank_12m,
      s.dwell_days
    FROM atlas.atlas_stock_state_daily s
    JOIN atlas.atlas_universe_stocks u USING (instrument_id)
    WHERE s.classifier_version = 'v2.0-validated'
      AND s.state = ${state}
      AND s.date = ${asOfDate}::date
      AND s.within_state_rank IS NOT NULL
    ORDER BY s.within_state_rank DESC NULLS LAST
    LIMIT ${limit}
  `
}

/**
 * 252-day state history for the dwell timeline. Most recent first.
 */
export async function getStateHistory(
  instrumentId: string,
  days = 252,
): Promise<StateHistoryEntry[]> {
  return sql<StateHistoryEntry[]>`
    SELECT
      date::text,
      state,
      dwell_days
    FROM atlas.atlas_stock_state_daily
    WHERE instrument_id = ${instrumentId}::uuid
      AND classifier_version = 'v2.0-validated'
    ORDER BY date DESC
    LIMIT ${days}
  `
}
