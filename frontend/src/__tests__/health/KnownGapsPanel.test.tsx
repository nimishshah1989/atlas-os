// Tests for src/components/health/KnownGapsPanel.tsx
// Verifies the honest known-gaps block renders all required sections and
// does not present stale items as green/OK.

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { KnownGapsPanel } from '@/components/health/KnownGapsPanel'

describe('KnownGapsPanel — structure', () => {
  it('renders the known data gaps heading', () => {
    render(<KnownGapsPanel />)
    expect(screen.getByText(/known data gaps/i)).toBeTruthy()
  })

  it('renders the last reviewed date', () => {
    render(<KnownGapsPanel />)
    expect(screen.getByText(/2026-05-20/)).toBeTruthy()
  })

  it('renders the introductory honesty note', () => {
    render(<KnownGapsPanel />)
    expect(screen.getByText(/no item is presented as green when it is not/i)).toBeTruthy()
  })
})

describe('KnownGapsPanel — holdings ingestion gap', () => {
  it('renders the holdings ingestion stale entry', () => {
    render(<KnownGapsPanel />)
    expect(screen.getByText(/monthly holdings ingestion/i)).toBeTruthy()
  })

  it('calls out de_mf_holdings', () => {
    render(<KnownGapsPanel />)
    expect(screen.getByText(/de_mf_holdings/)).toBeTruthy()
  })

  it('calls out de_etf_holdings', () => {
    render(<KnownGapsPanel />)
    expect(screen.getByText(/de_etf_holdings/)).toBeTruthy()
  })

  it('mentions the approximate stale date 2026-05-04', () => {
    render(<KnownGapsPanel />)
    expect(screen.getByText(/2026-05-04/)).toBeTruthy()
  })

  it('labels the holdings gap as STALE', () => {
    render(<KnownGapsPanel />)
    const staleLabels = screen.getAllByText('STALE')
    expect(staleLabels.length).toBeGreaterThanOrEqual(1)
  })
})

describe('KnownGapsPanel — adjustment factors gap', () => {
  it('renders the adjustment factors stale entry', () => {
    render(<KnownGapsPanel />)
    expect(screen.getByText(/adjustment factors/i)).toBeTruthy()
  })

  it('calls out de_adjustment_factors_daily', () => {
    render(<KnownGapsPanel />)
    expect(screen.getByText(/de_adjustment_factors_daily/)).toBeTruthy()
  })

  it('mentions 26 days stale', () => {
    render(<KnownGapsPanel />)
    const matches = screen.getAllByText(/26 days/)
    expect(matches.length).toBeGreaterThanOrEqual(1)
  })
})

describe('KnownGapsPanel — engine coverage (honest OK)', () => {
  it('renders the v2 state engine coverage entry', () => {
    render(<KnownGapsPanel />)
    expect(screen.getByText(/v2 state engine/i)).toBeTruthy()
  })

  it('states classified daily and current to T-1', () => {
    render(<KnownGapsPanel />)
    expect(screen.getByText(/current to the previous trading day \(T-1\)/i)).toBeTruthy()
  })

  it('labels the engine coverage entry as OK', () => {
    render(<KnownGapsPanel />)
    const okLabels = screen.getAllByText('OK')
    expect(okLabels.length).toBeGreaterThanOrEqual(1)
  })
})

describe('KnownGapsPanel — validator role', () => {
  it('renders the data validator entry', () => {
    render(<KnownGapsPanel />)
    expect(screen.getByText(/Data Validator — nightly automated audit/)).toBeTruthy()
  })

  it('lists all six issue classes by name', () => {
    render(<KnownGapsPanel />)
    const text = document.body.textContent ?? ''
    expect(text).toContain('gaps')
    expect(text).toContain('inconsistencies')
    expect(text).toContain('calculation errors')
    expect(text).toContain('accuracy errors')
    expect(text).toContain('insensible values')
    expect(text).toContain('incomplete data')
  })
})

describe('KnownGapsPanel — C5 honesty check (no fake green on stale items)', () => {
  it('stale items carry STALE label, not OK', () => {
    render(<KnownGapsPanel />)
    // The holdings entry must be STALE; ensure we never see its title paired with "OK" text
    // We check that both stale labels exist and the count of OK labels is exactly 2
    const staleLabels = screen.getAllByText('STALE')
    const okLabels = screen.getAllByText('OK')
    // 2 STALE entries (holdings + adjustment factors), 2 OK entries (engine + validator)
    expect(staleLabels.length).toBe(2)
    expect(okLabels.length).toBe(2)
  })
})
