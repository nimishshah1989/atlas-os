// Tests for src/lib/policy-validate.ts
// TDD: written before implementation.
// Mirrors the Python validate_policy test semantics exactly.
//
// 9 rules:
//   Rule 1: min_holdings > max_positions → violation
//   Rule 2: max_per_stock_pct > max_per_sector_pct → violation
//   Rule 3: cash_floor_pct outside [0, 100] → violation
//   Rule 4: min_within_state_rank outside [0, 1] → violation
//   Rule 5: min_rs_rank outside [0, 1] → violation
//   Rule 6: instrument_universe not in allowed set → violation
//   Rule 7: rebalance_cadence not in allowed set → violation
//   Rule 8: hard_stop_pct <= 0 → violation
//   Rule 9: trailing_stop_pct set and <= 0 → violation

import { describe, it, expect } from 'vitest'
import { validatePolicy } from '@/lib/policy-validate'
import type { FlatPolicy } from '@/lib/policy-validate'

// ---------------------------------------------------------------------------
// Baseline valid policy — matches the Python test baseline
// ---------------------------------------------------------------------------

const VALID_POLICY: FlatPolicy = {
  cash_floor_pct: '5',
  respect_regime_cap: true,
  max_per_stock_pct: '5',
  max_per_sector_pct: '15',
  max_small_cap_pct: '30',
  min_holdings: '10',
  max_positions: '30',
  buy_states: ['Emerging', 'Stage2'],
  min_within_state_rank: '0.60',
  min_rs_rank: '0.70',
  hard_stop_pct: '8',
  state_exit_trim: 'Stage3',
  state_exit_full: 'Stage4',
  trailing_stop_pct: null,
  instrument_universe: 'direct_equity',
  benchmark: 'NIFTY500',
  rebalance_cadence: 'weekly',
}

// ---------------------------------------------------------------------------
// Rule 1: min_holdings > max_positions
// ---------------------------------------------------------------------------

