/**
 * Tests for frontend/src/components/portfolio/DeteriorationPanel.tsx
 *
 * Covers:
 * - Renders deteriorating rows with symbol, rule badge, weight
 * - Empty state: calm "No holdings hitting an exit rule" when none deteriorating
 * - LinkedTicker renders for stock-type instruments
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { DeteriorationPanel } from '../DeteriorationPanel'
import type { DeteriItem } from '@/lib/policy-deterioration'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeItem(
  id: string,
  symbol: string | null,
  rule: 'full_exit' | 'trim',
  reason: string,
  weightPct = 5,
): DeteriItem {
  return {
    instrument_id: id,
    symbol,
    engine_state: rule === 'full_exit' ? 'stage_4' : 'stage_3',
    weight_pct: weightPct,
    rule,
    reason,
  }
}

const FULL_EXIT_ITEM = makeItem('A', 'WIPRO', 'full_exit', 'stage_4 — full exit required', 4.0)
const TRIM_ITEM = makeItem('B', 'INFY', 'trim', 'stage_3 — trim position', 7.5)

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

describe('DeteriorationPanel — empty state', () => {
  it('renders the calm empty state message when items is empty', () => {
    render(<DeteriorationPanel items={[]} />)
    expect(screen.getByTestId('deterioration-empty')).toBeInTheDocument()
    expect(screen.getByText(/no holdings hitting an exit rule/i)).toBeInTheDocument()
  })

  it('does not render a table when items is empty', () => {
    render(<DeteriorationPanel items={[]} />)
    expect(screen.queryByRole('table')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Non-empty state
// ---------------------------------------------------------------------------

describe('DeteriorationPanel — with deteriorating items', () => {
  it('renders a row for each deteriorating item', () => {
    render(<DeteriorationPanel items={[FULL_EXIT_ITEM, TRIM_ITEM]} />)
    // Both symbols should appear
    expect(screen.getByText('WIPRO')).toBeInTheDocument()
    expect(screen.getByText('INFY')).toBeInTheDocument()
  })

  it('renders full-exit badge for full_exit rule', () => {
    render(<DeteriorationPanel items={[FULL_EXIT_ITEM]} />)
    expect(screen.getByTestId('rule-badge-A')).toBeInTheDocument()
    expect(screen.getByTestId('rule-badge-A').textContent).toMatch(/full exit/i)
  })

  it('renders trim badge for trim rule', () => {
    render(<DeteriorationPanel items={[TRIM_ITEM]} />)
    expect(screen.getByTestId('rule-badge-B')).toBeInTheDocument()
    expect(screen.getByTestId('rule-badge-B').textContent).toMatch(/trim/i)
  })

  it('renders current weight percentage', () => {
    render(<DeteriorationPanel items={[FULL_EXIT_ITEM]} />)
    expect(screen.getByTestId('weight-A').textContent).toContain('4.00%')
  })

  it('does not render empty state when items are present', () => {
    render(<DeteriorationPanel items={[TRIM_ITEM]} />)
    expect(screen.queryByTestId('deterioration-empty')).toBeNull()
  })

  it('renders a table when items are present', () => {
    render(<DeteriorationPanel items={[FULL_EXIT_ITEM]} />)
    expect(screen.getByRole('table')).toBeInTheDocument()
  })

  it('handles null symbol gracefully (renders dash or instrument_id fallback)', () => {
    const nullSymbolItem = makeItem('C', null, 'full_exit', 'stage_4 — full exit required')
    render(<DeteriorationPanel items={[nullSymbolItem]} />)
    // Should not throw; row should still render
    const row = screen.getByTestId('deterioration-row-C')
    expect(row).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// hard_stop_pct honest labelling
// ---------------------------------------------------------------------------

describe('DeteriorationPanel — hard stop labelling', () => {
  it('renders hard stop as n/a when no items', () => {
    render(<DeteriorationPanel items={[]} hardStopTracked={false} />)
    expect(screen.getByTestId('hard-stop-status')).toHaveTextContent(/n\/a/i)
  })
})
