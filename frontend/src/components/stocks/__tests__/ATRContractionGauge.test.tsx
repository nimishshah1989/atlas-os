import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ATRContractionGauge } from '../ATRContractionGauge'
import type { ATRContraction } from '@/lib/queries/stocks'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeData(ratio: number): ATRContraction {
  return {
    atr_14_current:  ratio * 10,
    atr_14_252d_avg: 10,
    ratio,
  }
}

// ---------------------------------------------------------------------------
// Test 1: ratio < 1.0 — contracting, positive color class
// ---------------------------------------------------------------------------

describe('ATRContractionGauge — contracting (ratio < 1.0)', () => {
  it('renders the section heading', () => {
    render(<ATRContractionGauge data={makeData(0.75)} />)
    expect(screen.getByTestId('atr-gauge')).toBeInTheDocument()
    expect(screen.getByText(/Volatility contraction/i)).toBeInTheDocument()
  })

  it('renders the ratio value as 0.75', () => {
    render(<ATRContractionGauge data={makeData(0.75)} />)
    expect(screen.getByTestId('atr-ratio')).toHaveTextContent('0.75')
  })

  it('renders signal-pos class when ratio < 1.0', () => {
    render(<ATRContractionGauge data={makeData(0.75)} />)
    expect(screen.getByTestId('atr-ratio').className).toContain('text-signal-pos')
  })

  it('renders contracting label', () => {
    render(<ATRContractionGauge data={makeData(0.75)} />)
    // "contracting" appears in both the inline label and the footnote — check at least one
    expect(screen.getAllByText(/contracting/i).length).toBeGreaterThan(0)
  })

  it('renders the gauge track and fill', () => {
    render(<ATRContractionGauge data={makeData(0.75)} />)
    expect(screen.getByTestId('atr-gauge-track')).toBeInTheDocument()
    const fill = screen.getByTestId('atr-gauge-fill')
    // 0.75 / 2.0 * 100 = 37.5%
    expect(fill.style.width).toBe('37.5%')
  })
})

// ---------------------------------------------------------------------------
// Test 2: null data — unavailable placeholder
// ---------------------------------------------------------------------------

describe('ATRContractionGauge — null data', () => {
  it('renders unavailable placeholder when data is null', () => {
    render(<ATRContractionGauge data={null} />)
    expect(screen.getByText(/ATR contraction data unavailable/i)).toBeInTheDocument()
  })

  it('does not render the gauge track when data is null', () => {
    render(<ATRContractionGauge data={null} />)
    expect(screen.queryByTestId('atr-gauge-track')).not.toBeInTheDocument()
  })
})
