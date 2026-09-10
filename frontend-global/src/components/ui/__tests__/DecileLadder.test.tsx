/**
 * Atlas's signature block, on produced output rather than on the adapter's return value: what a
 * reader of the detail page actually sees when the scorer has not reached a lens.
 *
 * PROVENANCE. The row is the REAL degenerate one `blend()` writes when no lens had data — SPY in
 * the scratch database of EOD 2026-09-03, BlendResult(None, 'BELOW_THRESHOLD', 0), the same row
 * src/components/explorer/__tests__/InstrumentExplorer.test.tsx and src/lib/__tests__/ladder.test.ts
 * are built on. The weights are the seeds of scripts/global_market/seed_thresholds.py. No score is
 * invented, because the failure this file exists to catch is a score APPEARING where none was
 * computed (rule #0).
 */
import { render, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DecileLadder, NOT_MEASURED } from '@/components/ui/DecileLadder'
import { scoreToLadder } from '@/lib/ladder'
import type { ScoreDetail } from '@/lib/queries/scores'

const DEGENERATE: ScoreDetail = {
  scored_on: '2026-09-03',
  // Every lens in this fixture is null, so no lens carries a decile — the real shape, not a gap.
  deciles: {},
  values: { composite: null, technical: null, risk: null, cost_liquidity: null, flow: null, quality: null },
  conviction_tier: 'BELOW_THRESHOLD',
  peer_group: 'equity:broad_market',
  lenses_active: 0,
  coverage_factor: null,
  decile: null,
  peer_rank: null,
  peer_n: null,
  evidence: { technical: { reason: 'no sub-score had inputs' } },
  lenses: [
    { key: 'technical', weight: 0.35 },
    { key: 'quality', weight: 0.3 },
    { key: 'cost_liquidity', weight: 0.2 },
    { key: 'flow', weight: 0.15 },
    { key: 'risk', weight: 0 },
  ],
}

const draw = () =>
  render(<DecileLadder lenses={scoreToLadder('etf', DEGENERATE)} defaultOpenKey="technical" />).container

describe('the DecileLadder', () => {
  it('draws one row per lens, widest weight first', () => {
    const rows = draw().querySelectorAll('details')
    expect(rows).toHaveLength(5)
    expect(rows[0]?.textContent).toContain('Technical')
  })

  it('gives an unmeasured lens an EMPTY track and no fill — not a bar at zero', () => {
    const c = draw()
    expect(c.querySelectorAll('[data-lens-segment]')).toHaveLength(5)
    expect(c.querySelectorAll('[data-lens-fill]')).toHaveLength(0)
  })

  it('prints the words, never a 0, where a score would go', () => {
    const c = draw()
    expect(c.textContent).toContain(NOT_MEASURED)
    expect(within(c).queryByText('0')).toBeNull()
    expect(within(c).queryByText('0.0')).toBeNull()
  })

  it('says "overlay" for a lens carried at weight 0, and prints the real weight otherwise', () => {
    const text = draw().textContent ?? ''
    expect(text).toContain('overlay')
    expect(text).toContain('35%')
  })

  it('opens the named row so the actual numbers are on the screen without a click', () => {
    const rows = draw().querySelectorAll('details')
    expect(rows[0]?.open).toBe(true)
    expect(rows[1]?.open).toBe(false)
    expect(rows[0]?.textContent).toContain('The actual numbers')
  })

  it('shows the scorer’s own evidence for the lens it wrote one for', () => {
    expect(draw().textContent).toContain('reason: no sub-score had inputs')
  })
})
