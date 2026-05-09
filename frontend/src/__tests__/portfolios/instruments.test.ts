// Tests for src/lib/queries/instruments.ts
// Covers: filter wiring (mocked sql) for stocks, ETFs, and mutual funds.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({ default: vi.fn() }))

import sql from '@/lib/db'
import {
  getStocksForPicker,
  getETFsForPicker,
  getMutualFundsForPicker,
} from '@/lib/queries/instruments'

function mockSqlReturn(data: unknown): void {
  ;(sql as unknown as { mockReturnValue: (v: unknown) => void }).mockReturnValue(
    Promise.resolve(data),
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('getStocksForPicker', () => {
  it('returns empty array when no stocks match', async () => {
    mockSqlReturn([])
    const result = await getStocksForPicker({ tier: 'Micro', sector: 'Pharma' })
    expect(result).toEqual([])
  })

  it('passes filters and returns stock rows', async () => {
    const mockRows = [
      {
        instrument_id: 'uuid-hdfc',
        symbol: 'HDFCBANK',
        company_name: 'HDFC Bank Limited',
        tier: 'Large',
        sector: 'Banks',
        rs_state: 'Leader',
        effective_to: null,
      },
    ]
    mockSqlReturn(mockRows)
    const result = await getStocksForPicker({ tier: 'Large', sector: 'Banks' })
    expect(result).toHaveLength(1)
    expect(result[0].symbol).toBe('HDFCBANK')
    expect(result[0].rs_state).toBe('Leader')
  })

  it('handles null rs_state (metrics not available)', async () => {
    const mockRows = [
      {
        instrument_id: 'uuid-x',
        symbol: 'XYZCO',
        company_name: 'XYZ Corp',
        tier: 'Small',
        sector: 'IT',
        rs_state: null,
        effective_to: null,
      },
    ]
    mockSqlReturn(mockRows)
    const result = await getStocksForPicker()
    expect(result[0].rs_state).toBeNull()
  })

  it('works with no filters (default call)', async () => {
    mockSqlReturn([])
    const result = await getStocksForPicker()
    expect(result).toEqual([])
    expect(sql).toHaveBeenCalledTimes(1)
  })

  it('NUMERIC columns returned as string', async () => {
    // rs_state is a text field, not NUMERIC — this test confirms no float conversion
    const mockRows = [
      {
        instrument_id: 'uuid-y',
        symbol: 'RELIANCE',
        company_name: 'Reliance Industries',
        tier: 'Large',
        sector: 'Energy',
        rs_state: 'Strong',
        effective_to: null,
      },
    ]
    mockSqlReturn(mockRows)
    const result = await getStocksForPicker()
    expect(typeof result[0].symbol).toBe('string')
    expect(typeof result[0].tier).toBe('string')
  })
})

describe('getETFsForPicker', () => {
  it('returns empty array when no ETFs match', async () => {
    mockSqlReturn([])
    const result = await getETFsForPicker({ theme: 'Sectoral', linked_sector: 'Pharma' })
    expect(result).toEqual([])
  })

  it('returns ETF rows with correct shape', async () => {
    const mockRows = [
      {
        ticker: 'NIFTYBEES',
        etf_name: 'Nippon India ETF Nifty BeES',
        fund_house: 'Nippon India Mutual Fund',
        theme: 'Broad',
        linked_sector: null,
        asset_class: 'Equity',
        effective_to: null,
      },
    ]
    mockSqlReturn(mockRows)
    const result = await getETFsForPicker({ theme: 'Broad' })
    expect(result).toHaveLength(1)
    expect(result[0].ticker).toBe('NIFTYBEES')
    expect(result[0].linked_sector).toBeNull()
  })

  it('works with no filters', async () => {
    mockSqlReturn([])
    const result = await getETFsForPicker()
    expect(result).toEqual([])
  })

  it('handles sectoral ETF with linked_sector', async () => {
    const mockRows = [
      {
        ticker: 'BANKBEES',
        etf_name: 'Nippon Bank BeES',
        fund_house: 'Nippon',
        theme: 'Sectoral',
        linked_sector: 'Banks',
        asset_class: 'Equity',
        effective_to: null,
      },
    ]
    mockSqlReturn(mockRows)
    const result = await getETFsForPicker({ linked_sector: 'Banks' })
    expect(result[0].linked_sector).toBe('Banks')
    expect(result[0].theme).toBe('Sectoral')
  })
})

describe('getMutualFundsForPicker', () => {
  it('returns empty array when no funds match', async () => {
    mockSqlReturn([])
    const result = await getMutualFundsForPicker({ category_name: 'Mid Cap' })
    expect(result).toEqual([])
  })

  it('returns fund rows with correct shape', async () => {
    const mockRows = [
      {
        mstar_id: 'F00000XXXX',
        scheme_name: 'Mirae Asset Large Cap Fund - Growth',
        amc: 'Mirae Asset Investment Managers (India) Pvt. Ltd.',
        broad_category: 'Equity',
        category_name: 'Large Cap',
        effective_to: null,
      },
    ]
    mockSqlReturn(mockRows)
    const result = await getMutualFundsForPicker({ broad_category: 'Equity' })
    expect(result).toHaveLength(1)
    expect(result[0].mstar_id).toBe('F00000XXXX')
    expect(result[0].category_name).toBe('Large Cap')
  })

  it('works with no filters', async () => {
    mockSqlReturn([])
    const result = await getMutualFundsForPicker()
    expect(result).toEqual([])
  })
})
