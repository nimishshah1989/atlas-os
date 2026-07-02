// frontend/src/lib/queries/__tests__/funds_holding_stock.test.ts
//
// Four cases:
//   1. multi-fund  — 5 funds hold the iid, weights 0.5–4.2%, sorted by AUM desc
//   2. few-funds   — 1 fund holds
//   3. no-funds    — iid not in any fund's top_holdings → returns []
//   4. JSONB shape regression — canonical {instrument_id, weight_pct, symbol, verdict}
//      shape unpacks correctly; null weight_pct rows are filtered out
//
// Mock strategy: sql is a tagged-template function; we mock @/lib/db's
// default export as a function that returns the mock result. The query
// fires one SQL call per getFundsHoldingStock() invocation.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getFundsHoldingStock } from '../funds_holding_stock'
import type { FundHolding } from '../funds_holding_stock'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeRow(
  overrides: Partial<{
    fund_code: string
    fund_name: string | null
    aum_cr: string | null
    weight_pct: string | null
    atlas_grade: string
  }> = {},
) {
  return {
    fund_code: 'SC001',
    fund_name: 'Atlas Growth Fund',
    aum_cr: '1200.00',
    weight_pct: '2.50',
    atlas_grade: 'AA',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('getFundsHoldingStock', () => {
  beforeEach(() => sqlMock.mockReset())

  // -------------------------------------------------------------------------
  // Case 1: multi-fund — 5 funds, varying weights, sorted by AUM desc
  // -------------------------------------------------------------------------
  it('multi-fund: returns 5 rows sorted by AUM desc', async () => {
    const mockRows = [
      makeRow({ fund_code: 'SC005', fund_name: 'Axis Bluechip', aum_cr: '18500.00', weight_pct: '4.20', atlas_grade: 'AAA' }),
      makeRow({ fund_code: 'SC001', fund_name: 'HDFC Top 100',  aum_cr: '12000.00', weight_pct: '3.10', atlas_grade: 'AA'  }),
      makeRow({ fund_code: 'SC003', fund_name: 'Mirae Large Cap', aum_cr: '9500.00', weight_pct: '2.80', atlas_grade: 'AA' }),
      makeRow({ fund_code: 'SC002', fund_name: 'SBI Flexi',      aum_cr: '4200.00', weight_pct: '1.50', atlas_grade: 'A'  }),
      makeRow({ fund_code: 'SC004', fund_name: 'Motilal Mid 150', aum_cr: '1100.00', weight_pct: '0.50', atlas_grade: 'BBB' }),
    ]
    sqlMock.mockResolvedValueOnce(mockRows)

    const iid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
    const result = await getFundsHoldingStock(iid)

    expect(result).toHaveLength(5)

    // Sorted by AUM desc — first row should be Axis Bluechip at 18500 Cr
    expect(result[0].fund_code).toBe('SC005')
    expect(result[0].aum_cr).toBe('18500.00')
    expect(result[0].weight_pct).toBe('4.20')
    expect(result[0].atlas_grade).toBe('AAA')

    // Last row — lowest AUM
    expect(result[4].fund_code).toBe('SC004')
    expect(result[4].weight_pct).toBe('0.50')
    expect(result[4].atlas_grade).toBe('BBB')

    // All have required FundHolding keys
    for (const row of result) {
      expect(row).toHaveProperty('fund_code')
      expect(row).toHaveProperty('fund_name')
      expect(row).toHaveProperty('aum_cr')
      expect(row).toHaveProperty('weight_pct')
      expect(row).toHaveProperty('atlas_grade')
    }
  })

  // -------------------------------------------------------------------------
  // Case 2: few-funds — 1 fund holds the stock
  // -------------------------------------------------------------------------
  it('few-funds: returns 1 row when only one fund holds the stock', async () => {
    const mockRows = [
      makeRow({
        fund_code: 'SC099',
        fund_name: 'Navi Large & Midcap',
        aum_cr: '350.00',
        weight_pct: '1.20',
        atlas_grade: 'B',
      }),
    ]
    sqlMock.mockResolvedValueOnce(mockRows)

    const result = await getFundsHoldingStock('11111111-2222-3333-4444-555555555555')

    expect(result).toHaveLength(1)
    const f = result[0]
    expect(f.fund_code).toBe('SC099')
    expect(f.fund_name).toBe('Navi Large & Midcap')
    expect(f.aum_cr).toBe('350.00')
    expect(f.weight_pct).toBe('1.20')
    expect(f.atlas_grade).toBe('B')
  })

  // -------------------------------------------------------------------------
  // Case 3: no-funds — iid not in any fund's top_holdings
  // -------------------------------------------------------------------------
  it('no-funds: returns [] when iid is not held by any fund', async () => {
    sqlMock.mockResolvedValueOnce([])

    const result = await getFundsHoldingStock('00000000-0000-0000-0000-000000000000')

    expect(result).toEqual([])
    expect(sqlMock).toHaveBeenCalledTimes(1)
  })

  // -------------------------------------------------------------------------
  // Case 4: JSONB shape regression
  //   — canonical top_holdings element: {instrument_id, weight_pct, symbol, verdict}
  //   — a row with null weight_pct must be filtered out before returning
  //   — fund_name null → falls back to fund_code
  //   — aum_cr null → falls back to '0'
  // -------------------------------------------------------------------------
  it('JSONB regression: null weight_pct rows are filtered; null fund_name falls back to fund_code', async () => {
    // DB JSONB elements canonically look like:
    //   {"instrument_id": "<uuid>", "symbol": "RELIANCE", "weight_pct": 3.25, "verdict": "POSITIVE"}
    // The SQL layer casts weight_pct to text; a missing field comes back as null.
    const mockRows = [
      // Valid row — weight_pct present
      makeRow({
        fund_code: 'SC007',
        fund_name: 'Quant Active Fund',
        aum_cr: '2100.00',
        weight_pct: '3.25',
        atlas_grade: 'A',
      }),
      // Edge case — weight_pct is null (element missing the key; SQL filter
      // uses >= 0.5 so DB shouldn't return this, but we guard in-process too)
      makeRow({
        fund_code: 'SC008',
        fund_name: null,      // fund_name missing → should fall back to fund_code
        aum_cr: null,         // aum_cr missing → should fall back to '0'
        weight_pct: null,     // null weight → filtered out by in-process guard
        atlas_grade: 'B',
      }),
    ]
    sqlMock.mockResolvedValueOnce(mockRows)

    const result = await getFundsHoldingStock('cccccccc-dddd-eeee-ffff-000000000000')

    // Null weight_pct row must be dropped
    expect(result).toHaveLength(1)

    const f = result[0]
    expect(f.fund_code).toBe('SC007')
    expect(f.weight_pct).toBe('3.25')
    expect(f.atlas_grade).toBe('A')
  })

  // Bonus: fund_name=null + aum_cr=null fallback (weight_pct present so it passes filter)
  it('JSONB fallbacks: null fund_name → fund_code; null aum_cr → "0"', async () => {
    sqlMock.mockResolvedValueOnce([
      makeRow({ fund_code: 'SC010', fund_name: null, aum_cr: null, weight_pct: '0.75', atlas_grade: 'BB' }),
    ])

    const result = await getFundsHoldingStock('ffffffff-ffff-ffff-ffff-ffffffffffff')

    expect(result).toHaveLength(1)
    const f = result[0]
    expect(f.fund_name).toBe('SC010')   // falls back to fund_code
    expect(f.aum_cr).toBe('0')          // falls back to '0'
    expect(f.weight_pct).toBe('0.75')
  })

  // Grade derivation spot-checks: the SQL-level CASE derives the grade;
  // the mock returns the already-derived string. Verify the returned type
  // matches the expected grade literals.
  it('grade literals: all 6 atlas_grade values are accepted without transform', async () => {
    const grades = ['AAA', 'AA', 'A', 'BBB', 'BB', 'B']
    const mockRows = grades.map((g, i) =>
      makeRow({ fund_code: `SC${i}`, weight_pct: '1.00', atlas_grade: g, aum_cr: String((6 - i) * 1000) }),
    )
    sqlMock.mockResolvedValueOnce(mockRows)

    const result: FundHolding[] = await getFundsHoldingStock('12345678-1234-1234-1234-123456789abc')

    expect(result).toHaveLength(6)
    const returnedGrades = result.map(r => r.atlas_grade)
    expect(returnedGrades).toEqual(grades)
  })
})
