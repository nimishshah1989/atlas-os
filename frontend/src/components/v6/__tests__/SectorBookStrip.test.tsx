// frontend/src/components/v6/__tests__/SectorBookStrip.test.tsx
//
// 3 test cases per plan:
//   1. list variant: 5 rows → 5 row elements, correct chips per delta sign
//   2. single variant: 1 row rendered, displays that sector's data
//   3. no-book (all book_weight="0.00"): muted styling, no synthetic data

import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { SectorBookStrip } from '../SectorBookStrip'
import type { SectorBookExposure } from '@/lib/queries/v6/sector_book_exposure'

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

function makeRow(
  sector_name: string,
  book_weight: string,
  benchmark_weight: string,
  delta_pp: string,
  holding_count = 2,
): SectorBookExposure {
  return { sector_name, book_weight, benchmark_weight, delta_pp, holding_count }
}

// 5 sample rows covering all chip variants
const FIVE_ROWS: SectorBookExposure[] = [
  makeRow('Financial Services', '12.50', '10.00', '2.50', 5),   // OVERWEIGHT
  makeRow('Information Technology', '8.00', '12.00', '-4.00', 3), // UNDERWEIGHT
  makeRow('Consumer Goods', '5.00', '5.00', '0.00', 2),           // NEUTRAL
  makeRow('Healthcare', '7.00', '4.50', '2.50', 4),               // OVERWEIGHT
  makeRow('Energy', '3.00', '6.00', '-3.00', 1),                  // UNDERWEIGHT
]

// 1 single sector row
const SINGLE_ROW: SectorBookExposure[] = [
  makeRow('Metals & Mining', '6.00', '3.50', '2.50', 3),
]

// All zero book + benchmark weights (empty book scenario)
const NO_BOOK_ROWS: SectorBookExposure[] = [
  makeRow('Financial Services', '0.00', '0.00', '0.00', 0),
  makeRow('Information Technology', '0.00', '0.00', '0.00', 0),
  makeRow('Consumer Goods', '0.00', '0.00', '0.00', 0),
]

// ---------------------------------------------------------------------------
// Case 1: list variant — 5 rows, correct chips
// ---------------------------------------------------------------------------

