import { describe, it, expect } from 'vitest'
import { buildFundCurves, type EqPoint } from '../fundEquityCurve'

// REAL month-end NAV + index closes for Quant Small Cap (mstar F0GBR06SGW) and
// Nifty 50 / Nifty 500, Feb→Jun 2026, pulled from foundation_staging — NO synthetic
// inputs (rule #0). The fund ran +18.5% while Nifty 50 fell, so it exercises both a
// rising equity curve and RS lines climbing above 100.
const QUANT: EqPoint[] = [
  { d: '2026-02-27', fund: 236.63, nifty50: 25178.7, nifty500: 23166.9 },
  { d: '2026-03-31', fund: 219.53, nifty50: 22331.4, nifty500: 20528.1 },
  { d: '2026-04-20', fund: 248.03, nifty50: 23997.6, nifty500: 22683.6 },
  { d: '2026-05-29', fund: 267.64, nifty50: 23547.8, nifty500: 22657.0 },
  { d: '2026-06-25', fund: 280.40, nifty50: 23946.3, nifty500: 23000.0 },
]

describe('buildFundCurves', () => {
  it('rebases all three series to 100 at the first month', () => {
    const { equity } = buildFundCurves(QUANT)
    expect(equity[0]).toEqual({ d: '2026-02-27', fund: 100, nifty50: 100, nifty500: 100 })
  })

  it('tracks the fund vs Nifty 50 / Nifty 500 absolute curves (rebased)', () => {
    const { equity } = buildFundCurves(QUANT)
    const last = equity.at(-1)!
    expect(last.fund).toBeCloseTo(118.496, 2) // 100*280.40/236.63
    expect(last.nifty50).toBeCloseTo(95.105, 2) // 100*23946.3/25178.7 — Nifty 50 fell
    expect(last.nifty500).toBeCloseTo(99.280, 2) // 100*23000.0/23166.9
  })

  it('RS = fund-rebased ÷ index-rebased × 100, starting at 100', () => {
    const { rs } = buildFundCurves(QUANT)
    expect(rs[0]).toEqual({ d: '2026-02-27', vsNifty50: 100, vsNifty500: 100 })
    const last = rs.at(-1)!
    expect(last.vsNifty50).toBeCloseTo(124.594, 2) // beat Nifty 50 by ~24.6pp
    expect(last.vsNifty500).toBeCloseTo(119.356, 2) // beat Nifty 500 by ~19.4pp
  })

  it('skips leading months until all three series are present (RS must start at 100)', () => {
    const withGap: EqPoint[] = [
      { d: '2026-01-30', fund: 230, nifty50: null, nifty500: 22900 }, // no Nifty 50 yet → skipped
      ...QUANT,
    ]
    const { equity, rs } = buildFundCurves(withGap)
    expect(equity[0].d).toBe('2026-02-27')
    expect(rs[0]).toEqual({ d: '2026-02-27', vsNifty50: 100, vsNifty500: 100 })
  })

  it('nulls a benchmark point when its close is missing, without breaking the fund line', () => {
    const gap: EqPoint[] = [
      QUANT[0],
      { d: '2026-03-31', fund: 219.53, nifty50: null, nifty500: 20528.1 },
    ]
    const { equity, rs } = buildFundCurves(gap)
    expect(equity[1].fund).toBeCloseTo(92.773, 2) // 100*219.53/236.63 — fund still drawn
    expect(equity[1].nifty50).toBeNull()
    expect(rs[1].vsNifty50).toBeNull()
    expect(rs[1].vsNifty500).not.toBeNull()
  })

  it('returns empty when no month has all three series', () => {
    expect(buildFundCurves([{ d: '2026-06-25', fund: 280, nifty50: null, nifty500: null }])).toEqual({ equity: [], rs: [] })
  })
})
