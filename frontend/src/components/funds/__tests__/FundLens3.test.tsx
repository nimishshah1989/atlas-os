import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FundLens3 } from '../FundLens3'
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

describe('FundLens3', () => {
  it('renders Holdings Lens title', () => {
    render(<FundLens3 lens={FULL_LENS} stocksGate={true} marketGate={true} />)
    expect(screen.getByText(/Holdings Lens/)).toBeInTheDocument()
  })

  it('shows holdings-disclosure copy when lens is null', () => {
    render(<FundLens3 lens={null} stocksGate={null} marketGate={null} />)
    expect(screen.getByText(/No holdings disclosure available/)).toBeInTheDocument()
  })

  it('shows N/A when strong_aum_pct is null', () => {
    const lens = { ...FULL_LENS, strong_aum_pct: null }
    render(<FundLens3 lens={lens} stocksGate={true} marketGate={true} />)
    expect(screen.getByText(/No holdings disclosure available/)).toBeInTheDocument()
  })

  it('renders Stocks + Market gates', () => {
    render(<FundLens3 lens={FULL_LENS} stocksGate={true} marketGate={true} />)
    expect(screen.getByText('Stocks')).toBeInTheDocument()
    expect(screen.getByText('Market')).toBeInTheDocument()
  })

  it('renders ✗ for failed gate', () => {
    render(<FundLens3 lens={FULL_LENS} stocksGate={true} marketGate={false} />)
    expect(screen.getByText('✗')).toBeInTheDocument()
  })
})
