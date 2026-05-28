import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FundLens2 } from '../FundLens2'
import type { FundLensRow } from '@/lib/queries/funds'

const FULL_LENS: FundLensRow = {
  aligned_aum_pct: '60',
  avoid_aum_pct: '10',
  neutral_aum_pct: '30',
  strong_aum_pct: '55',
  weak_aum_pct: '15',
  unknown_aum_pct: '30',
  sector_concentration: null,
  holdings_concentration: null,
  last_disclosed_date: new Date('2026-04-30'),
  as_of_date: new Date('2026-04-30'),
}

describe('FundLens2', () => {
  it('renders Composition Lens title', () => {
    render(<FundLens2 lens={FULL_LENS} performanceGate={true} sectorsGate={true} />)
    expect(screen.getByText(/Composition Lens/)).toBeInTheDocument()
  })

  it('shows N/A bar when lens is null', () => {
    render(<FundLens2 lens={null} performanceGate={null} sectorsGate={null} />)
    expect(screen.getByText(/No portfolio disclosure available/)).toBeInTheDocument()
    expect(screen.getByLabelText(/no portfolio disclosure available/i)).toBeInTheDocument()
  })

  it('shows N/A when aligned_aum_pct is null', () => {
    const lens = { ...FULL_LENS, aligned_aum_pct: null }
    render(<FundLens2 lens={lens} performanceGate={true} sectorsGate={true} />)
    expect(screen.getByText(/No portfolio disclosure available/)).toBeInTheDocument()
  })

  it('renders Performance + Sectors gates as ✓ when passing', () => {
    render(<FundLens2 lens={FULL_LENS} performanceGate={true} sectorsGate={true} />)
    expect(screen.getByText('Performance')).toBeInTheDocument()
    expect(screen.getByText('Sectors')).toBeInTheDocument()
    const checks = screen.getAllByText('✓')
    expect(checks.length).toBe(2)
  })

  it('renders ✗ for failed gates and ? for null gates', () => {
    render(<FundLens2 lens={FULL_LENS} performanceGate={false} sectorsGate={null} />)
    expect(screen.getByText('✗')).toBeInTheDocument()
    expect(screen.getByText('?')).toBeInTheDocument()
  })
})
