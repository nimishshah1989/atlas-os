// frontend/src/components/sectors/__tests__/SectorRSMomentumBubble.test.tsx
// Tests for the pure point-builder behind the RS × momentum master bubble.
//
// Coverage (the math that can silently break — the JSX is thin):
//   - y (momentum) = rs_1m − rs_3m; x = the active RS window
//   - toggling the x axis to rs_sector_3m re-filters on that column
//   - a stock that can't compute momentum (missing rs_1m/rs_3m) or the active x is dropped
//   - null liq_cr falls to the dataset floor (bubble still renders, not dropped)

import { describe, it, expect } from 'vitest'
import { rsMomentumPoints } from '../SectorRSMomentumBubble'
import type { SectorStock } from '@/lib/queries/sector_lens'

function makeStock(symbol: string, overrides: Partial<SectorStock> = {}): SectorStock {
  return {
    symbol, name: symbol, cap: 'large',
    d_tech: 5, d_fund: 5, d_cat: null, d_flow: null, d_val: null, d_composite: 5,
    lead: 0, strength: 5,
    ret_1d: null, ret_1w: null, ret_1m: null, ret_3m: null, ret_6m: null, ret_12m: null,
    rs_1m: 8, rs_3m: 4, rs_6m: null, rs_sector_3m: 2,
    liq_cr: 100, ff_weight: null,
    ...overrides,
  }
}

describe('rsMomentumPoints', () => {
  it('sets x = rs_3m and y = rs_1m − rs_3m on the Nifty-500 axis', () => {
    const pts = rsMomentumPoints([makeStock('A', { rs_3m: 4, rs_1m: 8 })], 'rs_3m')
    expect(pts).toHaveLength(1)
    expect(pts[0].x).toBe(4)
    expect(pts[0].y).toBe(4) // 8 − 4
  })

  it('uses rs_sector_3m for x when toggled to the sector axis', () => {
    const pts = rsMomentumPoints([makeStock('A', { rs_3m: 4, rs_sector_3m: 2, rs_1m: 8 })], 'rs_sector_3m')
    expect(pts[0].x).toBe(2)
    expect(pts[0].y).toBe(4) // momentum still rs_1m − rs_3m
  })

  it('drops a stock that cannot compute momentum (missing rs_1m)', () => {
    const pts = rsMomentumPoints([
      makeStock('OK', { rs_3m: 4, rs_1m: 8 }),
      makeStock('NOMOM', { rs_3m: 4, rs_1m: null }),
    ], 'rs_3m')
    expect(pts.map(p => p.symbol)).toEqual(['OK'])
  })

  it('drops a stock missing the active x column when toggled to the sector axis', () => {
    const pts = rsMomentumPoints([
      makeStock('OK', { rs_3m: 4, rs_sector_3m: 2, rs_1m: 8 }),
      makeStock('NOSEC', { rs_3m: 4, rs_sector_3m: null, rs_1m: 8 }),
    ], 'rs_sector_3m')
    expect(pts.map(p => p.symbol)).toEqual(['OK'])
  })

  it('floors a null liquidity to the dataset minimum instead of dropping the stock', () => {
    const pts = rsMomentumPoints([
      makeStock('BIG', { liq_cr: 50 }),
      makeStock('NULLLIQ', { liq_cr: null }),
    ], 'rs_3m')
    const nullLiq = pts.find(p => p.symbol === 'NULLLIQ')
    expect(nullLiq).toBeDefined()
    expect(nullLiq!.z).toBe(50)
  })
})
