// Smoke test for getStockTraderHeader — pins the close_price wiring (B1/B2).
//
// The trader-view EventHeader sources its "Price" cell from the MV's
// close_price (the 747/747-populated column), not the 404-prone tv endpoint.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getStockTraderHeader } from '../stock-trader-header'

const baseRow = {
  symbol: 'RELIANCE',
  cap_tier: 'tier_1_megacap',
  conviction_score: '0.2595',
  conviction_tier: 'tier_1_megacap',
  composite_score: '-4.8100',
  combined_verdict: 'AVOID',
  verdict_reason: null,
  verdict_source: 'composite_score',
  first_called_at: null,
  since_call_return: null,
  cell_action: null,
  cell_tenure: null,
  cell_predicted_excess: null,
  cell_ic: null,
  close_price: '1321.20',
}

describe('getStockTraderHeader', () => {
  beforeEach(() => sqlMock.mockReset())

  it('parses close_price into a number for the header Price cell', async () => {
    sqlMock.mockResolvedValueOnce([baseRow])
    const out = await getStockTraderHeader('RELIANCE')
    expect(out?.close_price).toBe(1321.2)
    expect(out?.conviction_score).toBe(0.2595)
  })

  it('returns null close_price when the MV column is null', async () => {
    sqlMock.mockResolvedValueOnce([{ ...baseRow, close_price: null }])
    const out = await getStockTraderHeader('RELIANCE')
    expect(out?.close_price).toBeNull()
  })
})
