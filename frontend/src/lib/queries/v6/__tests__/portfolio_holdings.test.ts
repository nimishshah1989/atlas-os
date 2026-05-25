// frontend/src/lib/queries/v6/__tests__/portfolio_holdings.test.ts
//
// 4 test cases for portfolio_holdings.ts:
//   1. Multi-portfolio: 3 rows for same iid → portfolio_count=3, last_add_date matches MAX
//   2. Single-portfolio: 1 row → portfolio_count=1
//   3. No-holding (empty table): getHoldingState returns null
//   4. getHeldIidSet: returns correct Set when 5 distinct iids have open positions

import { describe, it, expect, vi, beforeEach } from 'vitest'

// Silence the server-only guard in test environment
vi.mock('server-only', () => ({}))

// React.cache pass-through: call the inner function directly (no memoization
// in tests — each test call gets a fresh invocation via the mock reset)
vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>()
  return {
    ...actual,
    cache: (fn: (...args: unknown[]) => unknown) => fn,
  }
})

const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getHoldingState, getHeldIidSet } from '../portfolio_holdings'

describe('getHoldingState', () => {
  beforeEach(() => sqlMock.mockReset())

  // -------------------------------------------------------------------------
  // Case 1: Multi-portfolio — 3 open rows for the same iid
  // -------------------------------------------------------------------------
  it('returns portfolio_count=3 and last_add_date=MAX when 3 open positions exist', async () => {
    // Postgres COUNT(*) + MAX: the aggregation is done in SQL so the mock
    // returns a single row with the pre-computed aggregate values.
    sqlMock.mockResolvedValueOnce([
      {
        portfolio_count: 3,
        last_add_date: '2026-05-20',
      },
    ])

    const result = await getHoldingState('iid-multi')

    expect(result).not.toBeNull()
    expect(result!.portfolio_count).toBe(3)
    expect(result!.last_add_date).toBe('2026-05-20')
    // weight_range and aggregate_weight are v6.0 placeholders
    expect(result!.weight_range).toEqual(['0.00', '0.00'])
    expect(result!.aggregate_weight).toBe('0.00')
  })

  // -------------------------------------------------------------------------
  // Case 2: Single-portfolio — exactly 1 open row
  // -------------------------------------------------------------------------
  it('returns portfolio_count=1 when exactly one open position exists', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        portfolio_count: 1,
        last_add_date: '2026-05-15',
      },
    ])

    const result = await getHoldingState('iid-single')

    expect(result).not.toBeNull()
    expect(result!.portfolio_count).toBe(1)
    expect(result!.last_add_date).toBe('2026-05-15')
    expect(result!.weight_range).toEqual(['0.00', '0.00'])
    expect(result!.aggregate_weight).toBe('0.00')
  })

  // -------------------------------------------------------------------------
  // Case 3: No-holding — empty table (v6.0 launch state)
  // -------------------------------------------------------------------------
  it('returns null when the instrument has no open positions (empty table)', async () => {
    // COUNT(*) on an empty set returns a single row with count=0.
    // MAX(entry_date) returns NULL. This is the v6.0 launch state.
    sqlMock.mockResolvedValueOnce([
      {
        portfolio_count: 0,
        last_add_date: null,
      },
    ])

    const result = await getHoldingState('iid-not-held')

    expect(result).toBeNull()
  })

  it('handles string portfolio_count from Postgres (COUNT returns text in some drivers)', async () => {
    // Some postgres-js configurations return COUNT as string; ensure parseInt
    // handles this correctly.
    sqlMock.mockResolvedValueOnce([
      {
        portfolio_count: '2',
        last_add_date: '2026-05-10',
      },
    ])

    const result = await getHoldingState('iid-string-count')

    expect(result).not.toBeNull()
    expect(result!.portfolio_count).toBe(2)
  })
})

describe('getHeldIidSet', () => {
  beforeEach(() => sqlMock.mockReset())

  // -------------------------------------------------------------------------
  // Case 4: Returns correct Set when 5 distinct iids have open positions
  // -------------------------------------------------------------------------
  it('returns a Set with all 5 distinct instrument_ids', async () => {
    const expectedIids = [
      'aaaa0000-0000-0000-0000-000000000001',
      'aaaa0000-0000-0000-0000-000000000002',
      'aaaa0000-0000-0000-0000-000000000003',
      'aaaa0000-0000-0000-0000-000000000004',
      'aaaa0000-0000-0000-0000-000000000005',
    ]

    sqlMock.mockResolvedValueOnce(
      expectedIids.map((iid) => ({ instrument_id: iid })),
    )

    const result = await getHeldIidSet()

    expect(result).toBeInstanceOf(Set)
    expect(result.size).toBe(5)
    for (const iid of expectedIids) {
      expect(result.has(iid)).toBe(true)
    }
  })

  it('returns an empty Set when the table has no open positions (empty-table launch state)', async () => {
    sqlMock.mockResolvedValueOnce([])

    const result = await getHeldIidSet()

    expect(result).toBeInstanceOf(Set)
    expect(result.size).toBe(0)
  })
})
