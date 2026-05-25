// frontend/src/components/v6/__tests__/SectorsListV6.test.tsx
//
// 4 test cases per spec:
//   1. Renders SectorBookStrip + ladder when data is present
//   2. Empty sectors → empty state copy "No sector data available"
//   3. Ladder rows sorted ascending by rank
//   4. Sparkline column is visible (header + cells present)

import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { SectorsListV6, type SectorsListV6Props } from '../SectorsListV6'
import type { ScreenSector } from '@/lib/api/v1'
import type { SectorBookExposure } from '@/lib/queries/v6/sector_book_exposure'
import type { SectorSnapshot, RRGHistoryRow } from '@/lib/queries/sectors'

// ---------------------------------------------------------------------------
// Mock heavy D3 dependency (RRGChart is a canvas/SVG component)
// ---------------------------------------------------------------------------

vi.mock('@/components/sectors/RRGChart', () => ({
  RRGChart: ({ current }: { current: SectorSnapshot[] }) => (
    <div data-testid="rrg-chart" aria-label={`RRG chart — ${current.length} sectors`} />
  ),
}))

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeSector(
  idx: number,
  overrides: Partial<ScreenSector> = {},
): ScreenSector {
  return {
    sector_iid:           `sector-${idx}`,
    sector_name:          `Sector ${idx}`,
    rank:                 idx,
    rank_change:          0,
    days_in_state:        5,
    sector_state:         idx <= 2 ? 'Overweight' : idx <= 4 ? 'Neutral' : 'Avoid',
    breadth_pct_stage_2:  0.55 - idx * 0.05,
    vol_regime:           'Normal',
    rs_pct_cross_sector:  0.1 - idx * 0.02,
    ret_1m:               0.03,
    ret_3m:               0.07,
    rrg_quadrant:         null,
    cells_favored_today:  [],
    ...overrides,
  }
}

function makeExposure(sectorName: string): SectorBookExposure {
  return {
    sector_name:       sectorName,
    book_weight:       '5.00',
    benchmark_weight:  '4.00',
    delta_pp:          '1.00',
    holding_count:     2,
  }
}

// 5 sectors for most tests
const FIVE_SECTORS: ScreenSector[] = [1, 2, 3, 4, 5].map(i => makeSector(i))

const FIVE_EXPOSURES: SectorBookExposure[] = FIVE_SECTORS.map(s => makeExposure(s.sector_name))

// Out-of-order sectors (to test sort)
const SHUFFLED_SECTORS: ScreenSector[] = [
  makeSector(3, { rank: 3 }),
  makeSector(1, { rank: 1 }),
  makeSector(5, { rank: 5 }),
  makeSector(2, { rank: 2 }),
  makeSector(4, { rank: 4 }),
]

const EMPTY_RRG_CURRENT: SectorSnapshot[] = []
const EMPTY_RRG_HISTORY: RRGHistoryRow[]  = []

