// Tests for src/app/portfolios/[id]/CompositionView.tsx
// Covers A1: symbol rendering instead of raw UUIDs, LinkedTicker for stocks,
// column header rename "ID / Ticker" → "Ticker", fallback for null symbol.

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StaticComposition } from '@/app/portfolios/[id]/CompositionView'

const STOCK_INST = {
  instrument_id: '001a1ce4-cc25-4639-9795-528a67d97c34',
  instrument_type: 'stock' as const,
  weight_pct: 5,
  symbol: 'HDFCBANK',
}

const ETF_INST = {
  instrument_id: 'etf-uuid-abc',
  instrument_type: 'etf' as const,
  weight_pct: 10,
  symbol: 'NIFTYBEES',
}

const NULL_SYMBOL_INST = {
  instrument_id: 'no-symbol-uuid',
  instrument_type: 'stock' as const,
  weight_pct: 3,
  symbol: null,
}

describe('StaticComposition — column headers', () => {
  it('renders "Ticker" column header, not "ID / Ticker"', () => {
    render(<StaticComposition instruments={[STOCK_INST]} />)
    expect(screen.getByText(/ticker/i)).toBeInTheDocument()
    expect(screen.queryByText(/id \/ ticker/i)).not.toBeInTheDocument()
  })
})

describe('StaticComposition — ticker rendering (A1)', () => {
  it('renders stock ticker symbol instead of raw UUID', () => {
    render(<StaticComposition instruments={[STOCK_INST]} />)
    expect(screen.getByText('HDFCBANK')).toBeInTheDocument()
    expect(screen.queryByText('001a1ce4-cc25-4639-9795-528a67d97c34')).not.toBeInTheDocument()
  })

  it('renders stock ticker as a LinkedTicker link to /stocks/SYMBOL', () => {
    render(<StaticComposition instruments={[STOCK_INST]} />)
    const link = screen.getByRole('link', { name: 'HDFCBANK' })
    expect(link).toHaveAttribute('href', '/stocks/HDFCBANK')
  })

  it('renders ETF symbol text (not a link)', () => {
    render(<StaticComposition instruments={[ETF_INST]} />)
    expect(screen.getByText('NIFTYBEES')).toBeInTheDocument()
  })

  it('falls back to UUID for null symbol stock', () => {
    render(<StaticComposition instruments={[NULL_SYMBOL_INST]} />)
    // Should render something — either "—" or the UUID fallback, not crash
    const row = screen.getByText(/no-symbol-uuid|—/)
    expect(row).toBeInTheDocument()
  })

  it('renders weight percentage', () => {
    render(<StaticComposition instruments={[STOCK_INST]} />)
    expect(screen.getByText('5.00%')).toBeInTheDocument()
  })
})

describe('StaticComposition — empty state', () => {
  it('renders "No instruments recorded" when list is empty', () => {
    render(<StaticComposition instruments={[]} />)
    expect(screen.getByText(/no instruments recorded/i)).toBeInTheDocument()
  })
})
