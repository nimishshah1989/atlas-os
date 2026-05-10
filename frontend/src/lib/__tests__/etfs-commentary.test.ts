import { describe, it, expect } from 'vitest'
import { buildETFCommentary, type ETFPageAggregates } from '@/lib/commentary/etfs'

function makeAgg(overrides: Partial<ETFPageAggregates> = {}): ETFPageAggregates {
  return {
    total: 80,
    investable_count: 20,
    leader_count: 12,
    strong_count: 8,
    pct_leader_strong: 0.25,
    broad_investable_count: 8,
    sectoral_investable_count: 10,
    median_rs_pctile: 0.55,
    accel_count: 15,
    regime_state: 'Cautious',
    deployment_multiplier: 0.6,
    ...overrides,
  }
}

describe('buildETFCommentary', () => {
  it('returns an object with narrative and contextCards', () => {
    const result = buildETFCommentary(makeAgg())
    expect(result).toHaveProperty('narrative')
    expect(result).toHaveProperty('contextCards')
    expect(typeof result.narrative).toBe('string')
    expect(Array.isArray(result.contextCards)).toBe(true)
  })

  it('Risk-Off condition: fires when regime_state is Risk-Off', () => {
    const result = buildETFCommentary(makeAgg({ regime_state: 'Risk-Off' }))
    expect(result.narrative).toContain('Risk-Off')
  })

  it('Risk-Off condition: mentions 0% deployment', () => {
    const result = buildETFCommentary(makeAgg({ regime_state: 'Risk-Off' }))
    expect(result.narrative).toContain('0%')
  })

  it('thin breadth condition: fires when pct_leader_strong < 0.10', () => {
    const result = buildETFCommentary(makeAgg({ pct_leader_strong: 0.08, leader_count: 4, strong_count: 2 }))
    expect(result.narrative).toContain('thin')
  })

  it('defensive tilt condition: fires when broad_investable > sectoral_investable', () => {
    const result = buildETFCommentary(makeAgg({ broad_investable_count: 15, sectoral_investable_count: 5 }))
    expect(result.narrative).toContain('Defensive tilt')
  })

  it('broad strength condition: fires when pct_leader_strong >= 0.30', () => {
    const result = buildETFCommentary(makeAgg({ pct_leader_strong: 0.35 }))
    expect(result.narrative).toContain('Broad ETF strength')
  })

  it('default condition: fires when no other condition matches', () => {
    const agg = makeAgg({
      regime_state: 'Cautious',
      pct_leader_strong: 0.20,
      broad_investable_count: 5,
      sectoral_investable_count: 10,
    })
    const result = buildETFCommentary(agg)
    expect(result.narrative).toContain('qualify for new positions')
  })

  it('contextCards always has 4 entries with expected labels', () => {
    const result = buildETFCommentary(makeAgg())
    const labels = result.contextCards.map(c => c.label)
    expect(labels).toContain('Investable')
    expect(labels).toContain('Leader/Strong')
    expect(labels).toContain('Broad Inv')
    expect(labels).toContain('Deployment')
  })
})
