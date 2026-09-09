// The methodology page's one hard contract: it must never state a weight of its own, and it
// must be honest about which lenses have a producer. Both are the kind of thing that goes
// quietly wrong — a page explaining the numbers, itself out of date.
import { describe, expect, it } from 'vitest'
import { ETF_LENSES } from '@/lib/queries/methodology'

describe('the methodology lens list', () => {
  it('names every lens the score table carries, and only those', () => {
    // ddl/05_scores.sql's etf_scores_daily lens columns. A lens added there and not here
    // would be computed and never explained.
    expect(ETF_LENSES.map((l) => l.lens).sort()).toEqual(
      ['cost_liquidity', 'flow', 'quality', 'risk', 'technical'].sort(),
    )
  })

  it('carries no weight of its own — weights come from the thresholds table', () => {
    for (const lens of ETF_LENSES) {
      expect(Object.keys(lens)).toEqual(['lens', 'label', 'reads'])
      expect(JSON.stringify(lens)).not.toMatch(/0\.\d+/)
    }
  })

  it('says what each lens reads, so a reader can check the claim', () => {
    for (const lens of ETF_LENSES) {
      expect(lens.reads.length).toBeGreaterThan(20)
      expect(lens.label.length).toBeGreaterThan(2)
    }
  })
})
