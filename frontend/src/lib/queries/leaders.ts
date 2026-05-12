// frontend/src/lib/queries/leaders.ts
// Reads from mv_rs_leaders_daily, mv_breakout_candidates, mv_deterioration_watch.
// All three are materialized views populated nightly by pg_cron at 20:00 IST.
// Postgres NUMERIC columns return as `string | null` — parse to number at
// display time, never here.
import 'server-only'
import sql from '@/lib/db'

export type RSLeaderRow = {
  instrument_id: string
  date: Date
  symbol: string
  company_name: string | null
  sector: string | null
  tier: string | null
  rs_pctile_3m: string | null    // NUMERIC — cross-stock percentile 0–1
  rs_pctile_1m: string | null    // NUMERIC
  rs_3m_nifty500: string | null  // NUMERIC — raw RS vs Nifty500 over 3 months
  ret_6m: string | null          // NUMERIC — 6-month total return
  rs_state: string | null        // 'Leader' | 'Strong'
  momentum_state: string | null
  state_since_date: Date | null
}

/**
 * Returns all current RS leaders / strong stocks from the materialized view.
 * Optionally filtered by sector. Ordered by rs_pctile_3m DESC NULLS LAST.
 *
 * @param sector  Filter to a specific sector, or null for all sectors.
 * @param limit   Maximum rows to return (default 100, max 500).
 */
export async function getRSLeaders(
  sector: string | null = null,
  limit = 100,
): Promise<RSLeaderRow[]> {
  if (limit < 1 || limit > 500) {
    throw new Error(`limit must be between 1 and 500, got: ${limit}`)
  }
  if (sector !== null) {
    return sql<RSLeaderRow[]>`
      SELECT
        instrument_id,
        date,
        symbol,
        company_name,
        sector,
        tier,
        rs_pctile_3m::text   AS rs_pctile_3m,
        rs_pctile_1m::text   AS rs_pctile_1m,
        rs_3m_nifty500::text AS rs_3m_nifty500,
        ret_6m::text         AS ret_6m,
        rs_state,
        momentum_state,
        state_since_date
      FROM atlas.mv_rs_leaders_daily
      WHERE sector = ${sector}
      ORDER BY rs_pctile_3m DESC NULLS LAST
      LIMIT ${limit}
    `
  }
  return sql<RSLeaderRow[]>`
    SELECT
      instrument_id,
      date,
      symbol,
      company_name,
      sector,
      tier,
      rs_pctile_3m::text   AS rs_pctile_3m,
      rs_pctile_1m::text   AS rs_pctile_1m,
      rs_3m_nifty500::text AS rs_3m_nifty500,
      ret_6m::text         AS ret_6m,
      rs_state,
      momentum_state,
      state_since_date
    FROM atlas.mv_rs_leaders_daily
    ORDER BY rs_pctile_3m DESC NULLS LAST
    LIMIT ${limit}
  `
}

export type BreakoutCandidateRow = {
  instrument_id: string
  date: Date
  symbol: string
  company_name: string | null
  sector: string | null
  tier: string | null
  new_rs_state: string | null
  prior_rs_state: string | null
  momentum_state: string | null
  state_since_date: Date | null
  rs_pctile_3m: string | null
  rs_3m_nifty500: string | null
}

export type DeteriorationWatchRow = BreakoutCandidateRow

/**
 * Stocks transitioning INTO 'Strong' or 'Leader' on the latest trading day.
 */
export async function getBreakoutCandidates(): Promise<BreakoutCandidateRow[]> {
  return sql<BreakoutCandidateRow[]>`
    SELECT
      instrument_id,
      date,
      symbol,
      company_name,
      sector,
      tier,
      new_rs_state,
      prior_rs_state,
      momentum_state,
      state_since_date,
      rs_pctile_3m::text   AS rs_pctile_3m,
      rs_3m_nifty500::text AS rs_3m_nifty500
    FROM atlas.mv_breakout_candidates
    ORDER BY rs_pctile_3m DESC NULLS LAST
  `
}

