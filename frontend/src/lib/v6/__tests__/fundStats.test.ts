import { describe, it, expect } from 'vitest'
import { sectorComposition, computeFundRiskStats, type NavPoint } from '../fundStats'

describe('sectorComposition', () => {
  it('groups holdings by sector, sums weight, counts, sorted desc', () => {
    const out = sectorComposition([
      { sector: 'Financials', weight: 10 }, { sector: 'IT', weight: 8 },
      { sector: 'Financials', weight: 5 }, { sector: null, weight: 2 },
    ])
    expect(out).toEqual([
      { sector: 'Financials', weight: 15, count: 2 },
      { sector: 'IT', weight: 8, count: 1 },
      { sector: 'Unclassified', weight: 2, count: 1 },
    ])
  })
  it('returns [] for no holdings', () => {
    expect(sectorComposition([])).toEqual([])
  })
})

// Risk math is a pure algorithm — these are explicit hand-computed series (testing the formula,
// not market data). The live page additionally shows REAL fund NAV stats (rule #0 end-to-end).
const mk = (navs: number[]): NavPoint[] => navs.map((nav, i) => ({ d: `2026-${String((i % 12) + 1).padStart(2, '0')}-01`, nav }))

describe('computeFundRiskStats', () => {
  it('max drawdown = worst peak-to-trough decline', () => {
    // peak 120 → trough 90 = −25%
    expect(computeFundRiskStats(mk([100, 120, 90, 108])).maxDrawdown).toBeCloseTo(-0.25, 6)
  })
  it('no drawdown for a monotonically rising series', () => {
    expect(computeFundRiskStats(mk([100, 110, 121])).maxDrawdown).toBe(0)
  })
  it('zero volatility for constant monthly returns → null Sharpe', () => {
    const s = computeFundRiskStats(mk([100, 110, 121])) // +10% each month
    expect(s.volAnn).toBeCloseTo(0, 9)
    expect(s.sharpe).toBeNull()
    expect(s.sortino).toBeNull()
  })
  it('cagrIncept annualises the full window', () => {
    // 2 monthly periods of +10% → (1.21)^(12/2) − 1
    expect(computeFundRiskStats(mk([100, 110, 121])).cagrIncept).toBeCloseTo(Math.pow(1.21, 6) - 1, 6)
  })
  it('ret1y is the simple return over the last 12 months', () => {
    const navs = [100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 200] // navs[0]→navs[12]
    expect(computeFundRiskStats(mk(navs)).ret1y).toBeCloseTo(1.0, 6) // +100%
  })
  it('windows are null when history is too short', () => {
    const s = computeFundRiskStats(mk([100, 110, 121]))
    expect(s.ret1y).toBeNull()
    expect(s.cagr3y).toBeNull()
    expect(s.cagr5y).toBeNull()
    expect(s.months).toBe(2)
  })
  it('sharpe = (annualised return − rf) / annualised vol', () => {
    const navs = [100, 105, 99, 107, 103, 110] // mixed
    const s = computeFundRiskStats(navs.map((nav, i) => ({ d: `d${i}`, nav })), 0.065)
    // recompute the expectation from the same primitives the impl uses
    const rets = navs.slice(1).map((v, i) => v / navs[i] - 1)
    const mean = rets.reduce((a, b) => a + b, 0) / rets.length
    const sd = Math.sqrt(rets.reduce((a, r) => a + (r - mean) ** 2, 0) / rets.length)
    const volAnn = sd * Math.sqrt(12)
    const cagr = Math.pow(navs[navs.length - 1] / navs[0], 12 / rets.length) - 1
    expect(s.sharpe).toBeCloseTo((cagr - 0.065) / volAnn, 6)
  })
})
