// Tests for src/lib/policy-compliance.ts
// Mirrors the Python compliance.py test suite exactly.
// TDD: written before implementation.
//
// Six rules:
//   max_per_stock   — any holding.weight_pct > policy.max_per_stock_pct
//   max_per_sector  — sector sum(weight_pct) > policy.max_per_sector_pct
//   max_small_cap   — sum(is_small_cap weights) > policy.max_small_cap_pct
//   min_holdings    — len(holdings) < policy.min_holdings
//   max_positions   — len(holdings) > policy.max_positions
//   cash_floor      — (100 − sum weights) < policy.cash_floor_pct
//
// All comparisons are STRICT (> or <). At-limit = not a breach.

import { describe, it, expect } from 'vitest'
import { checkCompliance } from '@/lib/policy-compliance'
import type { ComplianceHolding, CompliancePolicy } from '@/lib/policy-compliance'

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

const BASE_POLICY: CompliancePolicy = {
  max_per_stock_pct: 5,
  max_per_sector_pct: 15,
  max_small_cap_pct: 30,
  min_holdings: 5,
  max_positions: 30,
  cash_floor_pct: 5,
}

function makeHolding(overrides: Partial<ComplianceHolding>): ComplianceHolding {
  return {
    instrument_id: 'stock-a',
    weight_pct: 4,
    sector: 'IT',
    is_small_cap: false,
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Rule 1: max_per_stock
// ---------------------------------------------------------------------------

describe('checkCompliance — max_per_stock', () => {
  it('returns one breach when a holding weight strictly exceeds max_per_stock_pct', () => {
    // 7% holding vs 5% cap → breach (C6: 7 > 5)
    const holdings: ComplianceHolding[] = [
      makeHolding({ instrument_id: 'HDFCBANK', weight_pct: 7, sector: 'Banks' }),
      makeHolding({ instrument_id: 'INFY', weight_pct: 4, sector: 'IT' }),
    ]
    const breaches = checkCompliance(holdings, BASE_POLICY)
    const stockBreaches = breaches.filter((b) => b.rule === 'max_per_stock')
    expect(stockBreaches).toHaveLength(1)
    expect(stockBreaches[0].instrument_id).toBe('HDFCBANK')
    expect(stockBreaches[0].actual).toBe(7)
    expect(stockBreaches[0].limit).toBe(5)
  })

  it('no breach when holding weight exactly equals max_per_stock_pct (strict check)', () => {
    const holdings: ComplianceHolding[] = [
      makeHolding({ instrument_id: 'HDFCBANK', weight_pct: 5, sector: 'Banks' }),
    ]
    const breaches = checkCompliance(holdings, BASE_POLICY)
    expect(breaches.filter((b) => b.rule === 'max_per_stock')).toHaveLength(0)
  })

  it('returns multiple stock breaches when multiple holdings exceed cap', () => {
    const holdings: ComplianceHolding[] = [
      makeHolding({ instrument_id: 'A', weight_pct: 6, sector: 'IT' }),
      makeHolding({ instrument_id: 'B', weight_pct: 8, sector: 'IT' }),
      makeHolding({ instrument_id: 'C', weight_pct: 4, sector: 'IT' }),
    ]
    const breaches = checkCompliance(holdings, { ...BASE_POLICY, max_per_sector_pct: 100 })
    expect(breaches.filter((b) => b.rule === 'max_per_stock')).toHaveLength(2)
  })
})

// ---------------------------------------------------------------------------
// Rule 2: max_per_sector
// ---------------------------------------------------------------------------

describe('checkCompliance — max_per_sector', () => {
  it('breaches when sector sum strictly exceeds max_per_sector_pct', () => {
    // IT sector: 8 + 9 = 17 > 15
    const holdings: ComplianceHolding[] = [
      makeHolding({ instrument_id: 'INFY', weight_pct: 8, sector: 'IT' }),
      makeHolding({ instrument_id: 'TCS', weight_pct: 9, sector: 'IT' }),
      makeHolding({ instrument_id: 'HDFCBANK', weight_pct: 4, sector: 'Banks' }),
    ]
    const policy = { ...BASE_POLICY, max_per_stock_pct: 10 } // avoid stock breach noise
    const breaches = checkCompliance(holdings, policy)
    const sectorBreaches = breaches.filter((b) => b.rule === 'max_per_sector')
    expect(sectorBreaches).toHaveLength(1)
    expect(sectorBreaches[0].sector).toBe('IT')
    expect(sectorBreaches[0].actual).toBe(17)
  })

  it('no breach when sector sum exactly equals max_per_sector_pct', () => {
    const holdings: ComplianceHolding[] = [
      makeHolding({ instrument_id: 'INFY', weight_pct: 8, sector: 'IT' }),
      makeHolding({ instrument_id: 'TCS', weight_pct: 7, sector: 'IT' }),
    ]
    const policy = { ...BASE_POLICY, max_per_stock_pct: 10 }
    const breaches = checkCompliance(holdings, policy)
    expect(breaches.filter((b) => b.rule === 'max_per_sector')).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Rule 3: max_small_cap
// ---------------------------------------------------------------------------

describe('checkCompliance — max_small_cap', () => {
  it('breaches when small-cap sum strictly exceeds max_small_cap_pct', () => {
    // 10 + 12 + 12 = 34 > 30
    const holdings: ComplianceHolding[] = [
      makeHolding({ instrument_id: 'SC1', weight_pct: 10, is_small_cap: true, sector: 'IT' }),
      makeHolding({ instrument_id: 'SC2', weight_pct: 12, is_small_cap: true, sector: 'IT' }),
      makeHolding({ instrument_id: 'SC3', weight_pct: 12, is_small_cap: true, sector: 'Pharma' }),
      makeHolding({ instrument_id: 'LC1', weight_pct: 4, is_small_cap: false, sector: 'Banks' }),
    ]
    const policy = { ...BASE_POLICY, max_per_stock_pct: 15, max_per_sector_pct: 50 }
    const breaches = checkCompliance(holdings, policy)
    const scBreaches = breaches.filter((b) => b.rule === 'max_small_cap')
    expect(scBreaches).toHaveLength(1)
    expect(scBreaches[0].actual).toBe(34)
  })

  it('no breach when small-cap sum exactly equals max_small_cap_pct', () => {
    const holdings: ComplianceHolding[] = [
      makeHolding({ instrument_id: 'SC1', weight_pct: 30, is_small_cap: true, sector: 'IT' }),
    ]
    const policy = { ...BASE_POLICY, max_per_stock_pct: 35, max_per_sector_pct: 100 }
    const breaches = checkCompliance(holdings, policy)
    expect(breaches.filter((b) => b.rule === 'max_small_cap')).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Rule 4: min_holdings
// ---------------------------------------------------------------------------

describe('checkCompliance — min_holdings', () => {
  it('breaches when holding count is strictly below min_holdings', () => {
    // 3 holdings vs min 5 → breach
    const holdings: ComplianceHolding[] = [
      makeHolding({ instrument_id: 'A', weight_pct: 10, sector: 'IT' }),
      makeHolding({ instrument_id: 'B', weight_pct: 10, sector: 'Banks' }),
      makeHolding({ instrument_id: 'C', weight_pct: 10, sector: 'Pharma' }),
    ]
    const policy = { ...BASE_POLICY, max_per_stock_pct: 15, max_per_sector_pct: 100, min_holdings: 5 }
    const breaches = checkCompliance(holdings, policy)
    const mhBreaches = breaches.filter((b) => b.rule === 'min_holdings')
    expect(mhBreaches).toHaveLength(1)
    expect(mhBreaches[0].actual).toBe(3)
    expect(mhBreaches[0].limit).toBe(5)
  })

  it('no breach when holding count exactly equals min_holdings', () => {
    const holdings = Array.from({ length: 5 }, (_, i) =>
      makeHolding({ instrument_id: `stock-${i}`, weight_pct: 4, sector: `Sector${i}` }),
    )
    const breaches = checkCompliance(holdings, BASE_POLICY)
    expect(breaches.filter((b) => b.rule === 'min_holdings')).toHaveLength(0)
  })

  it('Python parity: 12 holdings vs min_holdings 15 → one breach (task spec case)', () => {
    const holdings = Array.from({ length: 12 }, (_, i) =>
      makeHolding({ instrument_id: `stock-${i}`, weight_pct: 3, sector: `Sector${i % 4}` }),
    )
    const policy = { ...BASE_POLICY, min_holdings: 15, max_per_stock_pct: 10, max_per_sector_pct: 30 }
    const breaches = checkCompliance(holdings, policy)
    const mhBreaches = breaches.filter((b) => b.rule === 'min_holdings')
    expect(mhBreaches).toHaveLength(1)
  })
})

// ---------------------------------------------------------------------------
// Rule 5: max_positions
// ---------------------------------------------------------------------------

describe('checkCompliance — max_positions', () => {
  it('breaches when holding count strictly exceeds max_positions', () => {
    const holdings = Array.from({ length: 6 }, (_, i) =>
      makeHolding({ instrument_id: `stock-${i}`, weight_pct: 2, sector: `Sector${i}` }),
    )
    const policy = { ...BASE_POLICY, max_positions: 5, min_holdings: 1 }
    const breaches = checkCompliance(holdings, policy)
    const mpBreaches = breaches.filter((b) => b.rule === 'max_positions')
    expect(mpBreaches).toHaveLength(1)
    expect(mpBreaches[0].actual).toBe(6)
    expect(mpBreaches[0].limit).toBe(5)
  })

  it('no breach when count exactly equals max_positions', () => {
    const holdings = Array.from({ length: 5 }, (_, i) =>
      makeHolding({ instrument_id: `stock-${i}`, weight_pct: 2, sector: `Sector${i}` }),
    )
    const policy = { ...BASE_POLICY, max_positions: 5, min_holdings: 1 }
    const breaches = checkCompliance(holdings, policy)
    expect(breaches.filter((b) => b.rule === 'max_positions')).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Rule 6: cash_floor
// ---------------------------------------------------------------------------

describe('checkCompliance — cash_floor', () => {
  it('breaches when residual cash is strictly below cash_floor_pct', () => {
    // sum weights = 97, cash = 3, floor = 5 → breach (3 < 5)
    const holdings = Array.from({ length: 10 }, (_, i) =>
      makeHolding({ instrument_id: `stock-${i}`, weight_pct: 9.7, sector: `Sector${i}` }),
    )
    const policy = {
      ...BASE_POLICY,
      max_per_stock_pct: 15,
      max_per_sector_pct: 100,
      min_holdings: 1,
      cash_floor_pct: 5,
    }
    const breaches = checkCompliance(holdings, policy)
    const cfBreaches = breaches.filter((b) => b.rule === 'cash_floor')
    expect(cfBreaches).toHaveLength(1)
    // cash = 100 - 97 = 3, below floor 5
    expect(cfBreaches[0].actual).toBeCloseTo(3, 5)
  })

  it('no breach when residual cash exactly equals cash_floor_pct', () => {
    // sum weights = 95, cash = 5, floor = 5 → no breach (5 == 5, strict less-than)
    const holdings = Array.from({ length: 5 }, (_, i) =>
      makeHolding({ instrument_id: `stock-${i}`, weight_pct: 19, sector: `Sector${i}` }),
    )
    const policy = {
      ...BASE_POLICY,
      max_per_stock_pct: 20,
      max_per_sector_pct: 100,
      min_holdings: 1,
      cash_floor_pct: 5,
    }
    const breaches = checkCompliance(holdings, policy)
    expect(breaches.filter((b) => b.rule === 'cash_floor')).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Fully compliant book → empty list
// ---------------------------------------------------------------------------

describe('checkCompliance — fully compliant book', () => {
  it('returns [] for a portfolio that satisfies all 6 rules', () => {
    // 8 holdings, all unique sectors, no small-cap, sum=80 (cash=20 > floor 5)
    const holdings: ComplianceHolding[] = [
      makeHolding({ instrument_id: 'A', weight_pct: 4, sector: 'Banks', is_small_cap: false }),
      makeHolding({ instrument_id: 'B', weight_pct: 4, sector: 'IT', is_small_cap: false }),
      makeHolding({ instrument_id: 'C', weight_pct: 4, sector: 'Pharma', is_small_cap: false }),
      makeHolding({ instrument_id: 'D', weight_pct: 4, sector: 'Auto', is_small_cap: false }),
      makeHolding({ instrument_id: 'E', weight_pct: 4, sector: 'FMCG', is_small_cap: false }),
      makeHolding({ instrument_id: 'F', weight_pct: 4, sector: 'Metals', is_small_cap: false }),
      makeHolding({ instrument_id: 'G', weight_pct: 4, sector: 'Energy', is_small_cap: false }),
      makeHolding({ instrument_id: 'H', weight_pct: 4, sector: 'Telecom', is_small_cap: false }),
    ]
    // 8 holdings, min=5 ✓, max=30 ✓
    // max_per_stock = 4 ≤ 5 ✓
    // max_per_sector = 4 ≤ 15 ✓ (each sector has only 1 stock)
    // small_cap = 0 ≤ 30 ✓
    // cash = 100 - 32 = 68 ≥ 5 ✓
    expect(checkCompliance(holdings, BASE_POLICY)).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// null policy fields → skip that rule
// ---------------------------------------------------------------------------

describe('checkCompliance — null policy fields skip the rule', () => {
  it('skips max_per_stock rule when policy.max_per_stock_pct is null', () => {
    const holdings: ComplianceHolding[] = [
      makeHolding({ instrument_id: 'A', weight_pct: 99, sector: 'IT' }),
    ]
    const policy: CompliancePolicy = {
      max_per_stock_pct: null,
      max_per_sector_pct: null,
      max_small_cap_pct: null,
      min_holdings: null,
      max_positions: null,
      cash_floor_pct: null,
    }
    expect(checkCompliance(holdings, policy)).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// Breach shape
// ---------------------------------------------------------------------------

describe('checkCompliance — breach shape', () => {
  it('max_per_stock breach has rule, message, actual, limit, instrument_id fields', () => {
    const holdings: ComplianceHolding[] = [
      makeHolding({ instrument_id: 'TATAMOTORS', weight_pct: 8, sector: 'Auto' }),
      makeHolding({ instrument_id: 'B', weight_pct: 3, sector: 'Banks' }),
      makeHolding({ instrument_id: 'C', weight_pct: 3, sector: 'IT' }),
      makeHolding({ instrument_id: 'D', weight_pct: 3, sector: 'Pharma' }),
      makeHolding({ instrument_id: 'E', weight_pct: 3, sector: 'FMCG' }),
    ]
    const breaches = checkCompliance(holdings, BASE_POLICY)
    const breach = breaches.find((b) => b.rule === 'max_per_stock')!
    expect(breach).toBeDefined()
    expect(typeof breach.message).toBe('string')
    expect(breach.message.length).toBeGreaterThan(0)
    expect(breach.actual).toBe(8)
    expect(breach.limit).toBe(5)
    expect(breach.instrument_id).toBe('TATAMOTORS')
  })

  it('max_per_sector breach has sector field', () => {
    const holdings: ComplianceHolding[] = [
      makeHolding({ instrument_id: 'INFY', weight_pct: 8, sector: 'IT' }),
      makeHolding({ instrument_id: 'TCS', weight_pct: 9, sector: 'IT' }),
      makeHolding({ instrument_id: 'B', weight_pct: 3, sector: 'Banks' }),
      makeHolding({ instrument_id: 'C', weight_pct: 3, sector: 'Pharma' }),
      makeHolding({ instrument_id: 'D', weight_pct: 3, sector: 'Auto' }),
    ]
    const policy = { ...BASE_POLICY, max_per_stock_pct: 10 }
    const breaches = checkCompliance(holdings, policy)
    const breach = breaches.find((b) => b.rule === 'max_per_sector')!
    expect(breach).toBeDefined()
    expect(breach.sector).toBe('IT')
    expect(breach.actual).toBe(17)
  })
})
