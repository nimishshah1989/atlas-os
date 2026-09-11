// The three column sets. What is under test is a contract about WHICH columns exist in each view,
// not any number: the sets decide what a fund manager can compare, and getting one wrong is a
// column that silently is not there.
import { describe, expect, it } from 'vitest'
import { boardColumns, isBoardView, VIEWS, type ColumnContext } from '@/components/explorer/columns'

const ETF: ColumnContext = { assetClass: 'etf', lensTotal: 5, technicalWeight: 0.35 }
const STOCK: ColumnContext = { assetClass: 'stock', lensTotal: 5, technicalWeight: 0.3 }
const keys = (ctx: ColumnContext, scored: boolean, view: (typeof VIEWS)[number]) =>
  boardColumns(ctx, scored, view).map((c) => c.key)

describe('identity holds while the question changes', () => {
  it('opens every ETF view with the same three columns, so a row stays the same row', () => {
    for (const v of VIEWS) expect(keys(ETF, true, v).slice(0, 3)).toEqual(['symbol', 'name', 'peer'])
  })

  it('opens every stock view with the sector and the cap cohort instead of a peer group', () => {
    for (const v of VIEWS) expect(keys(STOCK, true, v).slice(0, 4)).toEqual(['symbol', 'name', 'sector', 'cohort'])
  })

  it('carries the composite into every view — the column the reader sorts on must never vanish', () => {
    for (const v of VIEWS) {
      expect(keys(ETF, true, v)).toContain('composite')
      expect(keys(STOCK, true, v)).toContain('composite')
    }
  })
})

describe('the lens view shows the lenses that market actually has', () => {
  it('gives a fund risk, cost, flow and quality', () => {
    expect(keys(ETF, true, 'lenses')).toEqual(
      expect.arrayContaining(['lens_risk', 'lens_cost_liquidity', 'lens_flow', 'lens_quality']),
    )
  })

  it('gives a company fundamental, valuation, catalyst and flow — and none of the fund lenses', () => {
    const k = keys(STOCK, true, 'lenses')
    expect(k).toEqual(expect.arrayContaining(['lens_fundamental', 'lens_valuation', 'lens_catalyst', 'lens_flow']))
    expect(k).not.toContain('lens_cost_liquidity')
    expect(k).not.toContain('lens_quality')
  })
})

describe('the cost view', () => {
  it('gives a fund its theme, its fee and its assets', () => {
    expect(keys(ETF, true, 'cost')).toEqual(expect.arrayContaining(['theme_col', 'expense', 'aum', 'emas']))
  })

  it('gives a company NEITHER a fee NOR fund assets — a company has no expense ratio', () => {
    const k = keys(STOCK, true, 'cost')
    expect(k).not.toContain('expense')
    expect(k).not.toContain('aum')
    expect(k).not.toContain('theme_col')
    expect(k).toContain('emas')
  })
})

describe('before anything is scored', () => {
  it('collapses to ONE honest set whatever view is asked for — three ways to read no scores is three empty tables', () => {
    const unscored = VIEWS.map((v) => keys(ETF, false, v))
    for (const k of unscored) {
      expect(k).toEqual(unscored[0])
      expect(k).not.toContain('composite')
      expect(k).toContain('adv')
    }
  })
})

describe('a view arriving from the address bar', () => {
  it('accepts the three it knows and refuses anything else, so a stale bookmark falls back', () => {
    for (const v of VIEWS) expect(isBoardView(v)).toBe(true)
    expect(isBoardView('holdings')).toBe(false)
    expect(isBoardView(null)).toBe(false)
    expect(isBoardView(undefined)).toBe(false)
  })
})
