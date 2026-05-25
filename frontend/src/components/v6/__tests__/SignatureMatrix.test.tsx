// frontend/src/components/v6/__tests__/SignatureMatrix.test.tsx
// 5 cases: grid render, color mapping, null exposure, tooltip, ARIA

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SignatureMatrix } from '../SignatureMatrix'
import type { SignatureCell } from '../SignatureMatrix'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ALL_CELLS: SignatureCell[] = [
  { factor: 'Value',    exposure: 'POSITIVE', raw_score: '0.18',  rank_in_category: 3  },
  { factor: 'Momentum', exposure: 'NEUTRAL',  raw_score: '0.02',  rank_in_category: 22 },
  { factor: 'Quality',  exposure: 'NEGATIVE', raw_score: '-0.14', rank_in_category: 67 },
  { factor: 'Size',     exposure: null,        raw_score: null,    rank_in_category: null },
]

// ---------------------------------------------------------------------------
// Case 1: Renders all input cells in a grid
// ---------------------------------------------------------------------------

describe('SignatureMatrix — renders all cells', () => {
  it('renders every factor name in the grid', () => {
    render(<SignatureMatrix cells={ALL_CELLS} asset_label="HDFC Flexi Cap Fund" />)
    expect(screen.getByText('Value')).toBeInTheDocument()
    expect(screen.getByText('Momentum')).toBeInTheDocument()
    expect(screen.getByText('Quality')).toBeInTheDocument()
    expect(screen.getByText('Size')).toBeInTheDocument()
  })

  it('renders exactly as many listitem tiles as input cells', () => {
    const { container } = render(
      <SignatureMatrix cells={ALL_CELLS} asset_label="HDFC Flexi Cap Fund" />,
    )
    const tiles = container.querySelectorAll('[role="listitem"]')
    expect(tiles).toHaveLength(4)
  })

  it('renders empty grid without crash when cells array is empty', () => {
    const { container } = render(
      <SignatureMatrix cells={[]} asset_label="Empty Fund" />,
    )
    const tiles = container.querySelectorAll('[role="listitem"]')
    expect(tiles).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Case 2: Color mapping — correct background class per exposure value
// ---------------------------------------------------------------------------

describe('SignatureMatrix — color mapping by exposure', () => {
  it('POSITIVE tile has signal-pos/5 background', () => {
    const { container } = render(
      <SignatureMatrix
        cells={[{ factor: 'Value', exposure: 'POSITIVE', raw_score: '0.18', rank_in_category: 3 }]}
        asset_label="Test"
      />,
    )
    const tile = container.querySelector('[role="listitem"]')!
    expect(tile.className).toContain('bg-signal-pos/5')
  })

  it('NEUTRAL tile has bg-paper border class', () => {
    const { container } = render(
      <SignatureMatrix
        cells={[{ factor: 'Momentum', exposure: 'NEUTRAL', raw_score: '0.02', rank_in_category: 22 }]}
        asset_label="Test"
      />,
    )
    const tile = container.querySelector('[role="listitem"]')!
    expect(tile.className).toContain('bg-paper')
  })

  it('NEGATIVE tile has signal-neg/5 background', () => {
    const { container } = render(
      <SignatureMatrix
        cells={[{ factor: 'Quality', exposure: 'NEGATIVE', raw_score: '-0.14', rank_in_category: 67 }]}
        asset_label="Test"
      />,
    )
    const tile = container.querySelector('[role="listitem"]')!
    expect(tile.className).toContain('bg-signal-neg/5')
  })

  it('null exposure tile has bg-paper-deep background', () => {
    const { container } = render(
      <SignatureMatrix
        cells={[{ factor: 'Size', exposure: null, raw_score: null, rank_in_category: null }]}
        asset_label="Test"
      />,
    )
    const tile = container.querySelector('[role="listitem"]')!
    expect(tile.className).toContain('bg-paper-deep')
  })

  it('exposure chip for POSITIVE shows "POSITIVE" text', () => {
    render(
      <SignatureMatrix
        cells={[{ factor: 'Value', exposure: 'POSITIVE', raw_score: '0.18', rank_in_category: 3 }]}
        asset_label="Test"
      />,
    )
    expect(screen.getByText('POSITIVE')).toBeInTheDocument()
  })

  it('exposure chip for NEGATIVE shows "NEGATIVE" text', () => {
    render(
      <SignatureMatrix
        cells={[{ factor: 'Quality', exposure: 'NEGATIVE', raw_score: '-0.14', rank_in_category: 67 }]}
        asset_label="Test"
      />,
    )
    expect(screen.getByText('NEGATIVE')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Case 3: Null exposure — renders with bg-paper-deep + "—" placeholder
// ---------------------------------------------------------------------------

describe('SignatureMatrix — null exposure rendering', () => {
  it('renders "—" for null raw_score', () => {
    render(
      <SignatureMatrix
        cells={[{ factor: 'Size', exposure: null, raw_score: null, rank_in_category: null }]}
        asset_label="Test"
      />,
    )
    // signedPct(null) → "—"
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renders "N/A" chip for null exposure', () => {
    render(
      <SignatureMatrix
        cells={[{ factor: 'Size', exposure: null, raw_score: null, rank_in_category: null }]}
        asset_label="Test"
      />,
    )
    expect(screen.getByText('N/A')).toBeInTheDocument()
  })

  it('does not render rank label when rank_in_category is null', () => {
    render(
      <SignatureMatrix
        cells={[{ factor: 'Size', exposure: null, raw_score: null, rank_in_category: null }]}
        asset_label="Test"
      />,
    )
    // "Rank X" text should not exist
    expect(screen.queryByText(/^Rank \d/)).not.toBeInTheDocument()
  })

  it('null exposure tile has text-ink-tertiary score', () => {
    const { container } = render(
      <SignatureMatrix
        cells={[{ factor: 'Size', exposure: null, raw_score: null, rank_in_category: null }]}
        asset_label="Test"
      />,
    )
    const scoreEl = container.querySelector('.font-mono')
    expect(scoreEl?.className).toContain('text-ink-tertiary')
  })
})

// ---------------------------------------------------------------------------
// Case 4: Tooltip on factor name reveals explanation
// ---------------------------------------------------------------------------

describe('SignatureMatrix — tooltip on factor name', () => {
  it('info button is present on each factor tile', () => {
    render(
      <SignatureMatrix
        cells={[
          { factor: 'Value', exposure: 'POSITIVE', raw_score: '0.18', rank_in_category: 3 },
          { factor: 'Momentum', exposure: 'NEUTRAL', raw_score: '0.02', rank_in_category: 22 },
        ]}
        asset_label="Test"
      />,
    )
    // InfoTooltip renders a button[aria-label="info"] per tile
    const infoButtons = screen.getAllByRole('button', { name: 'info' })
    expect(infoButtons).toHaveLength(2)
  })

  it('tooltip content appears on hover', async () => {
    const user = userEvent.setup()
    render(
      <SignatureMatrix
        cells={[{ factor: 'Value', exposure: 'POSITIVE', raw_score: '0.18', rank_in_category: 3 }]}
        asset_label="Test"
      />,
    )
    const infoButton = screen.getByRole('button', { name: 'info' })
    await user.hover(infoButton)
    // The tooltip should contain some explanation text for "Value"
    // InfoTooltip renders content in a portal; Radix may render two nodes
    // (visible + a11y hidden copy) — use findAllByText and check at least one.
    const tooltips = await screen.findAllByText(/book\/price/i)
    expect(tooltips.length).toBeGreaterThanOrEqual(1)
  })
})

// ---------------------------------------------------------------------------
// Case 5: ARIA — each cell has correct aria-label
// ---------------------------------------------------------------------------

describe('SignatureMatrix — ARIA labels', () => {
  it('POSITIVE cell aria-label includes factor, exposure, score and rank', () => {
    const { container } = render(
      <SignatureMatrix
        cells={[{ factor: 'Value', exposure: 'POSITIVE', raw_score: '0.18', rank_in_category: 3 }]}
        asset_label="Test"
      />,
    )
    const tile = container.querySelector('[role="listitem"]')!
    const label = tile.getAttribute('aria-label') ?? ''
    expect(label).toContain('Value')
    expect(label).toContain('POSITIVE')
    expect(label).toContain('score')
    expect(label).toContain('rank')
  })

  it('null exposure cell aria-label says "no data"', () => {
    const { container } = render(
      <SignatureMatrix
        cells={[{ factor: 'Size', exposure: null, raw_score: null, rank_in_category: null }]}
        asset_label="Test"
      />,
    )
    const tile = container.querySelector('[role="listitem"]')!
    const label = tile.getAttribute('aria-label') ?? ''
    expect(label).toContain('Size')
    expect(label).toContain('no data')
  })

  it('section has aria-label identifying the asset', () => {
    render(
      <SignatureMatrix cells={ALL_CELLS} asset_label="HDFC Flexi Cap Fund" />,
    )
    expect(
      screen.getByRole('region', { name: /Factor exposure matrix for HDFC Flexi Cap Fund/i }),
    ).toBeInTheDocument()
  })
})
