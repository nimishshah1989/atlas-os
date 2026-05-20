// src/lib/policy-validate.ts
// Pure TS port of atlas/intelligence/policy/policy.py validate_policy.
// 9 consistency rules — exact mirror of the Python implementation.
// Returns violation messages; [] = valid. No DB access.
//
// Storage convention (mirrors Python docstring):
//   pct columns: whole-number percent stored as string ('5' = 5%)
//   rank columns: fraction in [0,1] stored as string ('0.60' = 60th-percentile)
//   int columns: stored as string ('10' = 10)
//   bool columns: JS boolean
//   array columns: string[]
//   trailing_stop_pct: string | null (null = disabled)

// ---------------------------------------------------------------------------
// Allowed value sets — mirror CHECK constraints from migration 092
// ---------------------------------------------------------------------------

const ALLOWED_UNIVERSES = new Set(['direct_equity', 'etf', 'mutual_fund', 'mixed'])
const ALLOWED_CADENCES = new Set(['daily', 'weekly', 'monthly'])

// ---------------------------------------------------------------------------
// FlatPolicy — all 17 policy fields as they arrive from the Postgres driver
// ---------------------------------------------------------------------------

export type FlatPolicy = {
  cash_floor_pct: string | null
  respect_regime_cap: boolean | null
  max_per_stock_pct: string | null
  max_per_sector_pct: string | null
  max_small_cap_pct: string | null
  min_holdings: string | null
  max_positions: string | null
  buy_states: string[] | null
  min_within_state_rank: string | null
  min_rs_rank: string | null
  hard_stop_pct: string | null
  state_exit_trim: string | null
  state_exit_full: string | null
  trailing_stop_pct: string | null
  instrument_universe: string | null
  benchmark: string | null
  rebalance_cadence: string | null
}

export const POLICY_FIELDS: ReadonlyArray<keyof FlatPolicy> = [
  'cash_floor_pct',
  'respect_regime_cap',
  'max_per_stock_pct',
  'max_per_sector_pct',
  'max_small_cap_pct',
  'min_holdings',
  'max_positions',
  'buy_states',
  'min_within_state_rank',
  'min_rs_rank',
  'hard_stop_pct',
  'state_exit_trim',
  'state_exit_full',
  'trailing_stop_pct',
  'instrument_universe',
  'benchmark',
  'rebalance_cadence',
]

// ---------------------------------------------------------------------------
// validatePolicy — pure function
// ---------------------------------------------------------------------------

/**
 * Returns a list of human-readable violation strings for a FlatPolicy.
 * An empty list means the policy is internally consistent.
 *
 * Rules mirror atlas/intelligence/policy/policy.py validate_policy exactly:
 *   Rule 1: min_holdings must not exceed max_positions
 *   Rule 2: max_per_stock_pct must not exceed max_per_sector_pct
 *   Rule 3: cash_floor_pct must be in [0, 100]
 *   Rule 4: min_within_state_rank must be in [0, 1]
 *   Rule 5: min_rs_rank must be in [0, 1]
 *   Rule 6: instrument_universe must be in the allowed set
 *   Rule 7: rebalance_cadence must be in the allowed set
 *   Rule 8: hard_stop_pct must be strictly positive
 *   Rule 9: trailing_stop_pct, when set, must be strictly positive
 */
export function validatePolicy(policy: FlatPolicy): string[] {
  const violations: string[] = []

  const minHoldings = Number(policy.min_holdings)
  const maxPositions = Number(policy.max_positions)
  const maxPerStock = Number(policy.max_per_stock_pct)
  const maxPerSector = Number(policy.max_per_sector_pct)
  const cashFloor = Number(policy.cash_floor_pct)
  const minWithinStateRank = Number(policy.min_within_state_rank)
  const minRsRank = Number(policy.min_rs_rank)
  const hardStop = Number(policy.hard_stop_pct)

  // Rule 1: min_holdings <= max_positions
  if (minHoldings > maxPositions) {
    violations.push(
      `min_holdings ${policy.min_holdings} exceeds max_positions ` +
        `${policy.max_positions} — portfolio cannot be fully constructed`,
    )
  }

  // Rule 2: max_per_stock_pct <= max_per_sector_pct
  if (maxPerStock > maxPerSector) {
    violations.push(
      `max_per_stock_pct ${policy.max_per_stock_pct} exceeds ` +
        `max_per_sector_pct ${policy.max_per_sector_pct} — a single stock ` +
        `cannot be allowed more weight than its whole sector cap`,
    )
  }

  // Rule 3: cash_floor_pct in [0, 100]
  if (cashFloor < 0 || cashFloor > 100) {
    violations.push(
      `cash_floor_pct ${policy.cash_floor_pct} is outside the valid range [0, 100]`,
    )
  }

  // Rule 4: min_within_state_rank in [0, 1]
  if (minWithinStateRank < 0 || minWithinStateRank > 1) {
    violations.push(
      `min_within_state_rank ${policy.min_within_state_rank} is outside ` +
        `the valid range [0, 1] (must be a quantile fraction)`,
    )
  }

  // Rule 5: min_rs_rank in [0, 1]
  if (minRsRank < 0 || minRsRank > 1) {
    violations.push(
      `min_rs_rank ${policy.min_rs_rank} is outside the valid range [0, 1] ` +
        `(must be a quantile fraction)`,
    )
  }

  // Rule 6: instrument_universe in allowed set
  if (policy.instrument_universe !== null && !ALLOWED_UNIVERSES.has(policy.instrument_universe)) {
    violations.push(
      `instrument_universe '${policy.instrument_universe}' is not one of ` +
        `${JSON.stringify([...ALLOWED_UNIVERSES].sort())}`,
    )
  }

  // Rule 7: rebalance_cadence in allowed set
  if (policy.rebalance_cadence !== null && !ALLOWED_CADENCES.has(policy.rebalance_cadence)) {
    violations.push(
      `rebalance_cadence '${policy.rebalance_cadence}' is not one of ` +
        `${JSON.stringify([...ALLOWED_CADENCES].sort())}`,
    )
  }

  // Rule 8: hard_stop_pct > 0
  if (hardStop <= 0) {
    violations.push(
      `hard_stop_pct ${policy.hard_stop_pct} must be strictly positive — ` +
        `a zero or negative stop is degenerate`,
    )
  }

  // Rule 9: trailing_stop_pct, when set, must be > 0
  if (policy.trailing_stop_pct !== null) {
    const trailing = Number(policy.trailing_stop_pct)
    if (trailing <= 0) {
      violations.push(
        `trailing_stop_pct ${policy.trailing_stop_pct} must be strictly ` +
          `positive when set (use null to disable trailing stop)`,
      )
    }
  }

  return violations
}
