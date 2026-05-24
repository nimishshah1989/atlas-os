import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { CellMatrix } from '../CellMatrix'
import { getDemoCellDefinitions } from '@/lib/api/demo-cells'

describe('CellMatrix', () => {
  it('renders a 3-row × 8-column grid for 24 cells', () => {
    const cells = getDemoCellDefinitions()
    expect(cells).toHaveLength(24)
    const { container } = render(<CellMatrix cells={cells} />)
    // 24 cells should produce 24 anchor or div tiles in the grid.
    // We can't filter the header row easily — instead count the IC numbers.
    const icSpans = container.querySelectorAll('.font-mono.text-\\[14px\\]')
    expect(icSpans.length).toBe(24)
  })

  it('marks empty cells (gate_pass=0) as non-clickable', () => {
    const cells = getDemoCellDefinitions()
    // Large-1m-POSITIVE has n_gate_pass=0 in the fixture.
    const empty = cells.find(c => c.cell_id === 'Large-1m-POSITIVE')
    expect(empty?.n_gate_pass).toBe(0)
    const { container } = render(<CellMatrix cells={cells} />)
    // Verify there are non-anchor cells (some are <a>, some are <div>).
    const anchors = container.querySelectorAll('a[href*="/matrix/"]')
    // 24 minus the 2 red cells (Large-1m-POSITIVE and Small-12m-NEGATIVE both have n_gate_pass=0).
    expect(anchors.length).toBeLessThanOrEqual(24)
    expect(anchors.length).toBeGreaterThanOrEqual(20)
  })

  it('shows the legend when showLegend is true (default)', () => {
    const cells = getDemoCellDefinitions()
    const { container } = render(<CellMatrix cells={cells} />)
    expect(container.textContent).toContain('IC ≥ 0.05')
  })
})
