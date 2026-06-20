import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SectorLensHeatmap } from '../SectorLensHeatmap'

const VECTORS = [
  { sector: 'Energy', technical: 65, fundamental: 58, valuation: 42, catalyst: 50, flow: 72, policy: 60, composite: 58.5, stock_count: 25 },
  { sector: 'IT', technical: 55, fundamental: 70, valuation: 38, catalyst: 45, flow: 60, policy: 40, composite: 51.3, stock_count: 40 },
]

describe('SectorLensHeatmap', () => {
  it('renders sector names as links', () => {
    render(<SectorLensHeatmap vectors={VECTORS} />)
    const link = screen.getByRole('link', { name: 'Energy' })
    expect(link.getAttribute('href')).toBe('/sectors/Energy')
  })

  it('renders composite scores', () => {
    render(<SectorLensHeatmap vectors={VECTORS} />)
    expect(screen.getByText('58.5')).toBeDefined()
    expect(screen.getByText('51.3')).toBeDefined()
  })

  it('renders stock counts', () => {
    render(<SectorLensHeatmap vectors={VECTORS} />)
    expect(screen.getByText('25')).toBeDefined()
    // "40" appears in both stock_count and policy score; just verify at least one renders
    expect(screen.getAllByText('40').length).toBeGreaterThanOrEqual(1)
  })

  it('returns null for empty vectors', () => {
    const { container } = render(<SectorLensHeatmap vectors={[]} />)
    expect(container.innerHTML).toBe('')
  })
})
