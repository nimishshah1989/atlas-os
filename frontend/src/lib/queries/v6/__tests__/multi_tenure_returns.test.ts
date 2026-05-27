// Tests for getMultiTenureReturns + getMultiTenureReturnsBatch.
//
// Four cases:
//   1. Single iid — full row with all 6 tenures populated
//   2. Single iid — null when no data exists
//   3. Batch of 5 iids — 5 rows returned
//   4. Batch with one invalid/missing iid — only valid rows in result

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import {
  getMultiTenureReturns,
  getMultiTenureReturnsBatch,
} from '../multi_tenure_returns'
import type { MultiTenureReturns } from '../multi_tenure_returns'

const FULL_ROW: MultiTenureReturns = {
  iid: 'aaa-111-uuid',
  date: '2026-05-22',
  ret_1d: '0.0142',
  ret_1w: '0.0315',
  ret_1m: '0.0823',
  ret_3m: '0.1240',
  ret_6m: '0.1891',
  ret_12m: '0.2750',
}

describe('getMultiTenureReturns', () => {
  beforeEach(() => sqlMock.mockReset())

  it('case 1 — returns full 6-tenure row for a known iid', async () => {
    sqlMock.mockResolvedValueOnce([FULL_ROW])

    const result = await getMultiTenureReturns('aaa-111-uuid')

    expect(result).not.toBeNull()
    expect(result!.iid).toBe('aaa-111-uuid')
    expect(result!.date).toBe('2026-05-22')
    // All 6 tenures present as stringified decimals
    expect(result!.ret_1d).toBe('0.0142')
    expect(result!.ret_1w).toBe('0.0315')
    expect(result!.ret_1m).toBe('0.0823')
    expect(result!.ret_3m).toBe('0.1240')
    expect(result!.ret_6m).toBe('0.1891')
    expect(result!.ret_12m).toBe('0.2750')
    // Values are strings, not numbers — Decimal transport guarantee
    expect(typeof result!.ret_1m).toBe('string')
    expect(typeof result!.ret_12m).toBe('string')
  })

  it('case 2 — returns null when no rows exist for the iid', async () => {
    sqlMock.mockResolvedValueOnce([])

    const result = await getMultiTenureReturns('zz-does-not-exist')

    expect(result).toBeNull()
  })

  it('preserves null cells for tenures with insufficient history', async () => {
    const partialRow: MultiTenureReturns = {
      iid: 'new-listing-uuid',
      date: '2026-05-22',
      ret_1d: '0.0050',
      ret_1w: null,
      ret_1m: null,
      ret_3m: null,
      ret_6m: null,
      ret_12m: null,
    }
    sqlMock.mockResolvedValueOnce([partialRow])

    const result = await getMultiTenureReturns('new-listing-uuid')

    expect(result).not.toBeNull()
    expect(result!.ret_1d).toBe('0.0050')
    expect(result!.ret_1w).toBeNull()
    expect(result!.ret_12m).toBeNull()
  })
})

describe('getMultiTenureReturnsBatch', () => {
  beforeEach(() => sqlMock.mockReset())

  it('case 3 — returns one row per iid for a batch of 5', async () => {
    const batchRows: MultiTenureReturns[] = Array.from({ length: 5 }, (_, i) => ({
      iid: `iid-${i + 1}`,
      date: '2026-05-22',
      ret_1d: `0.00${i + 1}0`,
      ret_1w: `0.0${i + 1}10`,
      ret_1m: `0.0${i + 1}50`,
      ret_3m: `0.${i + 1}200`,
      ret_6m: `0.${i + 1}500`,
      ret_12m: `0.${i + 1}900`,
    }))
    sqlMock.mockResolvedValueOnce(batchRows)

    const result = await getMultiTenureReturnsBatch(
      ['iid-1', 'iid-2', 'iid-3', 'iid-4', 'iid-5'],
    )

    expect(result).toHaveLength(5)
    expect(result[0].iid).toBe('iid-1')
    expect(result[4].iid).toBe('iid-5')
    // Each row has all 6 tenures
    for (const row of result) {
      expect(row.ret_1d).toBeTruthy()
      expect(row.ret_12m).toBeTruthy()
    }
  })

  it('case 4 — batch with one invalid iid returns only valid rows (DB skips missing)', async () => {
    // DB returns only 4 rows when 1 of the 5 iids has no history
    const fourRows: MultiTenureReturns[] = [
      { iid: 'iid-A', date: '2026-05-22', ret_1d: '0.0100', ret_1w: '0.0210', ret_1m: '0.0500', ret_3m: '0.1100', ret_6m: '0.1800', ret_12m: '0.2600' },
      { iid: 'iid-B', date: '2026-05-22', ret_1d: '0.0050', ret_1w: '0.0180', ret_1m: '0.0400', ret_3m: '0.0900', ret_6m: '0.1500', ret_12m: '0.2200' },
      { iid: 'iid-C', date: '2026-05-22', ret_1d: '-0.0020', ret_1w: '-0.0080', ret_1m: '-0.0150', ret_3m: '-0.0300', ret_6m: '0.0500', ret_12m: '0.1100' },
      { iid: 'iid-D', date: '2026-05-22', ret_1d: '0.0030', ret_1w: '0.0090', ret_1m: '0.0250', ret_3m: '0.0600', ret_6m: '0.1000', ret_12m: '0.1700' },
      // iid-INVALID has no rows in atlas_stock_metrics_daily — DB returns nothing
    ]
    sqlMock.mockResolvedValueOnce(fourRows)

    const result = await getMultiTenureReturnsBatch(
      ['iid-A', 'iid-B', 'iid-C', 'iid-D', 'iid-INVALID'],
    )

    expect(result).toHaveLength(4)
    const iids = result.map(r => r.iid)
    expect(iids).toContain('iid-A')
    expect(iids).toContain('iid-D')
    expect(iids).not.toContain('iid-INVALID')
  })

  it('returns empty array immediately for empty iids input without querying DB', async () => {
    const result = await getMultiTenureReturnsBatch([])

    expect(result).toEqual([])
    expect(sqlMock).not.toHaveBeenCalled()
  })
})
