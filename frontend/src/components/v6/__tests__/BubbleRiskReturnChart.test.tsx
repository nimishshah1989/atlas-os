// frontend/src/components/v6/__tests__/BubbleRiskReturnChart.test.tsx
//
// 4 test cases:
//   1. Multiple bubbles: 10 data points → 10 roster items rendered
//   2. Empty data: shows "No data available" — no synthetic bubbles
//   3. highlightId match: matching roster item carries data-id
//   4. State→color mapping: POSITIVE legend uses signal-pos background color

import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { BubbleRiskReturnChart } from '../BubbleRiskReturnChart'
import type { BubbleDatum } from '../BubbleRiskReturnChart'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeDatum(
  i: number,
  state: BubbleDatum['state'] = 'POSITIVE',
): BubbleDatum {
  return {
    id:    `stock-${i}`,
    label: `STOCK${i}`,
    risk:  String(10 + i * 2),
    ret:   String(-5 + i * 3),
    size:  String(1_000_000 * (i + 1)),
    state,
  }
}

const TEN_POINTS: BubbleDatum[] = Array.from({ length: 10 }, (_, i) => makeDatum(i))

const MIXED_STATES: BubbleDatum[] = [
  { id: 'pos-1', label: 'POS1', risk: '15', ret: '12',  size: '500000', state: 'POSITIVE' },
  { id: 'pos-2', label: 'POS2', risk: '12', ret: '18',  size: '800000', state: 'POSITIVE' },
  { id: 'neu-1', label: 'NEU1', risk: '20', ret: '2',   size: '300000', state: 'NEUTRAL'  },
  { id: 'neg-1', label: 'NEG1', risk: '30', ret: '-10', size: '200000', state: 'NEGATIVE' },
]

// ---------------------------------------------------------------------------
// Test 1: Multiple bubbles render
// ---------------------------------------------------------------------------

describe('BubbleRiskReturnChart — multiple bubbles', () => {
  it('renders 10 roster items for 10 data points', () => {
    const { getByTestId } = render(<BubbleRiskReturnChart data={TEN_POINTS} />)
    const roster = getByTestId('bubble-roster')
    // aria-hidden hides from role queries; use querySelectorAll directly
    const items = roster.querySelectorAll('[data-id]')
    expect(items.length).toBe(10)
  })

  it('renders chart container (not empty state) with 10 items', () => {
    render(<BubbleRiskReturnChart data={TEN_POINTS} />)
    // Empty state text must NOT appear
    expect(screen.queryByText('No data available')).toBeNull()
    // Legend count text is present
    expect(
      screen.getByText(/10 instruments/),
    ).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 2: Empty data → "No data available"
// ---------------------------------------------------------------------------

describe('BubbleRiskReturnChart — empty state', () => {
  it('shows "No data available" when data is empty', () => {
    render(<BubbleRiskReturnChart data={[]} />)
    expect(screen.getByText('No data available')).toBeInTheDocument()
  })

  it('does not render any roster items when data is empty', () => {
    const { container } = render(<BubbleRiskReturnChart data={[]} />)
    // No bubble-roster (it's inside the non-empty branch)
    expect(container.querySelector('[data-testid="bubble-roster"]')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Test 3: highlightId → roster item carries matching data-id
// ---------------------------------------------------------------------------

describe('BubbleRiskReturnChart — highlightId', () => {
  it('roster contains an item with the highlighted id', () => {
    const { getByTestId } = render(
      <BubbleRiskReturnChart data={MIXED_STATES} highlightId="pos-1" />,
    )
    const roster = getByTestId('bubble-roster')
    const highlighted = roster.querySelector('[data-id="pos-1"]')
    expect(highlighted).not.toBeNull()
  })

  it('aria-label on highlighted item includes expected fields', () => {
    const { getByTestId } = render(
      <BubbleRiskReturnChart data={MIXED_STATES} highlightId="pos-1" />,
    )
    const roster = getByTestId('bubble-roster')
    const item = roster.querySelector('[data-id="pos-1"]')!
    const label = item.getAttribute('aria-label')!
    expect(label).toContain('POS1')
    expect(label).toContain('risk 15')
    expect(label).toContain('return 12')
    expect(label).toContain('state POSITIVE')
  })
})

// ---------------------------------------------------------------------------
// Test 4: State → color mapping via legend
// ---------------------------------------------------------------------------

describe('BubbleRiskReturnChart — state→color', () => {
  it('POSITIVE legend dot uses signal-pos background (#2F6B43)', () => {
    const { container } = render(
      <BubbleRiskReturnChart data={MIXED_STATES} />,
    )
    // Legend dot for POSITIVE is a div with inline background style
    const dots = container.querySelectorAll('.rounded-full[style]')
    const positiveDoc = Array.from(dots).find(
      d => (d as HTMLElement).style.background.includes('47, 107, 67')
        || (d as HTMLElement).style.background.includes('#2F6B43')
        || (d as HTMLElement).getAttribute('style')?.includes('2F6B43')
        || (d as HTMLElement).getAttribute('style')?.includes('47, 107, 67'),
    )
    expect(positiveDoc).toBeDefined()
  })

  it('roster items carry correct data-state attributes', () => {
    const { getByTestId } = render(
      <BubbleRiskReturnChart data={MIXED_STATES} />,
    )
    const roster = getByTestId('bubble-roster')
    const posItems = roster.querySelectorAll('[data-state="POSITIVE"]')
    const negItems = roster.querySelectorAll('[data-state="NEGATIVE"]')
    expect(posItems.length).toBe(2)
    expect(negItems.length).toBe(1)
  })

  it('legend shows all three state labels', () => {
    render(<BubbleRiskReturnChart data={MIXED_STATES} />)
    expect(screen.getByText('positive')).toBeInTheDocument()
    expect(screen.getByText('neutral')).toBeInTheDocument()
    expect(screen.getByText('negative')).toBeInTheDocument()
  })
})