function makeProps(overrides: Partial<SectorsListV6Props> = {}): SectorsListV6Props {
  return {
    sectors:    FIVE_SECTORS,
    exposures:  FIVE_EXPOSURES,
    rrgCurrent: EMPTY_RRG_CURRENT,
    rrgHistory:  EMPTY_RRG_HISTORY,
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Case 1 — Renders SectorBookStrip + ladder
// ---------------------------------------------------------------------------

describe('SectorsListV6 — renders core sections', () => {
  it('renders SectorBookStrip (list variant) table', () => {
    render(<SectorsListV6 {...makeProps()} />)
    // SectorBookStrip renders a table with aria-label
    expect(
      screen.getByRole('table', { name: /book vs benchmark sector exposure/i }),
    ).toBeInTheDocument()
  })

  it('renders the sector ladder table', () => {
    render(<SectorsListV6 {...makeProps()} />)
    expect(screen.getByTestId('sectors-table')).toBeInTheDocument()
  })

  it('renders a sector ladder row for each sector', () => {
    render(<SectorsListV6 {...makeProps()} />)
    const table = screen.getByTestId('sectors-table')
    // tbody rows — one per sector
    const rows = within(table).getAllByRole('row')
    // includes header row → total = sectors + 1
    expect(rows.length).toBe(FIVE_SECTORS.length + 1)
  })

  it('sector names are visible in the ladder', () => {
    render(<SectorsListV6 {...makeProps()} />)
    for (const s of FIVE_SECTORS) {
      expect(screen.getAllByText(s.sector_name).length).toBeGreaterThan(0)
    }
  })
})

// ---------------------------------------------------------------------------
// Case 2 — Empty state
// ---------------------------------------------------------------------------

describe('SectorsListV6 — empty state', () => {
  it('shows empty state message when sectors array is empty', () => {
    render(
      <SectorsListV6
        {...makeProps({ sectors: [], exposures: [] })}
      />,
    )
    expect(screen.getByTestId('sectors-empty-state')).toBeInTheDocument()
    expect(screen.getByText(/No sector data available/i)).toBeInTheDocument()
  })

  it('does NOT render the ladder table when sectors is empty', () => {
    render(
      <SectorsListV6
        {...makeProps({ sectors: [], exposures: [] })}
      />,
    )
    expect(screen.queryByTestId('sectors-table')).not.toBeInTheDocument()
  })

  it('does NOT render the SectorBookStrip table when sectors is empty', () => {
    render(
      <SectorsListV6
        {...makeProps({ sectors: [], exposures: [] })}
      />,
    )
    expect(
      screen.queryByRole('table', { name: /book vs benchmark sector exposure/i }),
    ).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Case 3 — Ladder sorted by rank
// ---------------------------------------------------------------------------

describe('SectorsListV6 — ladder sorted by rank', () => {
  it('renders rows in ascending rank order by default', () => {
    render(
      <SectorsListV6
        {...makeProps({ sectors: SHUFFLED_SECTORS, exposures: [] })}
      />,
    )
    const table = screen.getByTestId('sectors-table')
    // Read data-rank attributes from tbody rows
    const rows = within(table).getAllByRole('row').slice(1) // skip header
    const rankAttrs = rows
      .map(row => row.getAttribute('data-rank'))
      .filter(Boolean)
      .map(Number)
    // Should be sorted ascending: [1, 2, 3, 4, 5]
    for (let i = 0; i < rankAttrs.length - 1; i++) {
      expect(rankAttrs[i]).toBeLessThanOrEqual(rankAttrs[i + 1])
    }
  })

  it('first ladder row has rank 1', () => {
    render(
      <SectorsListV6
        {...makeProps({ sectors: SHUFFLED_SECTORS, exposures: [] })}
      />,
    )
    const table = screen.getByTestId('sectors-table')
    const firstDataRow = within(table).getAllByRole('row')[1] // index 0 = header
    expect(firstDataRow.getAttribute('data-rank')).toBe('1')
  })
})

// ---------------------------------------------------------------------------
// Case 4 — Sparkline column visible
// ---------------------------------------------------------------------------

describe('SectorsListV6 — sparkline column', () => {
  it('renders sparkline column header "12W Traj"', () => {
    render(<SectorsListV6 {...makeProps()} />)
    expect(screen.getByTestId('sparkline-header')).toBeInTheDocument()
    expect(screen.getByTestId('sparkline-header').textContent).toMatch(/12W Traj/i)
  })

  it('renders a sparkline cell for each sector row', () => {
    render(<SectorsListV6 {...makeProps()} />)
    const sparklCells = screen.getAllByTestId('sparkline-cell')
    expect(sparklCells.length).toBe(FIVE_SECTORS.length)
  })

  it('each sparkline cell contains an SVG element with data-testid rank-sparkline', () => {
    render(<SectorsListV6 {...makeProps()} />)
    const sparklines = screen.getAllByTestId('rank-sparkline')
    expect(sparklines.length).toBe(FIVE_SECTORS.length)
  })

  it('sparkline SVG has aria-label with trajectory text', () => {
    render(<SectorsListV6 {...makeProps()} />)
    const sparklines = screen.getAllByTestId('rank-sparkline')
    for (const el of sparklines) {
      expect(el.getAttribute('aria-label')).toMatch(/12-week rank trajectory/i)
    }
  })
})
