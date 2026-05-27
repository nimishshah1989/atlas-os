// frontend/src/components/v6/__tests__/MultiTenureReturnsTable.test.tsx
//
// 5 test cases:
//   1. Renders N rows with correct columns visible
//   2. Color-threshold: all-positive row has all text-signal-pos; mixed row has mixed
//   3. Null cells render em-dash with text-ink-tertiary
//   4. highlightIid: matching row has ring-2 ring-signal-pos outline
//   5. Empty rows: renders fallback message, no synthetic data

import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import {
  MultiTenureReturnsTable,
  type MultiTenureReturnsTableProps,
} from '../MultiTenureReturnsTable'
import type { MultiTenureReturns } from '@/lib/queries/v6/multi_tenure_returns'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const IID_A = 'aaaaaaaa-0000-0000-0000-000000000001'
const IID_B = 'bbbbbbbb-0000-0000-0000-000000000002'
const IID_C = 'cccccccc-0000-0000-0000-000000000003'

const ROW_ALL_POSITIVE: MultiTenureReturns = {
  iid: IID_A,
  date: '2026-05-26',
  ret_1d: '0.012',
  ret_1w: '0.034',
  ret_1m: '0.075',
  ret_3m: '0.120',
  ret_6m: '0.183',
  ret_12m: '0.315',
}

const ROW_MIXED: MultiTenureReturns = {
  iid: IID_B,
  date: '2026-05-26',
  ret_1d: '-0.005',
  ret_1w: '0.020',
  ret_1m: '-0.040',
  ret_3m: '0.060',
  ret_6m: '-0.083',
  ret_12m: '0.110',
}

const ROW_WITH_NULLS: MultiTenureReturns = {
  iid: IID_C,
  date: '2026-05-26',
  ret_1d: null,
  ret_1w: null,
  ret_1m: '0.050',
  ret_3m: '0.090',
  ret_6m: null,
  ret_12m: null,
}

// ---------------------------------------------------------------------------
// Case 1 — Renders N rows; correct columns visible
// ---------------------------------------------------------------------------

describe('MultiTenureReturnsTable — row + column rendering', () => {
  it('renders all 6 column headers by default', () => {
    render(<MultiTenureReturnsTable rows={[ROW_ALL_POSITIVE]} />)
    const table = screen.getByRole('table')
    expect(within(table).getByRole('columnheader', { name: /1d/i })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: /1w/i })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: /1m/i })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: /3m/i })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: /6m/i })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: /12m/i })).toBeInTheDocument()
  })

  it('renders 2 data rows when passed 2 instruments', () => {
    render(<MultiTenureReturnsTable rows={[ROW_ALL_POSITIVE, ROW_MIXED]} />)
    // All rows including the header row
    const rows = screen.getAllByRole('row')
    // header row + 2 data rows = 3 total
    expect(rows).toHaveLength(3)
  })

  it('respects showColumns prop — only specified columns render', () => {
    render(
      <MultiTenureReturnsTable
        rows={[ROW_ALL_POSITIVE]}
        showColumns={['ret_1m', 'ret_6m']}
      />,
    )
    const table = screen.getByRole('table')
    expect(within(table).getByRole('columnheader', { name: /1m/i })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: /6m/i })).toBeInTheDocument()
    expect(within(table).queryByRole('columnheader', { name: /1d/i })).not.toBeInTheDocument()
    expect(within(table).queryByRole('columnheader', { name: /12m/i })).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Case 2 — Color-threshold: positive → text-signal-pos; negative → text-signal-neg
// ---------------------------------------------------------------------------

describe('MultiTenureReturnsTable — color threshold', () => {
  it('all return cells on an all-positive row have text-signal-pos class', () => {
    const { container } = render(
      <MultiTenureReturnsTable rows={[ROW_ALL_POSITIVE]} />,
    )
    // Find all data cells (exclude ticker + header cells)
    // Each return cell has role="cell" and aria-label matching a tenure
    const returnCells = container.querySelectorAll('td[aria-label*="1d"], td[aria-label*="1w"], td[aria-label*="1m"], td[aria-label*="3m"], td[aria-label*="6m"], td[aria-label*="12m"]')
    expect(returnCells.length).toBeGreaterThan(0)
    returnCells.forEach((cell) => {
      expect(cell.className).toContain('text-signal-pos')
    })
  })

  it('mixed row has both text-signal-pos and text-signal-neg cells', () => {
    const { container } = render(
      <MultiTenureReturnsTable rows={[ROW_MIXED]} />,
    )
    const posCells = container.querySelectorAll('td.text-signal-pos')
    const negCells = container.querySelectorAll('td.text-signal-neg')
    expect(posCells.length).toBeGreaterThan(0)
    expect(negCells.length).toBeGreaterThan(0)
  })

  it('negative return displays with minus sign', () => {
    render(<MultiTenureReturnsTable rows={[ROW_MIXED]} />)
    // ret_1d = '-0.005' → signedPct → '-0.5%'
    const cell = screen.getByRole('cell', { name: /1d:.*-/ })
    expect(cell.textContent).toMatch(/^-/)
  })

  it('positive return displays with plus sign', () => {
    render(<MultiTenureReturnsTable rows={[ROW_ALL_POSITIVE]} />)
    // ret_1d = '0.012' → signedPct → '+1.2%'
    const cell = screen.getByRole('cell', { name: /1d:.*\+/ })
    expect(cell.textContent).toMatch(/^\+/)
  })
})

