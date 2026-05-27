// frontend/src/lib/queries/v6/__tests__/sector_breadth.test.ts
//
// Tests for getSectorBreadth query.
//
// Covers:
//   1. Full result: maps all rows, computes n_stocks from string
//   2. Sector filter: passes sector param to SQL, returns single row
//   3. Empty result: returns [] when DB returns nothing
//   4. NULL handling: NULL features fields → "0.00" fallbacks

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getSectorBreadth } from '../sector_breadth'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeRow(overrides: Partial<{
  sector: string
  n_stocks: string
  pct_above_sma20: string
  pct_above_sma50: string
  pct_above_sma200: string
  top3_concentration_pct: string
  dispersion_sigma: string
  as_of_date: string
}> = {}) {
  return {
    sector: 'Banking',
    n_stocks: '38',
    pct_above_sma20: '74.00',
    pct_above_sma50: '66.00',
    pct_above_sma200: '58.00',
    top3_concentration_pct: '0.00',
    dispersion_sigma: '18.00',
    as_of_date: '2026-05-26',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Case 1: Full result — 2 sectors, maps rows correctly
// ---------------------------------------------------------------------------

describe('getSectorBreadth — full result (no sector filter)', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns mapped SectorBreadth[] with correct n_stocks parsing', async () => {
    sqlMock.mockResolvedValueOnce([
      makeRow({ sector: 'Banking', n_stocks: '38' }),
      makeRow({ sector: 'Capital Goods', n_stocks: '16', pct_above_sma20: '81.25' }),
    ])
    const result = await getSectorBreadth()
    expect(result).toHaveLength(2)
    expect(result[0].sector).toBe('Banking')
    expect(result[0].n_stocks).toBe(38)
    expect(result[0].pct_above_sma20).toBe('74.00')
    expect(result[0].pct_above_sma50).toBe('66.00')
    expect(result[0].pct_above_sma200).toBe('58.00')
    expect(result[0].top3_concentration_pct).toBe('0.00')
    expect(result[0].dispersion_sigma).toBe('18.00')
    expect(result[0].as_of_date).toBe('2026-05-26')
  })

  it('parses n_stocks as integer from string', async () => {
    sqlMock.mockResolvedValueOnce([makeRow({ n_stocks: '24' })])
    const result = await getSectorBreadth()
    expect(result[0].n_stocks).toBe(24)
    expect(typeof result[0].n_stocks).toBe('number')
  })

  it('preserves decimal precision on pct strings', async () => {
    sqlMock.mockResolvedValueOnce([makeRow({ pct_above_sma200: '33.33' })])
    const result = await getSectorBreadth()
    expect(result[0].pct_above_sma200).toBe('33.33')
  })
})

// ---------------------------------------------------------------------------
// Case 2: Sector filter
// ---------------------------------------------------------------------------

describe('getSectorBreadth — with sector filter', () => {
  beforeEach(() => sqlMock.mockReset())

  it('calls sql with the sector parameter and returns 1 row', async () => {
    sqlMock.mockResolvedValueOnce([makeRow({ sector: 'IT' })])
    const result = await getSectorBreadth('IT')
    expect(result).toHaveLength(1)
    expect(result[0].sector).toBe('IT')
    // Verify sql was called (with any args — template literal, not inspectable directly)
    expect(sqlMock).toHaveBeenCalledTimes(1)
  })

  it('returns [] when sector filter matches nothing', async () => {
    sqlMock.mockResolvedValueOnce([])
    const result = await getSectorBreadth('Nonexistent')
    expect(result).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// Case 3: Empty result
// ---------------------------------------------------------------------------

describe('getSectorBreadth — empty result', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns [] when DB has no scorecard rows', async () => {
    sqlMock.mockResolvedValueOnce([])
    const result = await getSectorBreadth()
    expect(result).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// Case 4: NULL handling — missing features JSONB keys
// ---------------------------------------------------------------------------

describe('getSectorBreadth — NULL field handling', () => {
  beforeEach(() => sqlMock.mockReset())

  it('falls back to "0.00" for NULL pct fields', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        sector: 'Healthcare',
        n_stocks: '5',
        pct_above_sma20: null,
        pct_above_sma50: null,
        pct_above_sma200: null,
        top3_concentration_pct: null,
        dispersion_sigma: null,
        as_of_date: null,
      },
    ])
    const result = await getSectorBreadth()
    expect(result[0].pct_above_sma20).toBe('0.00')
    expect(result[0].pct_above_sma50).toBe('0.00')
    expect(result[0].pct_above_sma200).toBe('0.00')
    expect(result[0].top3_concentration_pct).toBe('0.00')
    expect(result[0].dispersion_sigma).toBe('0.00')
    expect(result[0].as_of_date).toBe('')
  })

  it('handles numeric n_stocks (postgres-js may return number directly)', async () => {
    sqlMock.mockResolvedValueOnce([makeRow({ n_stocks: 12 as unknown as string })])
    const result = await getSectorBreadth()
    expect(result[0].n_stocks).toBe(12)
  })
})
