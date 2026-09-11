/**
 * The map: two thousand funds as one picture, and the one way a picture can lie.
 *
 * A scatter plot has an origin, and an origin is a place a point can sit. If a fund with no
 * volatility measurement were plotted anyway, it would land at the bottom-left — reading as
 * "worst score, and it moves the most" — which is a claim nobody made about it (rule #0). So an
 * unmeasured fund is NOT PLOTTED and is COUNTED in the caption, where a reader can see how much
 * of the board the picture is leaving out.
 *
 * The rows are the same six real ones as src/lib/__tests__/thresholds.test.ts, read from the live
 * board's payload on 2026-09-09 for EOD 2026-09-08, plus the unmeasured row the rule is about.
 */
import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { NOT_CAPTURED } from '@/lib/__tests__/laterColumns'
import { StrengthRiskBubble, yDomain } from '@/components/explorer/StrengthRiskBubble'
import { toInstrumentRow, type InstrumentDbRow, type InstrumentRow } from '@/lib/facts'

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))

const BASE = {
  asset_class: 'etf', sector_gics: null, universe_exclusion: null, in_universe: true,
  leveraged: false, inverse: false, hedged: false, class_status: 'auto', country: null,
  region: null, technical: null, peer_rank: null, peer_n: null, pos_52w: null,
  rs_3m_spy: null, rs_6m_spy: null, strategy: null, theme: null, class_asset_class: null,
  conviction_tier: 'HIGH', lenses_active: 3,
  ...NOT_CAPTURED,
} as const

const RAW: InstrumentDbRow[] = [
  { ...BASE, symbol: 'SPY', name: 'State Street SPDR S&P 500 ETF Trust', composite: '74.55', peer_group: 'equity:broad_market', composite_decile: 7, rs_12m_spy: '0.00000000', adv_usd: '33721055202.1800', vol_ann: '0.12796628', mdd_12m: '-0.08879991' },
  { ...BASE, symbol: 'IWM', name: 'iShares Russell 2000 ETF', composite: '90.45', peer_group: 'equity:broad_market', composite_decile: 10, rs_12m_spy: '0.04691471', adv_usd: '5881301779.6000', vol_ann: '0.18755545', mdd_12m: '-0.11028399' },
  { ...BASE, symbol: 'XPH', name: 'SPDR S&P Pharmaceuticals ETF', composite: '82.27', peer_group: 'unclassified:unclassified', composite_decile: 10, rs_12m_spy: '0.24654311', adv_usd: '6619419.3600', vol_ann: '0.22853817', mdd_12m: '-0.11974610' },
  { ...BASE, symbol: 'FDD', name: 'First Trust STOXX European Select Dividend Index Fund', composite: '83.86', peer_group: 'equity:dividend_income', composite_decile: 9, rs_12m_spy: '0.13444258', adv_usd: '2296258.0750', vol_ann: '0.15312524', mdd_12m: '-0.09393774' },
  { ...BASE, symbol: 'XMLV', name: 'Invesco S&P MidCap Low Volatility ETF', composite: '48.91', peer_group: 'equity:factor', composite_decile: 1, rs_12m_spy: '-0.08786587', adv_usd: '1008121.0768', vol_ann: '0.10503199', mdd_12m: '-0.07033732' },
  { ...BASE, symbol: 'IBTQ', name: 'iShares iBonds Dec 2033 Term Treasury ETF', composite: '19.32', peer_group: 'fixed_income:fixed_income', composite_decile: 1, rs_12m_spy: '-0.17257728', adv_usd: '1001463.9469', vol_ann: '0.04733420', mdd_12m: '-0.04291339' },
  { ...BASE, symbol: 'NEWF', name: 'A fund the price spine has not reached', class_status: null, conviction_tier: null, lenses_active: null, composite: null, peer_group: null, composite_decile: null, rs_12m_spy: null, adv_usd: null, vol_ann: null, mdd_12m: null },
]
const ROWS: InstrumentRow[] = RAW.map(toInstrumentRow)

const draw = (rows: InstrumentRow[]) =>
  render(<StrengthRiskBubble rows={rows} assetClass="etf" noun="ETFs" />).container

