// frontend/src/components/v6/__tests__/RegimeHero.test.tsx
//
// 5 test cases for RegimeHero:
//   1. Renders all 4 hero numbers when data is full
//   2. Null flip_probability_5d → renders "—"
//   3. Cautious regime label: renders without error
//   4. days_in_regime visible
//   5. Journey strip visible (12 weeks of segments)

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RegimeHero } from '../RegimeHero'
import type { RegimeDetail } from '@/lib/queries/v6/regime'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeJourney(n: number, state = 'Constructive') {
  // Produce unique dates by offsetting from a base date
  const base = new Date('2026-01-01')
  return Array.from({ length: n }, (_, i) => {
    const d = new Date(base)
    d.setDate(base.getDate() + i)
    return {
      date: d.toISOString().slice(0, 10),
      regime_state: state,
    }
  })
}

const FULL_DETAIL: RegimeDetail = {
  regime_state: 'Constructive',
  deployment_multiplier: '0.7000',
  days_in_regime: 14,
  flip_probability_5d: '0.124',
  journey: makeJourney(84),
  inputs: [],
  as_of: '2026-05-22',
}

const NULL_FLIP_DETAIL: RegimeDetail = {
  ...FULL_DETAIL,
  flip_probability_5d: null,
}

const CAUTIOUS_DETAIL: RegimeDetail = {
  regime_state: 'Cautious',
  deployment_multiplier: '0.4000',
  days_in_regime: 7,
  flip_probability_5d: null,
  journey: makeJourney(20, 'Cautious'),
  inputs: [],
  as_of: '2026-05-22',
}

const ZERO_DAYS_DETAIL: RegimeDetail = {
  ...FULL_DETAIL,
  days_in_regime: 0,
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RegimeHero', () => {
  it('renders all 4 hero numbers when data is full', () => {
    render(<RegimeHero detail={FULL_DETAIL} />)

    // Regime label — may appear in heading + legend; at least one instance
    expect(screen.getAllByText('Constructive').length).toBeGreaterThanOrEqual(1)

    // Deployment multiplier — formatted as "0.7×"
    expect(screen.getByText('0.7×')).toBeInTheDocument()

    // Days in regime
    expect(screen.getByText('14')).toBeInTheDocument()

    // Flip probability — "0.124" → "12.4%"
    expect(screen.getByText('12.4%')).toBeInTheDocument()
  })

  it('renders "—" when flip_probability_5d is null', () => {
    render(<RegimeHero detail={NULL_FLIP_DETAIL} />)

    // The "—" should appear for flip probability cell
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThanOrEqual(1)

    // Deployment is still shown
    expect(screen.getByText('0.7×')).toBeInTheDocument()
  })

  it('renders Cautious regime without error', () => {
    // Should not throw — Cautious is a real pre-v6 label
    const { container } = render(<RegimeHero detail={CAUTIOUS_DETAIL} />)

    // "Cautious" appears in heading + legend; at least one instance
    expect(screen.getAllByText('Cautious').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('0.4×')).toBeInTheDocument()
    expect(container.firstChild).not.toBeNull()
  })

  it('renders days_in_regime value visibly', () => {
    render(<RegimeHero detail={FULL_DETAIL} />)

    // The number "14" should be rendered
    expect(screen.getByText('14')).toBeInTheDocument()
  })

  it('renders journey strip with 84 segments visible', () => {
    render(<RegimeHero detail={FULL_DETAIL} />)

    // Journey strip: aria-label should describe it
    const strip = screen.getByRole('img', { name: /12-week regime journey/i })
    expect(strip).toBeInTheDocument()

    // Each journey point renders as a child div
    const segments = strip.querySelectorAll('div')
    expect(segments.length).toBe(84)
  })
})
