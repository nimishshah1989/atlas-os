import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

// Recharts uses browser APIs. Mock the entire module so tests run in jsdom.
vi.mock('recharts', () => {
  const React = require('react')
  const passthrough = ({ children }: { children?: React.ReactNode }) =>
    React.createElement('div', {}, children)
  return {
    LineChart:         passthrough,
    Line:              () => null,
    XAxis:             () => null,
    YAxis:             () => null,
    Tooltip:           () => null,
    ResponsiveContainer: passthrough,
    ReferenceLine:     () => null,
  }
})

import { OBVContinuousChart } from '../OBVContinuousChart'
import type { OBVPoint } from '@/lib/queries/stocks'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makePoint(i: number, obv: number): OBVPoint {
  return {
    date:   `2026-01-${String(i + 1).padStart(2, '0')}`,
    close:  100 + i,
    volume: 1_000_000,
    obv,
  }
}

function makeSeries(n: number): OBVPoint[] {
  // Rising OBV: obv = i * 1000
  return Array.from({ length: n }, (_, i) => makePoint(i, i * 1000))
}

// ---------------------------------------------------------------------------
// Test 1: happy path with 50 points
// ---------------------------------------------------------------------------

describe('OBVContinuousChart — happy path (50 points)', () => {
  it('renders the section heading', () => {
    render(<OBVContinuousChart series={makeSeries(50)} />)
    expect(screen.getByTestId('obv-chart')).toBeInTheDocument()
    expect(screen.getByText(/OBV trend/i)).toBeInTheDocument()
  })

  it('renders a positive slope as +value/day in signal-pos class', () => {
    render(<OBVContinuousChart series={makeSeries(50)} />)
    const slopeEl = screen.getByTestId('obv-slope')
    // Rising OBV series → positive slope
    expect(slopeEl.textContent).toMatch(/^\+/)
    expect(slopeEl.className).toContain('text-signal-pos')
  })

  it('renders accumulating label for positive slope', () => {
    render(<OBVContinuousChart series={makeSeries(50)} />)
    expect(screen.getByText('accumulating')).toBeInTheDocument()
  })

  it('renders negative slope in signal-neg class for falling OBV series', () => {
    // Falling series: obv = -i * 1000
    const falling = Array.from({ length: 50 }, (_, i) => makePoint(i, -i * 1000))
    render(<OBVContinuousChart series={falling} />)
    const slopeEl = screen.getByTestId('obv-slope')
    expect(slopeEl.className).toContain('text-signal-neg')
    expect(slopeEl.textContent).toMatch(/^-/)
  })
})

// ---------------------------------------------------------------------------
// Test 2: insufficient history placeholder
// ---------------------------------------------------------------------------

describe('OBVContinuousChart — insufficient history', () => {
  it('renders the insufficient-history placeholder when fewer than 14 points', () => {
    render(<OBVContinuousChart series={makeSeries(5)} />)
    expect(screen.getByText(/Insufficient history/i)).toBeInTheDocument()
  })

  it('does not render the slope annotation when fewer than 14 points', () => {
    render(<OBVContinuousChart series={makeSeries(5)} />)
    expect(screen.queryByTestId('obv-slope')).not.toBeInTheDocument()
  })
})