describe('the map plots what was measured and says what it left out', () => {
  it('plots the six measured funds and not the seventh', () => {
    const c = draw(ROWS)
    const titles = [...c.querySelectorAll('circle title')].map((t) => t.textContent ?? '')
    expect(titles).toHaveLength(6)
    expect(titles.some((t) => t.startsWith('NEWF'))).toBe(false)
    expect(titles.some((t) => t.startsWith('SPY — composite 74.5'))).toBe(true)
  })

  it('COUNTS the fund it could not plot, rather than dropping it silently', () => {
    expect(draw(ROWS).textContent).toContain('1 not scored or not priced')
    // With nothing missing there is nothing to confess, and the caption does not invent a zero.
    expect(draw(ROWS.filter((r) => r.symbol !== 'NEWF')).textContent).not.toContain('not scored or not priced')
  })

  it('says outright that it can plot nothing, instead of drawing an empty grid', () => {
    const c = draw(ROWS.filter((r) => r.symbol === 'NEWF'))
    expect(c.querySelector('svg')).toBeNull()
    expect(c.textContent).toContain('Nothing to plot')
  })

  it('a fund with a decile carries that decile’s own step off the ramp', () => {
    // The same `--decile-N` var as the chip and the meter: one decile, one colour, everywhere.
    const c = draw(ROWS)
    const spy = [...c.querySelectorAll('circle')].find((el) => el.querySelector('title')?.textContent?.startsWith('SPY'))
    expect(spy?.getAttribute('fill')).toBe('var(--decile-7)')
    const iwm = [...c.querySelectorAll('circle')].find((el) => el.querySelector('title')?.textContent?.startsWith('IWM'))
    expect(iwm?.getAttribute('fill')).toBe('var(--decile-10)')
  })

  it('draws the biggest fund as the biggest disc, and the smallest still visible', () => {
    // SPY trades $33.7bn a day against IBTQ's $1.0M — a 33,000× spread. Radius-linear scaling
    // would make IBTQ a subpixel; area-proportional with a floor keeps it on the chart.
    const c = draw(ROWS)
    const r = (sym: string) =>
      Number(
        [...c.querySelectorAll('circle')]
          .find((el) => el.querySelector('title')?.textContent?.startsWith(sym))
          ?.getAttribute('r') ?? 0,
      )
    expect(r('SPY')).toBeGreaterThan(r('IWM'))
    expect(r('IWM')).toBeGreaterThan(r('IBTQ'))
    expect(r('IBTQ')).toBeGreaterThanOrEqual(3)
  })
})

/**
 * The axis rule is arithmetic over a list of numbers, so it is tested as arithmetic: the values
 * below are not market data and claim to be none. What the rule must do — leave a long tail on the
 * scale, cut a broken one — is stated in the names.
 */
describe('yDomain — the scale belongs to the cohort, not to its worst row', () => {
  it('leaves a small cohort alone: a percentile of six numbers is not evidence', () => {
    const vols = ROWS.filter((r) => r.vol_ann != null).map((r) => Number(r.vol_ann))
    expect(yDomain(vols)).toEqual({ max: Math.max(...vols), cut: null })
  })

  it('keeps a long tail on the scale — a fund at three times the median is a fund, not a defect', () => {
    const cohort = Array.from({ length: 200 }, (_, i) => 0.08 + (i / 199) * 0.5) // 8% … 58%
    const d = yDomain(cohort)
    expect(d.cut).toBeNull()
    expect(d.max).toBeCloseTo(0.58)
  })

  it('cuts a pathological tail and reports where it cut', () => {
    const cohort = Array.from({ length: 200 }, (_, i) => 0.08 + (i / 199) * 0.5)
    const d = yDomain([...cohort, 300]) // the 30,000%-a-year row of 2026-09-10
    expect(d.cut).not.toBeNull()
    expect(d.max).toBeLessThan(1)
    expect(d.max).toBeGreaterThan(0.5)
    // the cut is the same number as the new top of the axis
    expect(d.cut).toBe(d.max)
  })

  it('does not cut when the maximum is merely the largest, not far beyond the rest', () => {
    const cohort = Array.from({ length: 200 }, (_, i) => 0.08 + (i / 199) * 0.5)
    expect(yDomain([...cohort, 0.7]).cut).toBeNull()
  })

  it('answers zero for nothing', () => {
    expect(yDomain([])).toEqual({ max: 0, cut: null })
  })
})

describe('the real six funds are all on the scale', () => {
  it('pins none of them and says nothing about a cut', () => {
    const c = draw(ROWS)
    expect(c.querySelectorAll('circle[data-pinned]')).toHaveLength(0)
    expect(c.textContent).not.toContain('off the scale')
  })
})
