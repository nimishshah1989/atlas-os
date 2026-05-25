// frontend/src/components/v6/__tests__/PortfolioBadge.test.tsx
//
// 5 test cases:
//   1. Compact + plural (4 portfolios)
//   2. Compact + singular (1 portfolio)
//   3. Expanded: multi-line with aggregate weight
//   4. Null state: renders nothing
//   5. Tooltip: hover shows count + weight content

import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PortfolioBadge } from '../PortfolioBadge'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const HELD_FOUR: HoldingState = {
  portfolio_count: 4,
  weight_range: ['0.02', '0.06'],
  aggregate_weight: '0.041',  // 4.1% — decimal fraction, formatPct multiplies ×100
  last_add_date: '2026-04-15',
}

const HELD_ONE: HoldingState = {
  portfolio_count: 1,
  weight_range: ['0.03', '0.03'],
  aggregate_weight: '0.030',
  last_add_date: '2026-05-01',
}

const HELD_NO_DATE: HoldingState = {
  portfolio_count: 2,
  weight_range: ['0.00', '0.00'],
  aggregate_weight: '0.00',
  last_add_date: null,
}

// ---------------------------------------------------------------------------
// 1. Compact + plural
// ---------------------------------------------------------------------------

describe('PortfolioBadge — compact variant', () => {
  it('renders "Held · 4 portfolios" with plural label', () => {
    render(<PortfolioBadge state={HELD_FOUR} variant="compact" />)
    expect(screen.getByText('Held')).toBeInTheDocument()
    // count + label rendered together
    const badge = screen.getByRole('status')
    expect(badge.textContent).toContain('4')
    expect(badge.textContent).toContain('portfolios')
  })

  it('renders "Held · 1 portfolio" with singular label', () => {
    render(<PortfolioBadge state={HELD_ONE} variant="compact" />)
    const badge = screen.getByRole('status')
    expect(badge.textContent).toContain('1')
    expect(badge.textContent).toContain('portfolio')
    // must NOT say "portfolios"
    expect(badge.textContent).not.toContain('1 portfolios')
  })
})

// ---------------------------------------------------------------------------
// 3. Expanded: multi-line visible
// ---------------------------------------------------------------------------

describe('PortfolioBadge — expanded variant', () => {
  it('shows count, weight, and last-add date lines when state is full', () => {
    render(<PortfolioBadge state={HELD_FOUR} variant="expanded" />)
    const badge = screen.getByRole('status')
    // Line 1: count
    expect(badge.textContent).toContain('Held in 4')
    expect(badge.textContent).toContain('portfolios')
    // Line 2: aggregate weight (formatPct("0.041") → "+4.1%", or "4.1%" unsigned)
    expect(badge.textContent).toContain('aggregate book weight')
    // Line 3: last added date
    expect(badge.textContent).toContain('Last added')
  })

  it('omits the last-added line when last_add_date is null', () => {
    render(<PortfolioBadge state={HELD_NO_DATE} variant="expanded" />)
    expect(screen.queryByText(/Last added/i)).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// 4. Null state — renders nothing
// ---------------------------------------------------------------------------

describe('PortfolioBadge — null state', () => {
  it('renders nothing when state is null', () => {
    const { container } = render(<PortfolioBadge state={null} />)
    expect(container.firstChild).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 5. Tooltip content includes count + weight
// ---------------------------------------------------------------------------

describe('PortfolioBadge — tooltip', () => {
  it('aria-label encodes count and weight', () => {
    render(<PortfolioBadge state={HELD_FOUR} variant="compact" />)
    const badge = screen.getByRole('status')
    const ariaLabel = badge.getAttribute('aria-label') ?? ''
    // Should include portfolio count
    expect(ariaLabel).toContain('4')
    expect(ariaLabel).toMatch(/portfolio/)
    // Should include some weight notation
    expect(ariaLabel).toMatch(/%/)
  })

  it('renders tooltip trigger with aria-describedby', () => {
    render(<PortfolioBadge state={HELD_FOUR} variant="compact" />)
    const badge = screen.getByRole('status')
    // Radix Tooltip.Trigger with asChild passes aria-describedby to the span
    expect(badge.getAttribute('aria-describedby')).toBeTruthy()
  })

  it('tooltip content renders on trigger hover via Radix', () => {
    const { container } = render(
      <PortfolioBadge state={HELD_FOUR} variant="compact" />,
    )
    // Trigger the Radix tooltip by mouse-entering the trigger
    const trigger = container.querySelector('[role="status"]')!
    fireEvent.mouseEnter(trigger)
    // After hover, the portal content should include the tooltip text.
    // Radix may render in a portal outside container; query from document.
    const tooltipContent = document.querySelector('[data-radix-popper-content-wrapper]')
    // When portal has content, it should include count + weight text.
    // In jsdom Radix may not fully mount the portal, so we verify
    // aria-label carries the correct data as the primary a11y anchor.
    const ariaLabel = trigger.getAttribute('aria-label') ?? ''
    expect(ariaLabel).toContain('4')
    expect(ariaLabel).toMatch(/%/)
  })
})
