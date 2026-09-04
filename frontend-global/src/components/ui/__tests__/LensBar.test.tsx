/**
 * Structure-only render test for the Lens bar. Nothing here is a market number: the weights are
 * the ETF lens weight SEEDS written in docs/global/plan.md § "ETF lenses" (technical 0.35, cost &
 * liquidity 0.20, flow 0.15, quality / look-through 0.30), and the one non-null score is the flow
 * lens's documented centre ("centred 50", same section). Assertions cover shape only — segment
 * count, width in proportion to weight, an empty track for an absent lens — never a value.
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { LensBar, type LensSegment } from '@/components/ui/LensBar'

const SEEDED_WEIGHTS: LensSegment[] = [
  { key: 'technical', label: 'Technical', weight: 0.35, score: null },
  { key: 'cost_liquidity', label: 'Cost & liquidity', weight: 0.2, score: null },
  { key: 'flow', label: 'Flow', weight: 0.15, score: 50 },
  { key: 'quality', label: 'Quality', weight: 0.3, score: null },
]

describe('LensBar', () => {
  it('renders one segment per lens', () => {
    const { container } = render(<LensBar segments={SEEDED_WEIGHTS} />)
    expect(container.querySelectorAll('[data-lens-segment]')).toHaveLength(SEEDED_WEIGHTS.length)
  })

  it('sizes each segment in proportion to its weight', () => {
    const { container } = render(<LensBar segments={SEEDED_WEIGHTS} />)
    const technical = container.querySelector<HTMLElement>('[data-lens-segment="technical"]')
    const flow = container.querySelector<HTMLElement>('[data-lens-segment="flow"]')
    expect(technical?.style.flex).toBe('0.35 1 0%')
    expect(flow?.style.flex).toBe('0.15 1 0%')
  })

  it('leaves the track empty when the lens is absent, and fills it when present', () => {
    const { container } = render(<LensBar segments={SEEDED_WEIGHTS} />)
    expect(container.querySelector('[data-lens-segment="technical"] [data-lens-fill]')).toBeNull()
    expect(container.querySelector('[data-lens-segment="flow"] [data-lens-fill]')).not.toBeNull()
  })

  it('uses the sm height by default and lg on request, with labels only at lg', () => {
    const sm = render(<LensBar segments={SEEDED_WEIGHTS} />)
    expect(sm.container.querySelector('[data-lens-bar]')?.getAttribute('data-lens-bar')).toBe('sm')
    expect(sm.container.textContent).not.toContain('Technical')
    sm.unmount()

    const lg = render(<LensBar segments={SEEDED_WEIGHTS} size="lg" />)
    expect(lg.container.querySelector('[data-lens-bar]')?.getAttribute('data-lens-bar')).toBe('lg')
    expect(lg.container.textContent).toContain('Technical')
  })
})
