// Smoke test for getInstrumentDetail — verifies iid + symbol lookup paths.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getInstrumentDetail } from '../instrument'

describe('getInstrumentDetail', () => {
  beforeEach(() => sqlMock.mockReset())

  // Two stocks in the universe.
  function setupTwoStocks() {
    sqlMock
      .mockResolvedValueOnce([
        {
          iid: 'aaa-uuid',
          symbol: 'RELIANCE',
          company_name: 'Reliance',
          sector: 'Energy',
          tier: 'Large',
          rs_state: 'Leader',
          engine_state: 'Stage 2',
          is_investable: true,
          ret_1m: null, ret_3m: null, ret_6m: null, ret_12m: null,
          rs_pctile_3m: null,
        },
        {
          iid: 'bbb-uuid',
          symbol: 'TCS',
          company_name: 'TCS',
          sector: 'IT',
          tier: 'Large',
          rs_state: null,
          engine_state: null,
          is_investable: null,
          ret_1m: null, ret_3m: null, ret_6m: null, ret_12m: null,
          rs_pctile_3m: null,
        },
      ])
      .mockResolvedValueOnce([])
  }

  it('resolves by iid', async () => {
    setupTwoStocks()
    const out = await getInstrumentDetail('bbb-uuid', '2026-05-22')
    expect(out?.symbol).toBe('TCS')
  })

  it('resolves by symbol', async () => {
    setupTwoStocks()
    const out = await getInstrumentDetail('RELIANCE', '2026-05-22')
    expect(out?.iid).toBe('aaa-uuid')
  })

  it('returns null when neither iid nor symbol matches', async () => {
    setupTwoStocks()
    const out = await getInstrumentDetail('ZZZ-NOPE', '2026-05-22')
    expect(out).toBeNull()
  })
})
