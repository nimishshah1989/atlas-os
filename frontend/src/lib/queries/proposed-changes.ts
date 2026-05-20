// src/lib/queries/proposed-changes.ts
// Server-only queries over atlas.atlas_portfolio_proposed_change.
// Created for Task 3.5: current-vs-target view needs pending proposed changes per portfolio.
import 'server-only'
import sql from '@/lib/db'

export type ProposedChangeRow = {
  id: string
  instrument_id: string
  // symbol resolved via LEFT JOIN atlas_universe_stocks; null if instrument not in universe
  symbol: string | null
  proposed_weight: string   // NUMERIC → string (parse at display time)
  status: 'pending' | 'applied' | 'rejected'
  rationale: string | null
  created_at: Date
  updated_at: Date
}

/**
 * Returns all pending proposed changes for a given portfolio, most-recent first.
 * Only returns rows with status='pending' — applied/rejected are historical and
 * do not appear in the current-vs-target live view.
 *
 * Joins atlas_universe_stocks to resolve a symbol for each proposed instrument_id.
 * If the instrument is not in the universe (e.g. recently de-listed or an ETF not in
 * atlas_universe_stocks), symbol is NULL.
 */
export async function getPendingProposedChanges(
  portfolioId: string,
): Promise<ProposedChangeRow[]> {
  return sql<ProposedChangeRow[]>`
    SELECT
      pc.id::text              AS id,
      pc.instrument_id::text   AS instrument_id,
      u.symbol                 AS symbol,
      pc.proposed_weight::text AS proposed_weight,
      pc.status,
      pc.rationale,
      pc.created_at,
      pc.updated_at
    FROM atlas.atlas_portfolio_proposed_change pc
    LEFT JOIN LATERAL (
      SELECT symbol
      FROM atlas.atlas_universe_stocks
      WHERE instrument_id = pc.instrument_id
      ORDER BY effective_from DESC
      LIMIT 1
    ) u ON TRUE
    WHERE pc.portfolio_id = ${portfolioId}
      AND pc.status = 'pending'
    ORDER BY pc.created_at DESC
  `
}
