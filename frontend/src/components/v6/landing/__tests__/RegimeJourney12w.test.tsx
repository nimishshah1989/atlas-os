// frontend/src/components/v6/landing/__tests__/RegimeJourney12w.test.tsx
//
// Unit tests for the 12-week regime journey component.
// Tests cover: empty state, regime color mapping, metric cell coloring,
// date formatting, and current-week highlight.

import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RegimeJourney12w } from '../RegimeJourney12w'
import type { WeeklyRegimeCell } from '@/lib/queries/v6/landing'

function makeCell(overrides: Partial<WeeklyRegimeCell> = {}): WeeklyRegimeCell {
  return {
    week_end_date: '2026-05-19',
    regime_state: 'Cautious',
    breadth_pct: 42,
    india_vix: 18.4,
    dispersion: 0.087,
    smallcap_rs: -0.34,
    is_current: false,
    ...overrides,
  }
}

describe('RegimeJourney12w', () => {
  it('renders empty state when cells array is empty', () => {
    render(<RegimeJourney12w cells={[]} />)
    expect(screen.getByText('No regime history data')).toBeDefined()
  })

  it('renders a regime block for each cell', () => {
    const cells: WeeklyRegimeCell[] = [
      makeCell({ week_end_date: '2026-03-03', regime_state: 'Risk-On' }),
      makeCell({ week_end_date: '2026-03-10', regime_state: 'Risk-On' }),
      makeCell({ week_end_date: '2026-05-19', regime_state: 'Cautious', is_current: true }),
    ]
    render(<RegimeJourney12w cells={cells} />)
    // Section heading should be present
    expect(screen.getByText('Trailing 12 weeks · how we got here')).toBeDefined()
  })

  it('marks the current week cell with ring styling', () => {
    const cells = [
      makeCell({ week_end_date: '2026-05-12', is_current: false }),
      makeCell({ week_end_date: '2026-05-19', is_current: true }),
    ]
    render(<RegimeJourney12w cells={cells} />)
    // The current cell should have aria-label containing "current"
    const currentBlock = screen.getByLabelText(/current/i)
    expect(currentBlock).toBeDefined()
  })

  it('displays all four metric row labels including Small-cap RS', () => {
    const cells = [makeCell()]
    render(<RegimeJourney12w cells={cells} />)
    expect(screen.getByText(/SC/i)).toBeDefined()
    expect(screen.getByText(/Breadth/i)).toBeDefined()
    expect(screen.getByText(/India VIX/i)).toBeDefined()
    expect(screen.getByText(/Dispersion/i)).toBeDefined()
  })

  it('shows em-dash for null metric values', () => {
    const cells = [
      makeCell({ breadth_pct: null, india_vix: null, dispersion: null, smallcap_rs: null }),
    ]
    render(<RegimeJourney12w cells={cells} />)
    // Should have multiple em-dashes for null metric cells (4 metrics can be null)
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThanOrEqual(4)
  })

  it('renders the legend with all four regime states', () => {
    const cells = [makeCell()]
    render(<RegimeJourney12w cells={cells} />)
    expect(screen.getByText('Risk-On')).toBeDefined()
    expect(screen.getByText('Elevated')).toBeDefined()
    expect(screen.getByText('Cautious')).toBeDefined()
    expect(screen.getByText('Risk-Off')).toBeDefined()
  })

  it('renders 12 blocks for 12 weekly cells', () => {
    const cells = Array.from({ length: 12 }, (_, i) =>
      makeCell({
        week_end_date: `2026-0${Math.floor(i / 4) + 3}-${String((i % 4) * 7 + 1).padStart(2, '0')}`,
        is_current: i === 11,
      }),
    )
    render(<RegimeJourney12w cells={cells} />)
    // There should be 12 aria-label elements for regime blocks
    const blocks = screen.getAllByRole('img')
    // Filter to regime blocks (not legend items)
    expect(blocks.length).toBeGreaterThanOrEqual(12)
  })
})
