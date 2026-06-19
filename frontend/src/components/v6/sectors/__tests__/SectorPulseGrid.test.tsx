// frontend/src/components/v6/sectors/__tests__/SectorPulseGrid.test.tsx
// Tests for the market-pulse relative-return grid.
//
// Coverage:
//   - relValue computes sector − base per window, null-safe
//   - tiles render with relative values and link to /sectors/[name]
//   - base toggle (Nifty 50 / Nifty 500) re-computes relative values
//   - window toggle switches the displayed window
//   - null relative renders em-dash

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import type { ReactNode } from 'react'

vi.mock('@/lib/queries/v6/sector_index_rs', () => ({}))
vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({ default: vi.fn() }))
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode; [k: string]: unknown }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}))

import { SectorPulseGrid, relValue } from '../SectorPulseGrid'
import type { SectorIndexRsPayload, SectorIndexRet, WindowRet } from '@/lib/queries/v6/sector_index_rs'

function win(o: Partial<WindowRet> = {}): WindowRet {
  return { ret_1d: null, ret_1w: null, ret_1m: null, ret_3m: null, ret_6m: null, ret_12m: null, ...o }
}

function sector(name: string, ret: Partial<WindowRet>): SectorIndexRet {
  return { sector_name: name, nse_index_code: `NIFTY ${name}`, ret: win(ret) }
}

const payload: SectorIndexRsPayload = {
  sectors: [
    sector('Banking', { ret_1d: 0.02, ret_1m: 0.05 }),
    sector('IT', { ret_1d: -0.01, ret_1m: 0.005 }),
  ],
  bases: {
    'NIFTY 50': win({ ret_1d: 0.005, ret_1m: 0.02 }),
    'NIFTY 500': win({ ret_1d: 0.01, ret_1m: 0.03 }),
  },
  as_of: '2026-06-19',
}

describe('relValue', () => {
  it('computes sector minus base for a window', () => {
    const v = relValue(payload.sectors[0], payload.bases['NIFTY 50'], '1m')
    expect(v).toBeCloseTo(0.03, 10) // 0.05 − 0.02
  })

  it('returns null when sector side is missing', () => {
    expect(relValue(payload.sectors[0], payload.bases['NIFTY 50'], '12m')).toBeNull()
  })

  it('returns null when base side is missing', () => {
    const noBase = win({ ret_1m: null })
    expect(relValue(payload.sectors[0], noBase, '1m')).toBeNull()
  })
})

describe('SectorPulseGrid', () => {
  it('renders a tile per sector linking to the detail page', () => {
    render(<SectorPulseGrid data={payload} />)
    const banking = screen.getByTitle(/^Banking/)
    expect(banking.getAttribute('href')).toBe('/sectors/Banking')
  })

  it('defaults to 1M vs Nifty 50 and shows relative value', () => {
    render(<SectorPulseGrid data={payload} />)
    // Banking 1M rel vs N50 = 0.05 − 0.02 = +3.0%
    const banking = screen.getByTitle(/^Banking/)
    expect(within(banking).getByText('+3.0%')).toBeTruthy()
  })

  it('switching base to Nifty 500 recomputes relative value', () => {
    render(<SectorPulseGrid data={payload} />)
    fireEvent.click(screen.getByRole('button', { name: 'Nifty 500' }))
    // Banking 1M rel vs N500 = 0.05 − 0.03 = +2.0%
    const banking = screen.getByTitle(/^Banking/)
    expect(within(banking).getByText('+2.0%')).toBeTruthy()
  })

  it('switching window to 1D recomputes relative value', () => {
    render(<SectorPulseGrid data={payload} />)
    fireEvent.click(screen.getByRole('button', { name: '1D' }))
    // Banking 1D rel vs N50 = 0.02 − 0.005 = +1.5%
    const banking = screen.getByTitle(/^Banking/)
    expect(within(banking).getByText('+1.5%')).toBeTruthy()
  })

  it('renders nothing when there are no sectors', () => {
    const { container } = render(
      <SectorPulseGrid data={{ ...payload, sectors: [] }} />,
    )
    expect(container.firstChild).toBeNull()
  })
})
