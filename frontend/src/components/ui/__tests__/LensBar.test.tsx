import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LensBar } from '@/components/ui/LensBar'

const segments = [
  { pct: 60, color: 'green' as const },
  { pct: 20, color: 'neutral' as const },
  { pct: 20, color: 'red' as const },
]

describe('LensBar', () => {
  it('renders N/A grey bar when nullish is true', () => {
    render(<LensBar segments={[]} label="Composition" nullish />)
    const bar = screen.getByRole('img')
    expect(bar).toHaveAttribute(
      'aria-label',
      expect.stringMatching(/no portfolio disclosure available/i),
    )
    expect(screen.getByText('N/A')).toBeInTheDocument()
  })

  it('renders normal bar with correct aria-label', () => {
    render(<LensBar segments={segments} label="Composition" />)
    const bar = screen.getByRole('img')
    expect(bar).toHaveAttribute('aria-label', expect.stringContaining('60% green'))
  })

  it('shows asOfDate text when provided', () => {
    render(<LensBar segments={segments} label="Holdings" asOfDate="01-May-2026" />)
    expect(screen.getByText('as of 01-May-2026')).toBeInTheDocument()
  })

  it('does not show asOfDate text when not provided', () => {
    const { queryByText } = render(<LensBar segments={segments} label="Holdings" />)
    expect(queryByText(/as of/i)).toBeNull()
  })

  it('segment widths sum to 100 after rounding adjustment', () => {
    // 33.33 + 33.33 + 33.34 → all round to 33 → total 99 → adjustment adds 1 to largest
    const uneven = [
      { pct: 33.33, color: 'green' as const },
      { pct: 33.33, color: 'neutral' as const },
      { pct: 33.34, color: 'red' as const },
    ]
    const { container } = render(<LensBar segments={uneven} label="Test" />)
    // Get all elements with inline style containing width
    const bars = container.querySelectorAll('[style*="width"]')
    const widths = Array.from(bars).map(b => parseInt((b as HTMLElement).style.width, 10))
    expect(widths.reduce((a, b) => a + b, 0)).toBe(100)
  })

  it('renders empty segments array as zero-width bars without crash', () => {
    // nullish=false but empty segments — should render without error
    expect(() => render(<LensBar segments={[]} label="Empty" />)).not.toThrow()
  })

  it('clamps negative pct to 0', () => {
    const negativeSeg = [
      { pct: -10, color: 'green' as const },
      { pct: 110, color: 'red' as const },
    ]
    const { container } = render(<LensBar segments={negativeSeg} label="Clamp" />)
    const bars = container.querySelectorAll('[style*="width"]')
    const widths = Array.from(bars).map(b => parseInt((b as HTMLElement).style.width, 10))
    widths.forEach(w => expect(w).toBeGreaterThanOrEqual(0))
  })
})
