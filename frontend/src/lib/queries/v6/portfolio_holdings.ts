// frontend/src/lib/queries/v6/portfolio_holdings.ts
//
// Server-only queries for per-iid paper-portfolio book state.
//
// Source: atlas.atlas_paper_portfolio (migration 084)
//
// v6.0 context: this table is EMPTY at launch — the portfolio writer cron is
// out of scope for v6.0. Both exports handle the empty-table case gracefully:
//   - getHoldingState returns null (no error)
//   - getHeldIidSet returns an empty Set (no error)
//
// Multi-user readiness: queries run via the service-role connection (@/lib/db)
// which bypasses RLS. At v6.0 there is a single-user assumption so no user_id
// filter is applied. When multi-user lands (v6.1+), add a user_id parameter
// and pass it as a SQL bind variable — do NOT interpolate it directly.
//
// Weight gap (v6.0): atlas_paper_portfolio has no weight_pct column. Weight
// is not stored per-lot; the schema tracks entry_price and position count only.
// weight_range and aggregate_weight are returned as ["0.00", "0.00"] / "0.00"
// until v6.1 derives weight from notional sizing data.
// TODO(v6.1): compute weight_range from lot notional / total_book_notional.

import 'server-only'
import { cache } from 'react'
import sql from '@/lib/db'

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type HoldingState = {
  /** Number of open portfolio rows for this instrument (across all users). */
  portfolio_count: number
  /**
   * Stringified Decimal [min_weight, max_weight] across users.
   * v6.0: always ["0.00", "0.00"] — no weight_pct column in migration 084.
   * TODO(v6.1): derive from notional / total book notional per user.
   */
  weight_range: [string, string]
  /**
   * Sum of weights across all open positions for this instrument.
   * v6.0: always "0.00" — see weight_range note above.
   * TODO(v6.1): sum(per-user weight_pct).
   */
  aggregate_weight: string
  /** MAX(entry_date) of all open positions, or null when no positions exist. */
  last_add_date: string | null
}

// ---------------------------------------------------------------------------
// Internal row type — Postgres returns numerics as string, counts as number
// ---------------------------------------------------------------------------

type HoldingAggRow = {
  portfolio_count: string | number
  last_add_date: string | null
}

type HeldIidRow = {
  instrument_id: string
}

// ---------------------------------------------------------------------------
// getHoldingState
// ---------------------------------------------------------------------------

/**
 * Return book-state for a single instrument.
 *
 * Returns null when the instrument has no open positions (including when the
 * table is empty — the v6.0 launch state).
 *
 * @param iid  UUID of the instrument (atlas_paper_portfolio.instrument_id).
 */
export async function getHoldingState(iid: string): Promise<HoldingState | null> {
  const rows = await sql<HoldingAggRow[]>`
    SELECT
      COUNT(*)::int                     AS portfolio_count,
      MAX(entry_date)::text             AS last_add_date
    FROM atlas.atlas_paper_portfolio
    WHERE instrument_id = ${iid}::uuid
      AND exit_date IS NULL
  `

  const row = rows[0]
  // COUNT(*) always returns a row (even for zero matches). If count is 0
  // there is no holding — return null per the spec.
  const count = typeof row?.portfolio_count === 'string'
    ? parseInt(row.portfolio_count, 10)
    : (row?.portfolio_count ?? 0)

  if (!row || count === 0) return null

  return {
    portfolio_count: count,
    // v6.0: weight_pct column does not exist in migration 084.
    // Placeholder stringified Decimals. TODO(v6.1): real weight derivation.
    weight_range: ['0.00', '0.00'],
    aggregate_weight: '0.00',
    last_add_date: row.last_add_date ?? null,
  }
}

// ---------------------------------------------------------------------------
// getHeldIidSet
// ---------------------------------------------------------------------------

/**
 * Return a Set of all instrument UUIDs with at least one open position.
 *
 * Memoized per server request via React.cache() — list pages (stocks,
 * sectors, etc.) call this once; all PortfolioBadge instances share the
 * result without re-querying.
 *
 * Returns an empty Set when the table has no open positions (the v6.0
 * launch state).
 */
export const getHeldIidSet: () => Promise<Set<string>> = cache(async () => {
  const rows = await sql<HeldIidRow[]>`
    SELECT DISTINCT instrument_id::text AS instrument_id
    FROM atlas.atlas_paper_portfolio
    WHERE exit_date IS NULL
  `
  return new Set(rows.map((r) => r.instrument_id))
})
