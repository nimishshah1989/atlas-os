// frontend/src/lib/queries/v6/__tests__/sector_book_exposure.test.ts
//
// 4 test cases for sector_book_exposure.ts:
//   1. Overweight: book has 10% Banking, benchmark has 6% → delta_pp ≈ "+4.00"
//   2. Underweight: book has 0% Pharma, benchmark has 8% → delta_pp = "-8.00"
//   3. No-holding (empty book): returns sectors all with book_weight="0.00"
//   4. Single-sector filter: getSectorBookExposure("Banking") returns 1 row
//
// The sql tagged-template mock captures calls via a vi.fn(). Each test sets
// up the expected DB row shape and asserts the returned SectorBookExposure[]
// matches the public contract exactly.

import { describe, it, expect, vi, beforeEach } from 'vitest'

// Silence the server-only guard in test environment
vi.mock('server-only', () => ({}))

const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getSectorBookExposure } from '../sector_book_exposure'

// ---------------------------------------------------------------------------
// Helper: build a raw DB row as the sql driver would return it
// ---------------------------------------------------------------------------
function makeRow(
  sector_name: string,
  book_weight: string,
  benchmark_weight: string,
  delta_pp: string,
  holding_count: number,
) {
  return { sector_name, book_weight, benchmark_weight, delta_pp, holding_count }
}

describe('getSectorBookExposure', () => {
  beforeEach(() => sqlMock.mockReset())

  // -------------------------------------------------------------------------
  // Case 1: Overweight sector
  //   book has 10% Banking, benchmark has 6% → delta_pp = "+4.00"
  // -------------------------------------------------------------------------
  it('returns delta_pp=+4.00 when book holds 10% Banking and benchmark is 6%', async () => {
    // The SQL ROUND() + FULL OUTER JOIN returns the computed row directly.
    // The mock simulates the DB response after the CTE arithmetic runs.
    sqlMock.mockResolvedValueOnce([
      makeRow('Banking', '10.00', '6.00', '4.00', 5),
      makeRow('IT', '5.00', '12.00', '-7.00', 2),
    ])

    const result = await getSectorBookExposure()

    expect(result).toHaveLength(2)

    const banking = result.find((r) => r.sector_name === 'Banking')
    expect(banking).toBeDefined()
    expect(banking!.book_weight).toBe('10.00')
    expect(banking!.benchmark_weight).toBe('6.00')
    // delta_pp is a signed string; positive means overweight
    expect(banking!.delta_pp).toBe('4.00')
    expect(banking!.holding_count).toBe(5)
  })

  // -------------------------------------------------------------------------
  // Case 2: Underweight sector
  //   book has 0% Pharma, benchmark has 8% → delta_pp = "-8.00"
  // -------------------------------------------------------------------------
  it('returns delta_pp=-8.00 when book holds 0% Pharma and benchmark is 8%', async () => {
    sqlMock.mockResolvedValueOnce([
      makeRow('Pharma', '0.00', '8.00', '-8.00', 0),
    ])

    const result = await getSectorBookExposure()

    expect(result).toHaveLength(1)

    const pharma = result[0]
    expect(pharma.sector_name).toBe('Pharma')
    expect(pharma.book_weight).toBe('0.00')
    expect(pharma.benchmark_weight).toBe('8.00')
    expect(pharma.delta_pp).toBe('-8.00')
    // holding_count must be 0 when nothing is held in this sector
    expect(pharma.holding_count).toBe(0)
  })

  // -------------------------------------------------------------------------
  // Case 3: Empty book (v6.0 launch state)
  //   portfolio is empty → all 30 benchmark sectors returned with
  //   book_weight="0.00" and delta_pp = "-<bench_weight>"
  // -------------------------------------------------------------------------
  it('returns all benchmark sectors with book_weight="0.00" when the book is empty', async () => {
    // Simulate 3 sectors (representative of the 30-sector universe)
    const emptyBookRows = [
      makeRow('Banking', '0.00', '18.50', '-18.50', 0),
      makeRow('IT', '0.00', '14.20', '-14.20', 0),
      makeRow('Pharma', '0.00', '8.00', '-8.00', 0),
    ]
    sqlMock.mockResolvedValueOnce(emptyBookRows)

    const result = await getSectorBookExposure()

    expect(result.length).toBe(3)
    for (const row of result) {
      expect(row.book_weight).toBe('0.00')
      expect(row.holding_count).toBe(0)
      // Every delta_pp must be negative (we are underweight everywhere)
      const delta = parseFloat(row.delta_pp)
      expect(delta).toBeLessThanOrEqual(0)
    }
  })

  // -------------------------------------------------------------------------
  // Case 4: Single-sector filter
  //   getSectorBookExposure("Banking") returns exactly 1 row for Banking
  // -------------------------------------------------------------------------
  it('returns exactly 1 row when sector_name filter is provided', async () => {
    sqlMock.mockResolvedValueOnce([
      makeRow('Banking', '10.00', '6.00', '4.00', 5),
    ])

    const result = await getSectorBookExposure('Banking')

    expect(result).toHaveLength(1)
    expect(result[0].sector_name).toBe('Banking')
    expect(result[0].book_weight).toBe('10.00')
    expect(result[0].benchmark_weight).toBe('6.00')
    expect(result[0].delta_pp).toBe('4.00')
    expect(result[0].holding_count).toBe(5)
  })

  // -------------------------------------------------------------------------
  // Type contract: holding_count as string (Postgres may return bigint as str)
  // -------------------------------------------------------------------------
  it('coerces string holding_count from Postgres to number', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        sector_name: 'Auto',
        book_weight: '5.00',
        benchmark_weight: '7.00',
        delta_pp: '-2.00',
        holding_count: '3',  // Postgres bigint may come back as string
      },
    ])

    const result = await getSectorBookExposure()

    expect(result[0].holding_count).toBe(3)
    expect(typeof result[0].holding_count).toBe('number')
  })
})
