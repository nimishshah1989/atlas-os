// frontend/src/components/v6/__tests__/RankDecompositionCards.test.tsx
// 5 test cases covering: card count, quartile color mapping, delta sign coloring,
// empty-components edge case, and composite + rank hero text.

import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { RankDecompositionCards } from '../RankDecompositionCards'
import type { RankComponent } from '../RankDecompositionCards'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeComponent(overrides: Partial<RankComponent> = {}): RankComponent {
  return {
    name: 'Risk-Adjusted Return',
    raw_score: '78',
    percentile_in_category: '80',
    weight_pct: '50',
    delta_vs_cohort: '5',
    ...overrides,
  }
}

const DEFAULT_COMPONENTS: RankComponent[] = [
  makeComponent({ name: 'Risk-Adjusted Return', weight_pct: '50' }),
  makeComponent({ name: 'Holdings Conviction', weight_pct: '20', raw_score: '65' }),
  makeComponent({ name: 'Style/Sector Tilt', weight_pct: '20', raw_score: '55' }),
  makeComponent({ name: 'Cost & Manager', weight_pct: '10', raw_score: '90' }),
]

// ---------------------------------------------------------------------------
// Test 1: Renders N cards from input
// ---------------------------------------------------------------------------

describe('RankDecompositionCards — card count', () => {
  it('renders exactly N cards matching the components array length', () => {
    render(
      <RankDecompositionCards
        composite_score="78.4"
        components={DEFAULT_COMPONENTS}
        rank_in_category={12}
        category_size={89}
      />,
    )

    // Each card has an aria-label containing "score"
    const cards = document.querySelectorAll('[aria-label*="score"]')
    expect(cards).toHaveLength(DEFAULT_COMPONENTS.length)
  })

  it('renders 3 cards when given 3 components', () => {
    render(
      <RankDecompositionCards
        composite_score="70.0"
        components={DEFAULT_COMPONENTS.slice(0, 3)}
        rank_in_category={5}
        category_size={40}
      />,
    )

    const cards = document.querySelectorAll('[aria-label*="score"]')
    expect(cards).toHaveLength(3)
  })
})

// ---------------------------------------------------------------------------
// Test 2: Quartile color mapping
// ---------------------------------------------------------------------------

describe('RankDecompositionCards — quartile color mapping', () => {
  const cases: Array<{ percentile: string; expectedClass: string; label: string }> = [
    { percentile: '10', expectedClass: 'bg-signal-neg/20', label: '<25 → signal-neg' },
    { percentile: '30', expectedClass: 'bg-signal-warn/40', label: '25-50 → signal-warn heavier' },
    { percentile: '60', expectedClass: 'bg-signal-warn/20', label: '50-75 → signal-warn light' },
    { percentile: '90', expectedClass: 'bg-signal-pos/20', label: '>=75 → signal-pos' },
  ]

  it.each(cases)('percentile $percentile maps to $label', ({ percentile, expectedClass }) => {
    const { container } = render(
      <RankDecompositionCards
        composite_score="75.0"
        components={[makeComponent({ percentile_in_category: percentile })]}
        rank_in_category={1}
        category_size={10}
      />,
    )

    // The percentile chip is a <span> inside the card
    const chip = Array.from(container.querySelectorAll('span')).find(
      (el) => el.textContent?.includes('percentile'),
    )
    expect(chip).toBeDefined()
    expect(chip!.className).toContain(expectedClass)
  })
})

// ---------------------------------------------------------------------------
// Test 3: Delta sign coloring
// ---------------------------------------------------------------------------

describe('RankDecompositionCards — delta sign coloring', () => {
  it('positive delta renders with text-signal-pos class', () => {
    const { container } = render(
      <RankDecompositionCards
        composite_score="75.0"
        components={[makeComponent({ delta_vs_cohort: '7.5' })]}
        rank_in_category={1}
        category_size={10}
      />,
    )

    const deltaEl = Array.from(container.querySelectorAll('p')).find(
      (el) => el.textContent?.includes('pp vs cohort'),
    )
    expect(deltaEl).toBeDefined()
    expect(deltaEl!.className).toContain('text-signal-pos')
  })

  it('negative delta renders with text-signal-neg class', () => {
    const { container } = render(
      <RankDecompositionCards
        composite_score="75.0"
        components={[makeComponent({ delta_vs_cohort: '-4.2' })]}
        rank_in_category={1}
        category_size={10}
      />,
    )

    const deltaEl = Array.from(container.querySelectorAll('p')).find(
      (el) => el.textContent?.includes('pp vs cohort'),
    )
    expect(deltaEl).toBeDefined()
    expect(deltaEl!.className).toContain('text-signal-neg')
  })
})

// ---------------------------------------------------------------------------
// Test 4: Empty components — renders only hero strip, no card grid
// ---------------------------------------------------------------------------

describe('RankDecompositionCards — empty components', () => {
  it('renders hero strip and no card grid when components is empty', () => {
    const { container } = render(
      <RankDecompositionCards
        composite_score="78.4"
        components={[]}
        rank_in_category={12}
        category_size={89}
      />,
    )

    // Hero strip should exist
    expect(screen.getByText('Composite')).toBeInTheDocument()

    // No cards rendered
    const cards = container.querySelectorAll('[aria-label*="score"]')
    expect(cards).toHaveLength(0)

    // No card grid container
    const cardGrid = container.querySelector('.flex.flex-wrap.gap-3')
    expect(cardGrid).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Test 5: Composite + rank hero text appears verbatim
// ---------------------------------------------------------------------------

describe('RankDecompositionCards — hero strip text', () => {
  it('renders "78.4 · Composite · Rank 12th of 89" in hero strip', () => {
    render(
      <RankDecompositionCards
        composite_score="78.4"
        components={DEFAULT_COMPONENTS}
        rank_in_category={12}
        category_size={89}
      />,
    )

    // Composite score appears
    expect(screen.getByText('78.4')).toBeInTheDocument()
    // "Composite" label
    expect(screen.getByText('Composite')).toBeInTheDocument()
    // Rank text
    expect(screen.getByText('Rank 12th of 89')).toBeInTheDocument()
  })

  it('uses correct ordinal suffix for rank', () => {
    render(
      <RankDecompositionCards
        composite_score="60.0"
        components={[]}
        rank_in_category={1}
        category_size={50}
      />,
    )
    expect(screen.getByText('Rank 1st of 50')).toBeInTheDocument()
  })
})
