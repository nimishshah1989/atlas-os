// frontend/src/lib/queries/v6/__tests__/industry_snapshot.test.ts
//
// 4 test cases for getIndustrySnapshot:
//   1. funds variant: returns IndustrySnapshot with non-empty leaderboard
//   2. etfs variant: returns ETF snapshot
//   3. No AMC data: leaderboard = []
//   4. Counts add up: n_atlas_leaders + n_avoid + neutrals <= n_total

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))

const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getIndustrySnapshot } from '../industry_snapshot'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const TOTALS_ROW = {
  n_total: '120',
  n_atlas_leaders: '18',
  n_avoid: '12',
  median_expense: '0.92',
  median_aum_cr: '2450.00',
}

const AMC_ROWS = [
  { amc: 'Mirae Asset', avg_composite: '72.50', n_funds: '8' },
  { amc: 'HDFC AMC', avg_composite: '69.10', n_funds: '12' },
  { amc: 'Axis AMC', avg_composite: '65.80', n_funds: '10' },
  { amc: 'SBI Funds', avg_composite: '63.20', n_funds: '15' },
  { amc: 'Kotak AMC', avg_composite: '60.50', n_funds: '9' },
]

// ---------------------------------------------------------------------------
// Test 1: funds variant returns IndustrySnapshot with non-empty leaderboard
// ---------------------------------------------------------------------------

describe('getIndustrySnapshot — funds variant', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns IndustrySnapshot with correct shape and non-empty leaderboard', async () => {
    // Two calls: totals query then AMC query
    sqlMock
      .mockResolvedValueOnce([TOTALS_ROW])
      .mockResolvedValueOnce(AMC_ROWS)

    const snap = await getIndustrySnapshot('funds')

    expect(snap.asset_class).toBe('funds')
    expect(snap.n_total).toBe(120)
    expect(snap.n_atlas_leaders).toBe(18)
    expect(snap.n_avoid).toBe(12)
    expect(snap.pct_above_benchmark_3y).toBeNull()
    expect(snap.median_expense).toBe('0.92')
    expect(snap.median_aum_cr).toBe('2450.00')

    // AMC leaderboard: 5 rows
    expect(snap.amc_leaderboard).toHaveLength(5)
    const first = snap.amc_leaderboard[0]
    expect(first.amc).toBe('Mirae Asset')
    expect(first.avg_composite).toBe('72.50')
    expect(first.n_funds).toBe(8)

    // All n_funds are numbers (not strings)
    for (const row of snap.amc_leaderboard) {
      expect(typeof row.n_funds).toBe('number')
      expect(typeof row.avg_composite).toBe('string')
    }
  })
})

// ---------------------------------------------------------------------------
// Test 2: ETFs variant returns ETF snapshot
// ---------------------------------------------------------------------------

describe('getIndustrySnapshot — etfs variant', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns ETF snapshot with asset_class=etfs', async () => {
    const ETF_TOTALS = {
      n_total: '45',
      n_atlas_leaders: '6',
      n_avoid: '3',
      median_expense: '0.15',
      median_aum_cr: '1200.00',
    }

    const ETF_AMC_ROWS = [
      { amc: 'Nippon India ETF', avg_composite: '68.00', n_funds: '5' },
      { amc: 'HDFC ETF', avg_composite: '65.50', n_funds: '4' },
    ]

    sqlMock
      .mockResolvedValueOnce([ETF_TOTALS])
      .mockResolvedValueOnce(ETF_AMC_ROWS)

    const snap = await getIndustrySnapshot('etfs')

    expect(snap.asset_class).toBe('etfs')
    expect(snap.n_total).toBe(45)
    expect(snap.n_atlas_leaders).toBe(6)
    expect(snap.n_avoid).toBe(3)
    expect(snap.median_expense).toBe('0.15')

    // ETFs also get AMC leaderboard per Vocabulary lock override
    expect(snap.amc_leaderboard).toHaveLength(2)
    expect(snap.amc_leaderboard[0].amc).toBe('Nippon India ETF')
  })
})

// ---------------------------------------------------------------------------
// Test 3: No AMC data — leaderboard = []
// ---------------------------------------------------------------------------

describe('getIndustrySnapshot — no AMC data', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns empty amc_leaderboard when no AMC rows returned', async () => {
    sqlMock
      .mockResolvedValueOnce([TOTALS_ROW])
      .mockResolvedValueOnce([])   // empty AMC result

    const snap = await getIndustrySnapshot('funds')

    expect(snap.amc_leaderboard).toEqual([])
    // Other fields still populated
    expect(snap.n_total).toBe(120)
  })

  it('returns empty leaderboard for ETFs when no AMC data', async () => {
    const ETF_TOTALS = {
      n_total: '10',
      n_atlas_leaders: '1',
      n_avoid: '1',
      median_expense: null,
      median_aum_cr: null,
    }

    sqlMock
      .mockResolvedValueOnce([ETF_TOTALS])
      .mockResolvedValueOnce([])

    const snap = await getIndustrySnapshot('etfs')
    expect(snap.amc_leaderboard).toEqual([])
    expect(snap.median_expense).toBeNull()
    expect(snap.median_aum_cr).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Test 4: Counts add up — n_atlas_leaders + n_avoid <= n_total
// ---------------------------------------------------------------------------

describe('getIndustrySnapshot — count invariant', () => {
  beforeEach(() => sqlMock.mockReset())

  it('n_atlas_leaders + n_avoid do not exceed n_total', async () => {
    sqlMock
      .mockResolvedValueOnce([TOTALS_ROW])
      .mockResolvedValueOnce(AMC_ROWS)

    const snap = await getIndustrySnapshot('funds')

    // leaders and avoids are subsets of the total population
    expect(snap.n_atlas_leaders + snap.n_avoid).toBeLessThanOrEqual(snap.n_total)

    // Implicit "neutrals" = n_total - n_atlas_leaders - n_avoid (may overlap)
    const neutrals = snap.n_total - snap.n_atlas_leaders - snap.n_avoid
    expect(neutrals).toBeGreaterThanOrEqual(0)
  })

  it('handles zero counts gracefully (new universe with no scored funds)', async () => {
    const EMPTY_TOTALS = {
      n_total: '0',
      n_atlas_leaders: '0',
      n_avoid: '0',
      median_expense: null,
      median_aum_cr: null,
    }

    sqlMock
      .mockResolvedValueOnce([EMPTY_TOTALS])
      .mockResolvedValueOnce([])

    const snap = await getIndustrySnapshot('funds')
    expect(snap.n_total).toBe(0)
    expect(snap.n_atlas_leaders).toBe(0)
    expect(snap.n_avoid).toBe(0)
    expect(snap.amc_leaderboard).toEqual([])
  })
})