describe('validatePolicy — Rule 1: min_holdings vs max_positions', () => {
  it('returns a violation when min_holdings exceeds max_positions', () => {
    // Python test case: min_holdings=50, max_positions=40 → violation
    const policy: FlatPolicy = { ...VALID_POLICY, min_holdings: '50', max_positions: '40' }
    const violations = validatePolicy(policy)
    expect(violations).toHaveLength(1)
    expect(violations[0]).toMatch(/min_holdings/)
    expect(violations[0]).toMatch(/max_positions/)
  })

  it('no violation when min_holdings equals max_positions', () => {
    const policy: FlatPolicy = { ...VALID_POLICY, min_holdings: '30', max_positions: '30' }
    expect(validatePolicy(policy)).toHaveLength(0)
  })

  it('no violation when min_holdings is less than max_positions', () => {
    expect(validatePolicy(VALID_POLICY)).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Rule 2: max_per_stock_pct > max_per_sector_pct
// ---------------------------------------------------------------------------

describe('validatePolicy — Rule 2: max_per_stock vs max_per_sector', () => {
  it('returns a violation when max_per_stock_pct exceeds max_per_sector_pct', () => {
    // Python test case: max_per_stock=20, max_per_sector=15 → violation
    const policy: FlatPolicy = { ...VALID_POLICY, max_per_stock_pct: '20', max_per_sector_pct: '15' }
    const violations = validatePolicy(policy)
    expect(violations).toHaveLength(1)
    expect(violations[0]).toMatch(/max_per_stock_pct/)
    expect(violations[0]).toMatch(/max_per_sector_pct/)
  })

  it('no violation when max_per_stock_pct equals max_per_sector_pct', () => {
    const policy: FlatPolicy = { ...VALID_POLICY, max_per_stock_pct: '15', max_per_sector_pct: '15' }
    expect(validatePolicy(policy)).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Rule 3: cash_floor_pct in [0, 100]
// ---------------------------------------------------------------------------

describe('validatePolicy — Rule 3: cash_floor_pct range', () => {
  it('returns a violation when cash_floor_pct is negative', () => {
    const policy: FlatPolicy = { ...VALID_POLICY, cash_floor_pct: '-1' }
    const violations = validatePolicy(policy)
    expect(violations).toHaveLength(1)
    expect(violations[0]).toMatch(/cash_floor_pct/)
  })

  it('returns a violation when cash_floor_pct is above 100', () => {
    const policy: FlatPolicy = { ...VALID_POLICY, cash_floor_pct: '101' }
    const violations = validatePolicy(policy)
    expect(violations).toHaveLength(1)
    expect(violations[0]).toMatch(/cash_floor_pct/)
  })

  it('no violation at boundary 0', () => {
    const policy: FlatPolicy = { ...VALID_POLICY, cash_floor_pct: '0' }
    expect(validatePolicy(policy)).toHaveLength(0)
  })

  it('no violation at boundary 100', () => {
    const policy: FlatPolicy = { ...VALID_POLICY, cash_floor_pct: '100' }
    expect(validatePolicy(policy)).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Rule 4: min_within_state_rank in [0, 1]
// ---------------------------------------------------------------------------

describe('validatePolicy — Rule 4: min_within_state_rank range', () => {
  it('returns a violation when min_within_state_rank is out of [0, 1]', () => {
    // Python test case: rank out of [0,1] → violation
    const policy: FlatPolicy = { ...VALID_POLICY, min_within_state_rank: '1.5' }
    const violations = validatePolicy(policy)
    expect(violations).toHaveLength(1)
    expect(violations[0]).toMatch(/min_within_state_rank/)
  })

  it('returns a violation when min_within_state_rank is negative', () => {
    const policy: FlatPolicy = { ...VALID_POLICY, min_within_state_rank: '-0.1' }
    const violations = validatePolicy(policy)
    expect(violations).toHaveLength(1)
    expect(violations[0]).toMatch(/min_within_state_rank/)
  })

  it('no violation at boundary 0', () => {
    const policy: FlatPolicy = { ...VALID_POLICY, min_within_state_rank: '0' }
    expect(validatePolicy(policy)).toHaveLength(0)
  })

  it('no violation at boundary 1', () => {
    const policy: FlatPolicy = { ...VALID_POLICY, min_within_state_rank: '1' }
    expect(validatePolicy(policy)).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Rule 5: min_rs_rank in [0, 1]
// ---------------------------------------------------------------------------

describe('validatePolicy — Rule 5: min_rs_rank range', () => {
  it('returns a violation when min_rs_rank is out of [0, 1]', () => {
    // Python test case: rank out of [0,1] → violation
    const policy: FlatPolicy = { ...VALID_POLICY, min_rs_rank: '2' }
    const violations = validatePolicy(policy)
    expect(violations).toHaveLength(1)
    expect(violations[0]).toMatch(/min_rs_rank/)
  })
})

// ---------------------------------------------------------------------------
// Rule 6: instrument_universe allowed set
// ---------------------------------------------------------------------------

describe('validatePolicy — Rule 6: instrument_universe', () => {
  it('returns a violation for an unknown instrument_universe', () => {
    // Python test case: bad instrument_universe → violation
    const policy: FlatPolicy = { ...VALID_POLICY, instrument_universe: 'crypto' }
    const violations = validatePolicy(policy)
    expect(violations).toHaveLength(1)
    expect(violations[0]).toMatch(/instrument_universe/)
    expect(violations[0]).toMatch(/crypto/)
  })

  it('accepts all four valid values', () => {
    const valid = ['direct_equity', 'etf', 'mutual_fund', 'mixed']
    for (const u of valid) {
      const policy: FlatPolicy = { ...VALID_POLICY, instrument_universe: u }
      expect(validatePolicy(policy)).toHaveLength(0)
    }
  })
})

// ---------------------------------------------------------------------------
// Rule 7: rebalance_cadence allowed set
// ---------------------------------------------------------------------------

describe('validatePolicy — Rule 7: rebalance_cadence', () => {
  it('returns a violation for an unknown rebalance_cadence', () => {
    const policy: FlatPolicy = { ...VALID_POLICY, rebalance_cadence: 'quarterly' }
    const violations = validatePolicy(policy)
    expect(violations).toHaveLength(1)
    expect(violations[0]).toMatch(/rebalance_cadence/)
  })

  it('accepts all three valid cadences', () => {
    for (const c of ['daily', 'weekly', 'monthly']) {
      const policy: FlatPolicy = { ...VALID_POLICY, rebalance_cadence: c }
      expect(validatePolicy(policy)).toHaveLength(0)
    }
  })
})

// ---------------------------------------------------------------------------
// Rule 8: hard_stop_pct > 0
// ---------------------------------------------------------------------------

describe('validatePolicy — Rule 8: hard_stop_pct', () => {
  it('returns a violation when hard_stop_pct is zero', () => {
    const policy: FlatPolicy = { ...VALID_POLICY, hard_stop_pct: '0' }
    const violations = validatePolicy(policy)
    expect(violations).toHaveLength(1)
    expect(violations[0]).toMatch(/hard_stop_pct/)
  })

  it('returns a violation when hard_stop_pct is negative', () => {
    const policy: FlatPolicy = { ...VALID_POLICY, hard_stop_pct: '-5' }
    const violations = validatePolicy(policy)
    expect(violations).toHaveLength(1)
    expect(violations[0]).toMatch(/hard_stop_pct/)
  })

  it('no violation when hard_stop_pct is strictly positive', () => {
    const policy: FlatPolicy = { ...VALID_POLICY, hard_stop_pct: '8' }
    expect(validatePolicy(policy)).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Rule 9: trailing_stop_pct, when set, must be > 0
// ---------------------------------------------------------------------------

describe('validatePolicy — Rule 9: trailing_stop_pct', () => {
  it('no violation when trailing_stop_pct is null (disabled)', () => {
    const policy: FlatPolicy = { ...VALID_POLICY, trailing_stop_pct: null }
    expect(validatePolicy(policy)).toHaveLength(0)
  })

  it('returns a violation when trailing_stop_pct is zero', () => {
    const policy: FlatPolicy = { ...VALID_POLICY, trailing_stop_pct: '0' }
    const violations = validatePolicy(policy)
    expect(violations).toHaveLength(1)
    expect(violations[0]).toMatch(/trailing_stop_pct/)
  })

  it('returns a violation when trailing_stop_pct is negative', () => {
    const policy: FlatPolicy = { ...VALID_POLICY, trailing_stop_pct: '-3' }
    const violations = validatePolicy(policy)
    expect(violations).toHaveLength(1)
    expect(violations[0]).toMatch(/trailing_stop_pct/)
  })

  it('no violation when trailing_stop_pct is a positive string', () => {
    const policy: FlatPolicy = { ...VALID_POLICY, trailing_stop_pct: '5' }
    expect(validatePolicy(policy)).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Multiple violations accumulate
// ---------------------------------------------------------------------------

describe('validatePolicy — multiple violations', () => {
  it('returns multiple violation messages when multiple rules fire', () => {
    // min_holdings(50) > max_positions(40) AND max_per_stock(20) > max_per_sector(15)
    const policy: FlatPolicy = {
      ...VALID_POLICY,
      min_holdings: '50',
      max_positions: '40',
      max_per_stock_pct: '20',
      max_per_sector_pct: '15',
    }
    const violations = validatePolicy(policy)
    expect(violations.length).toBeGreaterThanOrEqual(2)
  })
})

// ---------------------------------------------------------------------------
// Fully valid policy → []
// ---------------------------------------------------------------------------

describe('validatePolicy — fully valid policy', () => {
  it('returns [] for the baseline valid policy', () => {
    expect(validatePolicy(VALID_POLICY)).toEqual([])
  })
})
