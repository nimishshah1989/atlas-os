// frontend/src/lib/queries/v6/switch_proposals.ts
//
// MF SWITCH proposals — surfaces funds in the user's held set that meet
// the switch criteria defined in atlas_mf_switch_rules.
//
// Locked methodology (CONTEXT.md MF SWITCH / migration 085 + 095):
//   - Same category only at v6 launch
//   - SWITCH fires when held fund's peer_quartile <= current_quartile_floor
//     AND a target fund in the same category with peer_quartile >=
//     target_quartile_ceiling AND consistency_months >=
//     min_target_consistency_months exists
//   - Tie-break on lowest expense ratio
//
// v6.0 null-data handling:
//   - atlas_paper_portfolio is EMPTY at v6.0 launch → getHeldIidSet() returns
//     an empty Set → getSwitchProposals() returns [] immediately (no SQL).
//   - atlas_mf_recommendation_daily is EMPTY (NAV gap — migration 096) →
//     peer_quartile cannot be looked up → returns [] without error.
//
// All Decimal columns are stringified (Postgres NUMERIC → string via postgres-js).

import 'server-only'
import { cache } from 'react'
import sql from '@/lib/db'
import { getHeldIidSet } from './portfolio_holdings'

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type SwitchProposal = {
  /** UUID of the held fund (source) */
  source_iid: string
  /** Morningstar/scheme code of the held fund */
  source_code: string
  /** Display name of the held fund */
  source_name: string
  /** Current peer quartile of the held fund */
  source_peer_quartile: 'Q1' | 'Q2' | 'Q3' | 'Q4'
  /** UUID of the recommended target fund */
  target_iid: string | null
  /** Scheme code of the recommended target fund */
  target_code: string | null
  /** Display name of the recommended target fund */
  target_name: string | null
  /** Peer quartile of the recommended target fund */
  target_peer_quartile: 'Q1' | 'Q2' | 'Q3' | 'Q4' | null
  /** Fund category (same for source and target) */
  category: string
}

// ---------------------------------------------------------------------------
// Internal row types
// ---------------------------------------------------------------------------

type SwitchRuleRow = {
  category: string
  current_quartile_floor: string
  target_quartile_ceiling: string
  min_target_consistency_months: number
  tie_break: string
}