/**
 * Stocks transitioning OUT of 'Strong'/'Leader' on the latest trading day —
 * an early-warning watch list.
 */
export async function getDeteriorationWatch(): Promise<DeteriorationWatchRow[]> {
  return sql<DeteriorationWatchRow[]>`
    SELECT
      instrument_id,
      date,
      symbol,
      company_name,
      sector,
      tier,
      new_rs_state,
      prior_rs_state,
      momentum_state,
      state_since_date,
      rs_pctile_3m::text   AS rs_pctile_3m,
      rs_3m_nifty500::text AS rs_3m_nifty500
    FROM atlas.mv_deterioration_watch
    ORDER BY rs_pctile_3m DESC NULLS LAST
  `
}

// ── Percolation queries — RS Leaders data surfaced at sector / fund / ETF level ──

export type SectorLeaderStat = {
  sector: string
  leader_count: number
  top_symbols: string[]
}

/**
 * Per-sector leader count + top 3 symbols ranked by 3M RS pctile.
 * Used to enrich the SectorDecisionTable with a Leaders column.
 */
export async function getLeadersBySector(): Promise<SectorLeaderStat[]> {
  const rows = await sql<{ sector: string; leader_count: string; top_symbols: string | null }[]>`
    SELECT
      sector,
      COUNT(*)::text                                                   AS leader_count,
      STRING_AGG(symbol, ',' ORDER BY rs_pctile_3m DESC NULLS LAST)   AS top_symbols
    FROM atlas.mv_rs_leaders_daily
    WHERE sector IS NOT NULL
    GROUP BY sector
    ORDER BY COUNT(*) DESC
  `
  return rows.map(r => ({
    sector: r.sector,
    leader_count: Number(r.leader_count),
    top_symbols: r.top_symbols ? r.top_symbols.split(',').slice(0, 3) : [],
  }))
}

export type LeaderHoldingRow = {
  instrument_id: string
  symbol: string
  company_name: string | null
  sector: string | null
  weight: string       // decimal fraction, e.g. "0.0512"
  rs_state: string | null
  rs_pctile_3m: string | null
  momentum_state: string | null
}

/**
 * Which of a mutual fund's holdings are currently RS Leaders or Strong.
 * Returns at most the latest disclosure period's data joined to the MV.
 */
export async function getFundLeaderHoldings(mstarId: string): Promise<LeaderHoldingRow[]> {
  return sql<LeaderHoldingRow[]>`
    SELECT
      h.instrument_id,
      l.symbol,
      l.company_name,
      l.sector,
      (h.weight_pct / 100)::text AS weight,
      l.rs_state,
      l.rs_pctile_3m::text       AS rs_pctile_3m,
      l.momentum_state
    FROM de_mf_holdings h
    INNER JOIN atlas.mv_rs_leaders_daily l USING (instrument_id)
    WHERE h.mstar_id   = ${mstarId}
      AND h.as_of_date = (
        SELECT MAX(as_of_date) FROM de_mf_holdings WHERE mstar_id = ${mstarId}
      )
    ORDER BY l.rs_pctile_3m DESC NULLS LAST
  `
}

/**
 * Which of an ETF's holdings are currently RS Leaders or Strong.
 */
export async function getETFLeaderHoldings(ticker: string): Promise<LeaderHoldingRow[]> {
  return sql<LeaderHoldingRow[]>`
    SELECT
      h.instrument_id,
      l.symbol,
      l.company_name,
      l.sector,
      h.weight::text       AS weight,
      l.rs_state,
      l.rs_pctile_3m::text AS rs_pctile_3m,
      l.momentum_state
    FROM de_etf_holdings h
    INNER JOIN atlas.mv_rs_leaders_daily l USING (instrument_id)
    WHERE h.ticker    = ${ticker}
      AND h.as_of_date = (
        SELECT MAX(as_of_date) FROM de_etf_holdings WHERE ticker = ${ticker}
      )
    ORDER BY l.rs_pctile_3m DESC NULLS LAST
  `
}
