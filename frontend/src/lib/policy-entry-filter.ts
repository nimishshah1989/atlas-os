/**
 * Policy entry-rule filter — pure TypeScript, no I/O.
 *
 * Given a list of candidate instruments and the policy's entry-rule params,
 * returns only those candidates that pass ALL three gates:
 *   1. engine_state ∈ buy_states
 *   2. within_state_rank (null → 0) >= min_within_state_rank
 *   3. rs_rank_12m       (null → 0) >= min_rs_rank
 *
 * NULL handling (honest — no fabricated data):
 *   - engine_state null → excluded (cannot match any buy_state)
 *   - within_state_rank null → treated as 0 (excluded when threshold > 0)
 *   - rs_rank_12m null → treated as 0 (excluded when threshold > 0)
 *
 * Placement rationale: the consumer (StockScreener) is a frontend component
 * that already holds the fetched stock array. Filtering in JS over <500 stocks
 * is sub-millisecond; no second round-trip needed.  The pure-function contract
 * allows deterministic unit tests with hand-specified inputs (DoD #4 verified).
 *
 * Column mapping from atlas_stock_signal_unified (via stocks.ts):
 *   engine_state     → su.engine_state
 *   within_state_rank → su.within_state_rank::float8   (fraction [0,1])
 *   rs_rank_12m      → su.rs_rank_12m::float8          (fraction [0,1])
 */

export interface CandidateInstrument {
  instrument_id: string
  symbol: string
  /** Weinstein engine state, e.g. 'stage_2a', 'stage_2b'. null = unclassified. */
  engine_state: string | null
  /** Quantile rank within state cohort, [0,1]. null = not computed (treated as 0). */
  within_state_rank: number | null
  /** 12-month RS quantile rank, [0,1]. null = not computed (treated as 0). */
  rs_rank_12m: number | null
}

export interface PolicyEntryParams {
  /** Allowed Weinstein states for entry. Empty list = no stock passes. */
  buy_states: string[]
  /** Minimum within-state rank required (fraction [0,1]). */
  min_within_state_rank: number
  /** Minimum 12-month RS rank required (fraction [0,1]). */
  min_rs_rank: number
}

/**
 * Filter candidates against a policy's entry rules.
 *
 * Returns a new array (input order preserved) of candidates satisfying all
 * three entry gates. Pure function — no side effects, no I/O.
 *
 * @param candidates   Instruments to filter. May be empty.
 * @param params       Entry-rule params extracted from the effective policy.
 * @returns Filtered array, preserving input order.
 */
export function applyEntryFilter(
  candidates: CandidateInstrument[],
  params: PolicyEntryParams,
): CandidateInstrument[] {
  const buySet = new Set(params.buy_states)
  const { min_within_state_rank, min_rs_rank } = params

  return candidates.filter(c => {
    // Gate 1: state membership
    if (c.engine_state == null || !buySet.has(c.engine_state)) return false

    // Gate 2: within_state_rank (null → 0)
    const rank = c.within_state_rank ?? 0
    if (rank < min_within_state_rank) return false

    // Gate 3: rs_rank_12m (null → 0)
    const rs = c.rs_rank_12m ?? 0
    if (rs < min_rs_rank) return false

    return true
  })
}