// ---------------------------------------------------------------------------
// Case 3 — Null cells: render em-dash with text-ink-tertiary
// ---------------------------------------------------------------------------

describe('MultiTenureReturnsTable — null cells', () => {
  it('null return value renders em-dash character', () => {
    const { container } = render(
      <MultiTenureReturnsTable rows={[ROW_WITH_NULLS]} />,
    )
    // Find cells with em-dash content
    const allCells = Array.from(container.querySelectorAll('td[role="cell"]'))
    const emDashCells = allCells.filter((c) => c.textContent === '—')
    // ROW_WITH_NULLS has 4 null fields: ret_1d, ret_1w, ret_6m, ret_12m
    expect(emDashCells).toHaveLength(4)
  })

  it('null cells have text-ink-tertiary class', () => {
    const { container } = render(
      <MultiTenureReturnsTable rows={[ROW_WITH_NULLS]} />,
    )
    const allCells = Array.from(container.querySelectorAll('td[role="cell"]'))
    const emDashCells = allCells.filter((c) => c.textContent === '—')
    emDashCells.forEach((cell) => {
      expect(cell.className).toContain('text-ink-tertiary')
    })
  })

  it('null cell aria-label contains em-dash', () => {
    render(<MultiTenureReturnsTable rows={[ROW_WITH_NULLS]} />)
    // ret_1d is null → aria-label "CCCCCCCC 1d: —"
    const cell = screen.getByRole('cell', { name: /1d: —/ })
    expect(cell).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Case 4 — highlightIid: matching row has ring-signal-pos outline
// ---------------------------------------------------------------------------

describe('MultiTenureReturnsTable — highlightIid', () => {
  it('highlighted row has bg-paper-deep class', () => {
    const { container } = render(
      <MultiTenureReturnsTable
        rows={[ROW_ALL_POSITIVE, ROW_MIXED]}
        highlightIid={IID_A}
      />,
    )
    const rows = container.querySelectorAll('tr[role="row"]')
    // data rows start at index 1 (index 0 is the header row)
    const firstDataRow = rows[1]
    expect(firstDataRow.className).toContain('bg-paper-deep')
  })

  it('highlighted row has ring-2 ring-signal-pos', () => {
    const { container } = render(
      <MultiTenureReturnsTable
        rows={[ROW_ALL_POSITIVE, ROW_MIXED]}
        highlightIid={IID_A}
      />,
    )
    const rows = container.querySelectorAll('tr[role="row"]')
    const firstDataRow = rows[1]
    expect(firstDataRow.className).toContain('ring-2')
    expect(firstDataRow.className).toContain('ring-signal-pos')
  })

  it('non-highlighted row does NOT have bg-paper-deep', () => {
    const { container } = render(
      <MultiTenureReturnsTable
        rows={[ROW_ALL_POSITIVE, ROW_MIXED]}
        highlightIid={IID_A}
      />,
    )
    const rows = container.querySelectorAll('tr[role="row"]')
    // second data row (IID_B) should NOT be highlighted
    const secondDataRow = rows[2]
    expect(secondDataRow.className).not.toContain('ring-signal-pos')
  })
})

// ---------------------------------------------------------------------------
// Case 5 — Empty rows: renders fallback message
// ---------------------------------------------------------------------------

describe('MultiTenureReturnsTable — empty state', () => {
  it('renders fallback message when rows is empty', () => {
    render(<MultiTenureReturnsTable rows={[]} />)
    expect(screen.getByText('No return data available')).toBeInTheDocument()
  })

  it('fallback cell spans all columns (no synthetic rows)', () => {
    const { container } = render(
      <MultiTenureReturnsTable rows={[]} />,
    )
    // Only 1 data row rendered (the fallback), no ghost rows
    const tbody = container.querySelector('tbody')!
    const dataRows = tbody.querySelectorAll('tr')
    expect(dataRows).toHaveLength(1)

    // The single cell has a colSpan covering all 7 columns (ticker + 6 returns)
    const cell = dataRows[0].querySelector('td')!
    expect(Number(cell.getAttribute('colspan'))).toBeGreaterThan(1)
  })

  it('renders column headers even when rows is empty', () => {
    render(<MultiTenureReturnsTable rows={[]} />)
    expect(screen.getByRole('columnheader', { name: /1d/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /12m/i })).toBeInTheDocument()
  })
})
