import { describe, it, expect } from 'vitest'
import { stateRank, matchesSearch, buildSortKey, RS_ORDER, MOM_ORDER } from '@/lib/screener-utils'

describe('stateRank', () => {
  it('returns 0 for the first item in the order', () => {
    expect(stateRank(RS_ORDER, 'Leader')).toBe(0)
  })

  it('returns correct index for a known state', () => {
    expect(stateRank(RS_ORDER, 'Average')).toBe(4)
  })

  it('returns order.length for an unknown state', () => {
    expect(stateRank(RS_ORDER, 'Unknown')).toBe(RS_ORDER.length)
  })

  it('returns order.length for null', () => {
    expect(stateRank(MOM_ORDER, null)).toBe(MOM_ORDER.length)
  })
})

describe('matchesSearch', () => {
  it('matches symbol case-insensitively', () => {
    expect(matchesSearch({ symbol: 'RELIANCE', companyName: 'Reliance Industries' }, 'rel')).toBe(true)
  })

  it('matches companyName case-insensitively', () => {
    expect(matchesSearch({ symbol: 'HDFC', companyName: 'HDFC Bank Ltd' }, 'bank')).toBe(true)
  })

  it('returns true for empty query', () => {
    expect(matchesSearch({ symbol: 'X', companyName: 'Y' }, '')).toBe(true)
  })

  it('returns true for whitespace-only query', () => {
    expect(matchesSearch({ symbol: 'X', companyName: 'Y' }, '   ')).toBe(true)
  })

  it('returns false when neither symbol nor name matches', () => {
    expect(matchesSearch({ symbol: 'INFY', companyName: 'Infosys' }, 'reliance')).toBe(false)
  })
})

describe('buildSortKey', () => {
  it('returns numeric value for rs_pctile_3m', () => {
    const result = buildSortKey('rs_pctile_3m', { rs_pctile_3m: '0.85' })
    expect(result).toBeCloseTo(0.85)
  })

  it('returns -Infinity for null numeric column', () => {
    expect(buildSortKey('rs_pctile_3m', { rs_pctile_3m: null })).toBe(-Infinity)
  })

  it('returns stateRank index for rs_state', () => {
    expect(buildSortKey('rs_state', { rs_state: 'Leader' })).toBe(0)
    expect(buildSortKey('rs_state', { rs_state: 'Laggard' })).toBe(RS_ORDER.length - 1)
  })

  it('returns stateRank for momentum_state', () => {
    expect(buildSortKey('momentum_state', { momentum_state: 'Accelerating' })).toBe(0)
  })
})