type RecoRow = {
  mf_instrument_id: string
  category: string
  peer_quartile: string
  consistency_months: number
  expense_ratio: string | null
  date: string
  // Joined from atlas_fund_scorecard for display
  scheme_code: string | null
  fund_name: string | null
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const QUARTILE_ORDER: Record<string, number> = { Q1: 1, Q2: 2, Q3: 3, Q4: 4 }

function quartileAtOrBelow(q: string, floor: string): boolean {
  return (QUARTILE_ORDER[q] ?? 5) >= (QUARTILE_ORDER[floor] ?? 0)
}

function quartileAtOrAbove(q: string, ceiling: string): boolean {
  return (QUARTILE_ORDER[q] ?? 0) <= (QUARTILE_ORDER[ceiling] ?? 5)
}

// ---------------------------------------------------------------------------
// getSwitchProposals
// ---------------------------------------------------------------------------

/**
 * Return MF SWITCH proposals for the current user's held funds.
 *
 * Returns [] (not throws) in all null-data scenarios:
 *   - portfolio empty (v6.0 launch state)
 *   - atlas_mf_recommendation_daily empty (NAV gap)
 *   - no held fund meets the switch criteria
 *
 * Memoized per server request via React.cache().
 */
export const getSwitchProposals: () => Promise<SwitchProposal[]> = cache(
  async (): Promise<SwitchProposal[]> => {
    // Shortcut: no held funds → no proposals possible.
    const heldIids = await getHeldIidSet()
    if (heldIids.size === 0) return []

    // Fetch active switch rules.
    const rules = await sql<SwitchRuleRow[]>`
      SELECT
        category,
        current_quartile_floor::text,
        target_quartile_ceiling::text,
        min_target_consistency_months,
        tie_break
      FROM atlas.atlas_mf_switch_rules
      WHERE active = TRUE
    `
    if (rules.length === 0) return []

    // Fetch latest recommendation rows for all held funds.
    // atlas_mf_recommendation_daily may be empty (NAV gap at v6.0 launch) →
    // returns [] gracefully.
    const heldArray = Array.from(heldIids)
    const recoRows = await sql<RecoRow[]>`
      SELECT
        r.mf_instrument_id::text,
        r.category,
        r.peer_quartile::text,
        r.consistency_months,
        r.expense_ratio::text,
        r.date::text,
        s.scheme_code,
        COALESCE(s.fund_name, u.scheme_name) AS fund_name
      FROM atlas.atlas_mf_recommendation_daily r
      LEFT JOIN atlas.atlas_fund_scorecard s
        ON s.scheme_code = r.mf_instrument_id::text
       AND s.snapshot_date = (
         SELECT MAX(snapshot_date) FROM atlas.atlas_fund_scorecard
       )
      LEFT JOIN atlas.atlas_universe_funds u
        ON u.mstar_id = r.mf_instrument_id::text
       AND u.effective_to IS NULL
      WHERE r.mf_instrument_id = ANY(${heldArray}::uuid[])
        AND r.date = (
          SELECT MAX(date) FROM atlas.atlas_mf_recommendation_daily
          WHERE mf_instrument_id = r.mf_instrument_id
        )
    `

    // atlas_mf_recommendation_daily is currently empty → no data.
    if (recoRows.length === 0) return []

    const proposals: SwitchProposal[] = []

    for (const recoRow of recoRows) {
      // Find the applicable switch rule for this fund's category.
      const rule = rules.find((r) => r.category === recoRow.category)
      if (!rule) continue

      // Check: held fund is at/below the switch floor.
      if (!quartileAtOrBelow(recoRow.peer_quartile, rule.current_quartile_floor)) {
        continue
      }

      // Find a target fund: same category, quartile at/above ceiling, sufficient
      // consistency, different from the source fund.
      // NOTE: atlas_mf_recommendation_daily is empty in v6.0 — this query
      // returns no rows gracefully.
      const targets = await sql<RecoRow[]>`
        SELECT
          r.mf_instrument_id::text,
          r.category,
          r.peer_quartile::text,
          r.consistency_months,
          r.expense_ratio::text,
          r.date::text,
          s.scheme_code,
          COALESCE(s.fund_name, u.scheme_name) AS fund_name
        FROM atlas.atlas_mf_recommendation_daily r
        LEFT JOIN atlas.atlas_fund_scorecard s
          ON s.scheme_code = r.mf_instrument_id::text
         AND s.snapshot_date = (
           SELECT MAX(snapshot_date) FROM atlas.atlas_fund_scorecard
         )
        LEFT JOIN atlas.atlas_universe_funds u
          ON u.mstar_id = r.mf_instrument_id::text
         AND u.effective_to IS NULL
        WHERE r.category = ${recoRow.category}
          AND r.mf_instrument_id != ${recoRow.mf_instrument_id}::uuid
          AND r.date = (
            SELECT MAX(date) FROM atlas.atlas_mf_recommendation_daily
            WHERE category = ${recoRow.category}
          )
          AND r.consistency_months >= ${rule.min_target_consistency_months}
        ORDER BY
          -- Q1 < Q2 < Q3 < Q4 (lower = better quartile)
          CASE r.peer_quartile
            WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 ELSE 4
          END ASC,
          r.expense_ratio ASC NULLS LAST
        LIMIT 1
      `

      // Filter target by quartile ceiling.
      const target = targets.find((t) =>
        quartileAtOrAbove(t.peer_quartile, rule.target_quartile_ceiling),
      ) ?? null

      const sourceQuartile = recoRow.peer_quartile as SwitchProposal['source_peer_quartile']

      proposals.push({
        source_iid: recoRow.mf_instrument_id,
        source_code: recoRow.scheme_code ?? recoRow.mf_instrument_id,
        source_name: recoRow.fund_name ?? recoRow.scheme_code ?? recoRow.mf_instrument_id,
        source_peer_quartile: sourceQuartile,
        target_iid: target?.mf_instrument_id ?? null,
        target_code: target?.scheme_code ?? null,
        target_name: target?.fund_name ?? null,
        target_peer_quartile: target
          ? (target.peer_quartile as SwitchProposal['target_peer_quartile'])
          : null,
        category: recoRow.category,
      })
    }

    return proposals
  },
)
