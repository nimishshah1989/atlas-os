// Smoke tests for instrument.ts — getInstrumentDetail (iid/symbol lookup)
// + getInstrumentMeta + resolveSymbolToIid.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))

// React.cache pass-through: call the inner function directly so each test
// invocation runs the real function body (no cross-test memoization leak).
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

import { getInstrumentDetail, getInstrumentMeta, resolveSymbolToIid } from '../instrument'

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

// ---------------------------------------------------------------------------
// getInstrumentMeta
// ---------------------------------------------------------------------------

describe('getInstrumentMeta', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns full meta with name mapped from company_name when iid is valid', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        instrument_id: 'c1c1c1c1-0000-0000-0000-000000000001',
        symbol: 'RELIANCE',
        company_name: 'Reliance Industries Limited',
        sector: 'Energy',
        tier: 'Large',
      },
    ])
    const meta = await getInstrumentMeta('c1c1c1c1-0000-0000-0000-000000000001')
    expect(meta).not.toBeNull()
    expect(meta?.instrument_id).toBe('c1c1c1c1-0000-0000-0000-000000000001')
    expect(meta?.symbol).toBe('RELIANCE')
    // company_name → name mapping is the key assertion
    expect(meta?.name).toBe('Reliance Industries Limited')
    expect(meta?.sector).toBe('Energy')
    expect(meta?.cap_tier).toBe('Large')
    // market_cap_cr is always null at v6.0 (column does not exist)
    expect(meta?.market_cap_cr).toBeNull()
  })

  it('returns null when iid is not in active universe', async () => {
    sqlMock.mockResolvedValueOnce([])
    const meta = await getInstrumentMeta('00000000-0000-0000-0000-000000000000')
    expect(meta).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// resolveSymbolToIid
// ---------------------------------------------------------------------------

describe('resolveSymbolToIid', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns instrument_id UUID when symbol exists', async () => {
    sqlMock.mockResolvedValueOnce([
      { instrument_id: 'd2d2d2d2-0000-0000-0000-000000000002' },
    ])
    const iid = await resolveSymbolToIid('RELIANCE')
    expect(iid).toBe('d2d2d2d2-0000-0000-0000-000000000002')
  })

  it('returns null when symbol does not exist in universe', async () => {
    sqlMock.mockResolvedValueOnce([])
    const iid = await resolveSymbolToIid('NONEXISTENT')
    expect(iid).toBeNull()
  })
})
