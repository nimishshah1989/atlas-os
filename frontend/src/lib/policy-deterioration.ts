/**
 * Policy deterioration evaluator — pure TypeScript, no I/O.
 *
 * Given a list of holdings (each with their current engine_state) and the
 * portfolio's effective policy exit rules, returns the subset of holdings
 * that are hitting an exit trigger.
 *
 * Exit rules evaluated:
 *   state_exit_full  — holding's engine_state matches → full-exit rule
 *   state_exit_trim  — holding's engine_state matches → trim rule
 *
 * hard_stop_pct: intentionally NOT evaluated.
 * Reason (C5 honesty): no entry-price, cost-basis, or return-since-entry data
 * exists in the portfolio holdings JSONB or any joinable table. Fabricating a
 * return-since-entry would violate the NO SYNTHETIC DATA law. The panel
 * honestly labels hard-stop as "n/a — entry price not tracked".
 *
 * Mutual exclusivity guarantee (C7):
 * By policy design, state_exit_full and state_exit_trim are different states
 * from buy_states (e.g. stage_3/stage_4 vs stage_2a/2b/2c). A holding whose
 * engine_state triggers an exit rule will never be in buy_states, so it
 * cannot simultaneously be a buy candidate. Unit-tested explicitly.
 *
 * NULL handling (honest):
 *   - engine_state null → not matched, not surfaced
 *   - state_exit_trim null → trim check skipped
 *   - state_exit_full null → full-exit check skipped
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DeteriHolding {
  instrument_id: string
  symbol: string | null
  /** Current Weinstein engine state, e.g. 'stage_3', 'stage_4'. null = unclassified. */
  engine_state: string | null
  /** Current weight as a whole-number percentage (e.g. 7.5 = 7.5%). */
  weight_pct: number
}

export interface DeteriPolicy {
  /** State that triggers a partial trim. null = trim check disabled. */
  state_exit_trim: string | null
  /** State that triggers a full exit. null = full-exit check disabled. */
  state_exit_full: string | null
  /** Allowed entry states — used for mutual-exclusivity assertion in tests. */
  buy_states: string[]
}

export type DeteriRule = 'full_exit' | 'trim'

export interface DeteriItem {
  instrument_id: string
  symbol: string | null
  /** The engine_state that triggered this item. */
  engine_state: string
  weight_pct: number
  rule: DeteriRule
  /** Human-readable reason string, e.g. "stage_4 — full exit required". */
  reason: string
}

// ---------------------------------------------------------------------------
// Pure evaluator
// ---------------------------------------------------------------------------

/**
 * Evaluate each holding against the policy's exit rules.
 *
 * Returns a new array of DeteriItem for holdings that hit an exit trigger.
 * Input order is preserved for consistent UI rendering.
 *
 * @param holdings  Portfolio holdings with current engine_state.
 * @param policy    Exit-rule params from the effective policy.
 * @returns         Array of deteriorating holdings (may be empty).
 */
export function findDeterioration(
  holdings: DeteriHolding[],
  policy: DeteriPolicy,
): DeteriItem[] {
  const items: DeteriItem[] = []

  for (const holding of holdings) {
    // NULL engine_state: cannot match any exit rule — honest skip.
    if (holding.engine_state == null) continue

    const state = holding.engine_state

    // Rule 1: full-exit check
    if (policy.state_exit_full != null && state === policy.state_exit_full) {
      items.push({
        instrument_id: holding.instrument_id,
        symbol: holding.symbol,
        engine_state: state,
        weight_pct: holding.weight_pct,
        rule: 'full_exit',
        reason: `${state} — full exit required`,
      })
      // A holding can only match one rule (state is a single value). Skip trim check.
      continue
    }

    // Rule 2: trim check
    if (policy.state_exit_trim != null && state === policy.state_exit_trim) {
      items.push({
        instrument_id: holding.instrument_id,
        symbol: holding.symbol,
        engine_state: state,
        weight_pct: holding.weight_pct,
        rule: 'trim',
        reason: `${state} — trim position`,
      })
    }
  }

  return items
}
