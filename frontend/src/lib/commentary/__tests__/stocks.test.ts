import { describe, it, expect, vi } from 'vitest'

vi.mock('server-only', () => ({}))

import { buildStocksCommentary, type StocksPageAggregates } from '@/lib/commentary/stocks'

const base: StocksPageAggregates = {
  total:                 500,
  investable_count:      40,
  leader_count:          30,
  strong_count:          60,
  pct_leader_strong:     0.18,
  median_rs_pctile:      0.55,
  accel_count:           20,
  regime_state:          'Constructive',
  deployment_multiplier: 0.7,
}

describe('buildStocksCommentary', () => {
  it('returns a narrative string with meaningful length', () => {
    const result = buildStocksCommentary(base)
    expect(typeof result.narrative).toBe('string')
    expect(result.narrative.length).toBeGreaterThan(30)
  })

  it('returns a non-empty context cards array', () => {
    const result = buildStocksCommentary(base)
    expect(Array.isArray(result.contextCards)).toBe(true)
    expect(result.contextCards.length).toBeGreaterThan(0)
  })

  it('context cards include investable_count', () => {
    const result = buildStocksCommentary(base)
    const card = result.contextCards.find(c => c.label.toLowerCase().includes('investable'))
    expect(card).toBeDefined()
    expect(card?.value).toContain('40')
  })

  it('context cards include leader+strong count', () => {
    const result = buildStocksCommentary(base)
    const card = result.contextCards.find(c => c.label.toLowerCase().includes('leader'))
    expect(card).toBeDefined()
    expect(card?.value).toContain('90') // 30 + 60
  })

  it('context cards include deployment %', () => {
    const result = buildStocksCommentary(base)
    const card = result.contextCards.find(c => c.label.toLowerCase().includes('deploy'))
    expect(card).toBeDefined()
    expect(card?.value).toContain('70%')
  })

  it('flags thin leadership when pct_leader_strong < 0.10', () => {
    const thin = { ...base, pct_leader_strong: 0.08, leader_count: 5, strong_count: 10 }
    const result = buildStocksCommentary(thin)
    expect(result.narrative.toLowerCase()).toMatch(/thin|narrow|few|limited/)
  })

  it('calls out broad strength when pct_leader_strong >= 0.30', () => {
    const broad = { ...base, pct_leader_strong: 0.35, leader_count: 100, strong_count: 75 }
    const result = buildStocksCommentary(broad)
    expect(result.narrative.toLowerCase()).toMatch(/broad|strong breadth|wide/)
  })

  it('references Risk-Off regime with 0% deployment', () => {
    const riskOff = { ...base, regime_state: 'Risk-Off', deployment_multiplier: 0 }
    const result = buildStocksCommentary(riskOff)
    expect(result.narrative.toLowerCase()).toMatch(/risk-off|no new|0%/)
  })

  it('narrative mentions regime state for base case', () => {
    const result = buildStocksCommentary(base)
    expect(result.narrative).toMatch(/Constructive|70%/)
  })

  it('deployment card is marked as not positive for Risk-Off (0% deployment)', () => {
    const riskOff = { ...base, regime_state: 'Risk-Off', deployment_multiplier: 0 }
    const result = buildStocksCommentary(riskOff)
    const card = result.contextCards.find(c => c.label.toLowerCase().includes('deploy'))
    expect(card?.deltaPositive).toBeFalsy()
  })
})