describe('SectorBookStrip — list variant (5 rows)', () => {
  it('renders exactly 5 row elements', () => {
    render(<SectorBookStrip exposures={FIVE_ROWS} variant="list" />)
    const rows = screen.getAllByRole('row')
    expect(rows).toHaveLength(5)
  })

  it('renders OVERWEIGHT chip for positive delta rows', () => {
    render(<SectorBookStrip exposures={FIVE_ROWS} variant="list" />)
    const overweightChips = screen.getAllByText('OVERWEIGHT')
    expect(overweightChips.length).toBeGreaterThanOrEqual(2)
    // Check Financial Services row (2.50 pp)
    const fsRow = screen.getByRole('row', {
      name: /Financial Services/,
    })
    expect(within(fsRow).getByText('OVERWEIGHT')).toBeInTheDocument()
  })

  it('renders UNDERWEIGHT chip for negative delta rows', () => {
    render(<SectorBookStrip exposures={FIVE_ROWS} variant="list" />)
    const underweightChips = screen.getAllByText('UNDERWEIGHT')
    expect(underweightChips.length).toBeGreaterThanOrEqual(2)
    // Check IT row (-4.00 pp)
    const itRow = screen.getByRole('row', {
      name: /Information Technology/,
    })
    expect(within(itRow).getByText('UNDERWEIGHT')).toBeInTheDocument()
  })

  it('renders NEUTRAL chip for zero delta row', () => {
    render(<SectorBookStrip exposures={FIVE_ROWS} variant="list" />)
    const neutralChips = screen.getAllByText('NEUTRAL')
    expect(neutralChips.length).toBeGreaterThanOrEqual(1)
    const cgRow = screen.getByRole('row', {
      name: /Consumer Goods/,
    })
    expect(within(cgRow).getByText('NEUTRAL')).toBeInTheDocument()
  })

  it('applies signal-pos class to OVERWEIGHT chip', () => {
    const { container } = render(<SectorBookStrip exposures={FIVE_ROWS} variant="list" />)
    const overChips = container.querySelectorAll('[class*="bg-signal-pos"]')
    // At least one overweight chip should use signal-pos
    expect(overChips.length).toBeGreaterThan(0)
  })

  it('applies signal-neg class to UNDERWEIGHT chip', () => {
    const { container } = render(<SectorBookStrip exposures={FIVE_ROWS} variant="list" />)
    const underChips = container.querySelectorAll('[class*="bg-signal-neg"]')
    expect(underChips.length).toBeGreaterThan(0)
  })

  it('rows have correct aria-label with sector name', () => {
    render(<SectorBookStrip exposures={FIVE_ROWS} variant="list" />)
    // Financial Services row aria-label
    expect(
      screen.getByRole('row', {
        name: /Financial Services: book 12\.50%, benchmark 10\.00%, delta 2\.50pp/,
      }),
    ).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Case 2: single variant — 1 row rendered
// ---------------------------------------------------------------------------

describe('SectorBookStrip — single variant (1 row)', () => {
  it('renders exactly 1 row element', () => {
    render(<SectorBookStrip exposures={SINGLE_ROW} variant="single" />)
    const rows = screen.getAllByRole('row')
    expect(rows).toHaveLength(1)
  })

  it("displays the sector's name", () => {
    render(<SectorBookStrip exposures={SINGLE_ROW} variant="single" />)
    expect(screen.getByText('Metals & Mining')).toBeInTheDocument()
  })

  it('renders OVERWEIGHT chip for the single positive-delta row', () => {
    render(<SectorBookStrip exposures={SINGLE_ROW} variant="single" />)
    expect(screen.getByText('OVERWEIGHT')).toBeInTheDocument()
  })

  it('aria-label contains book/benchmark/delta values', () => {
    render(<SectorBookStrip exposures={SINGLE_ROW} variant="single" />)
    expect(
      screen.getByRole('row', {
        name: /Metals & Mining: book 6\.00%, benchmark 3\.50%, delta 2\.50pp/,
      }),
    ).toBeInTheDocument()
  })

  it('renders nothing visible when passed empty array', () => {
    render(<SectorBookStrip exposures={[]} variant="single" />)
    expect(screen.getByText('No sector exposure data')).toBeInTheDocument()
    // sr-only element — not visible
    const el = screen.getByText('No sector exposure data')
    expect(el.className).toContain('sr-only')
  })
})

// ---------------------------------------------------------------------------
// Case 3: no-book — all book_weight="0.00", benchmark_weight="0.00"
// ---------------------------------------------------------------------------

describe('SectorBookStrip — no-book (all zeros)', () => {
  it('renders all rows without crashing (no synthetic data)', () => {
    render(<SectorBookStrip exposures={NO_BOOK_ROWS} variant="list" />)
    const rows = screen.getAllByRole('row')
    // All 3 rows rendered
    expect(rows).toHaveLength(3)
  })

  it('applies muted (text-ink-tertiary) styling on sector name cells', () => {
    const { container } = render(<SectorBookStrip exposures={NO_BOOK_ROWS} variant="list" />)
    const mutedNames = container.querySelectorAll('.text-ink-tertiary')
    expect(mutedNames.length).toBeGreaterThan(0)
  })

  it('does NOT fabricate non-zero weight values', () => {
    render(<SectorBookStrip exposures={NO_BOOK_ROWS} variant="list" />)
    // In muted rows delta is "—", not a made-up number
    const dashElements = screen.getAllByText('—')
    expect(dashElements.length).toBeGreaterThanOrEqual(NO_BOOK_ROWS.length)
  })

  it('shows em-dash for delta in muted rows', () => {
    render(<SectorBookStrip exposures={NO_BOOK_ROWS} variant="list" />)
    const dashes = screen.getAllByText('—')
    // At least one per row
    expect(dashes.length).toBeGreaterThanOrEqual(3)
  })
})
