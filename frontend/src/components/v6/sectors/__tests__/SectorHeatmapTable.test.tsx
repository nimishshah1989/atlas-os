// frontend/src/components/v6/sectors/__tests__/SectorHeatmapTable.test.tsx
// Tests for the new index-level 1D column on the multi-window heatmap.

import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'

vi.mock('@/lib/queries/v6/sectors', () => ({}))
vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({ default: vi.fn() }))
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode; [k: string]: unknown }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}))

import { SectorHeatmapTable } from '../SectorHeatmapTable'
import type { SectorCardRow } from '@/lib/queries/v6/sectors'

function makeCard(overrides: Partial<SectorCardRow> = {}): SectorCardRow {
  return {
    as_of_date: '2026-06-19', sector_name: 'Banking', constituent_count: 12,
    ret_1w: 0.01, ret_1m: 0.02, ret_3m: 0.03, ret_6m: 0.04, ret_12m: 0.05,
    rs_1m: 0.01, rs_3m: 0.02, rs_6m: 0.03, vol_60d_ann: 0.1,
    pct_above_ema20: 0.6, pct_above_ema200: 0.5, pct_at_52wh: 0.2, hhi_concentration: 0.1,
    buy_signal_count: 1, confidence_distribution: { H: 1, M: 0, L: 0 },
    verdict: 'Overweight', verdict_abbr: 'OW', ...overrides,
  }
}

describe('SectorHeatmapTable 1D column', () => {
  it('renders the NSE index 1D return when provided', () => {
    render(
      <SectorHeatmapTable
        cards={[makeCard({ sector_name: 'Banking' })]}
        idxRet1dBySector={{ Banking: 0.012 }}
      />,
    )
    expect(screen.getByText('1D')).toBeTruthy()
    expect(screen.getByText('+1.2%')).toBeTruthy()
  })

  it('renders em-dash when the sector has no index 1D value', () => {
    render(
      <SectorHeatmapTable
        cards={[makeCard({ sector_name: 'Banking' })]}
        idxRet1dBySector={{}}
      />,
    )
    const row = screen.getByText('Banking').closest('tr') as HTMLElement
    // First data cell after the sector name is the 1D column → em-dash.
    expect(within(row).getAllByText('—').length).toBeGreaterThan(0)
  })
})
