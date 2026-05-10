import { describe, it, expect } from 'vitest'
import { buildSectorCommentary, type SectorCommentaryContext } from '@/lib/commentary/sectors'

const base: SectorCommentaryContext = {
  sectorName: 'Banking',
  sectorState: 'Neutral',
  divergence_flag: false,
  bottomup_momentum_state: 'Improving',
  constituent_count: 18,
  leadingRRGCount: 1,
  recentlyUpgraded: false,
}

describe('buildSectorCommentary', () => {
  it('returns a narrative string', () => {
    const result = buildSectorCommentary(base)
    expect(typeof result.narrative).toBe('string')
    expect(result.narrative.length).toBeGreaterThan(20)
  })

  it('condition 1: divergence_flag=true mentions conflict', () => {
    const result = buildSectorCommentary({ ...base, divergence_flag: true })
    expect(result.narrative.toLowerCase()).toContain('conflict')
  })

  it('condition 2: recently upgraded to Overweight mentions rotation signal', () => {
    const result = buildSectorCommentary({
      ...base,
      sectorState: 'Overweight',
      recentlyUpgraded: true,
    })
    expect(result.narrative.toLowerCase()).toContain('rotation signal')
  })

  it('condition 3: 3+ Leading RRG sectors mentions broad leadership', () => {
    const result = buildSectorCommentary({ ...base, leadingRRGCount: 4 })
    expect(result.narrative.toLowerCase()).toContain('leadership')
  })

  it('condition 4: Deteriorating + Overweight warns to reduce exposure', () => {
    const result = buildSectorCommentary({
      ...base,
      sectorState: 'Overweight',
      bottomup_momentum_state: 'Deteriorating',
    })
    expect(result.narrative.toLowerCase()).toContain('reducing exposure')
  })

  it('condition 5: constituent_count < 10 warns small sample', () => {
    const result = buildSectorCommentary({ ...base, constituent_count: 7 })
    expect(result.narrative).toContain('7')
    expect(result.narrative.toLowerCase()).toContain('small')
  })

  it('fallthrough: no special condition returns generic summary', () => {
    const result = buildSectorCommentary(base)
    expect(result.narrative.length).toBeGreaterThan(20)
  })

  it('returns contextCards array with at least 2 items', () => {
    const result = buildSectorCommentary(base)
    expect(Array.isArray(result.contextCards)).toBe(true)
    expect(result.contextCards.length).toBeGreaterThanOrEqual(2)
  })
})
