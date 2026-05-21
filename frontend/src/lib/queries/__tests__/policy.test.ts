// Tests for resolveField in src/lib/queries/policy.ts
//
// resolveField is the pure merge function that matches the backend
// atlas/intelligence/policy/policy.py _merge semantics:
//   SQL NULL  (JS null/undefined)  → source: 'inherited'
//   any non-null value incl. []   → source: 'overridden'
//
// These tests specifically guard against the empty-array regression where
// buy_states = [] (a "buy nothing" mandate) was previously misreported as
// 'inherited', silently falling back to the house default.

import { describe, it, expect, vi } from 'vitest'

// Stub the DB module — resolveField is a pure function with no DB dependency.
// We mock @/lib/db so the module can be imported without a live Postgres connection.
vi.mock('@/lib/db', () => ({ default: vi.fn() }))

import { resolveField } from '../policy'

// ---------------------------------------------------------------------------
// Basic scalar cases
// ---------------------------------------------------------------------------

describe('resolveField — scalar fields', () => {
  it('returns overridden when override is a non-null string', () => {
    const result = resolveField('5', '10')
    expect(result).toEqual({ value: '10', source: 'overridden' })
  })

  it('returns inherited when override is null (SQL NULL)', () => {
    const result = resolveField('5', null)
    expect(result).toEqual({ value: '5', source: 'inherited' })
  })

  it('returns inherited when override is undefined (absent field)', () => {
    const result = resolveField('5', undefined as unknown as null)
    expect(result).toEqual({ value: '5', source: 'inherited' })
  })

  it('returns overridden when override is boolean true', () => {
    const result = resolveField(false, true)
    expect(result).toEqual({ value: true, source: 'overridden' })
  })

  it('returns overridden when override is boolean false', () => {
    // false is non-null so it IS an explicit override
    const result = resolveField(true, false)
    expect(result).toEqual({ value: false, source: 'overridden' })
  })

  it('house value is null and override is a string → overridden', () => {
    const result = resolveField(null, 'weekly')
    expect(result).toEqual({ value: 'weekly', source: 'overridden' })
  })

  it('both null → inherited with null value', () => {
    const result = resolveField(null, null)
    expect(result).toEqual({ value: null, source: 'inherited' })
  })
})

// ---------------------------------------------------------------------------
// Array field — the key regression cases
// ---------------------------------------------------------------------------

describe('resolveField — array fields (buy_states)', () => {
  it('non-empty override array → overridden (value is the override array)', () => {
    // Portfolio explicitly sets buy_states to specific stages
    const result = resolveField(['stage_2a', 'stage_2b'], ['stage_2a', 'stage_2b', 'stage_2c'])
    expect(result).toEqual({
      value: ['stage_2a', 'stage_2b', 'stage_2c'],
      source: 'overridden',
    })
  })

  it('empty override array [] → overridden with value [] (buy-nothing mandate)', () => {
    // This is the regression case: a portfolio that overrides buy_states to []
    // means "buy nothing". The DB returns [] (not NULL). Must be 'overridden'.
    const result = resolveField(['stage_2a', 'stage_2b'], [])
    expect(result).toEqual({ value: [], source: 'overridden' })
  })

  it('null override for array field → inherited (SQL NULL means no override row set)', () => {
    // The DB returns SQL NULL as JS null — this means the portfolio has NOT
    // set a buy_states override; the house default should apply.
    const result = resolveField(['stage_2a', 'stage_2b'], null)
    expect(result).toEqual({ value: ['stage_2a', 'stage_2b'], source: 'inherited' })
  })

  it('empty house array + empty override array → overridden with []', () => {
    const result = resolveField([], [])
    expect(result).toEqual({ value: [], source: 'overridden' })
  })

  it('null house + empty override array → overridden with []', () => {
    const result = resolveField(null, [])
    expect(result).toEqual({ value: [], source: 'overridden' })
  })

  it('null house + null override → inherited with null', () => {
    const result = resolveField(null, null)
    expect(result).toEqual({ value: null, source: 'inherited' })
  })
})

// ---------------------------------------------------------------------------
// Backend parity confirmation
// ---------------------------------------------------------------------------

describe('resolveField — backend _merge parity', () => {
  it('the rule is: non-NULL = overridden, NULL = inherited — no other conditions', () => {
    // Exhaustive check: [] is non-null in JS, so it is overridden.
    // Only null/undefined is inherited.
    const cases: Array<[unknown, string]> = [
      [[], 'overridden'],
      [['x'], 'overridden'],
      ['', 'overridden'],
      ['0', 'overridden'],
      [false, 'overridden'],
      [true, 'overridden'],
      [null, 'inherited'],
    ]
    for (const [overrideVal, expectedSource] of cases) {
      const result = resolveField('house', overrideVal as Parameters<typeof resolveField>[1])
      expect(result.source, `overrideVal=${JSON.stringify(overrideVal)}`).toBe(expectedSource)
    }
  })
})
