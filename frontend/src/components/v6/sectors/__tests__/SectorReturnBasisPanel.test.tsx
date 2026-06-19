// frontend/src/components/v6/sectors/__tests__/SectorReturnBasisPanel.test.tsx
// Tests the dual-basis helpers + the Index ⟷ Bottom-up toggle panel.

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'

vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({ default: vi.fn() }))

import { basisReturn, basisRs } from '@/lib/queries/v6/sector_return_bases_shared'
import type { SectorReturnBases, ReturnSet } from '@/lib/queries/v6/sector_return_bases_shared'
import { SectorReturnBasisPanel } from '../SectorReturnBasisPanel'

function set(o: Partial<ReturnSet>): ReturnSet {
  return { ret_1d: null, ret_1w: null, ret_1m: null, ret_3m: null, ret_6m: null, ret_12m: null, ...o }
}

const defence: SectorReturnBases = {
  sector_name: 'Defence',
  index_code: 'NIFTY IND DEFENCE',
  index: set({ ret_1d: 0.004, ret_3m: 0.177, ret_12m: 0.074 }),
  bottomup: set({ ret_1d: 0.007, ret_3m: 0.176, ret_12m: 0.191 }),
}
const nifty500 = set({ ret_3m: 0.08, ret_12m: -0.006 })

describe('basis helpers', () => {
  it('basisReturn picks the active basis + window', () => {
    expect(basisReturn(defence, 'index', '12m')).toBeCloseTo(0.074, 6)
    expect(basisReturn(defence, 'bottomup', '12m')).toBeCloseTo(0.191, 6)
  })
  it('basisRs subtracts the Nifty 500 return', () => {
    expect(basisRs(defence, nifty500, 'index', '3m')).toBeCloseTo(0.177 - 0.08, 6)
  })
  it('basisRs is null when either side is missing', () => {
    expect(basisRs(defence, nifty500, 'index', '1m')).toBeNull() // sector 1m null
    expect(basisRs(defence, nifty500, 'bottomup', '1d')).toBeNull() // n500 1d null
  })
})

describe('SectorReturnBasisPanel', () => {
  it('defaults to Index and shows the cap-weighted index 12M return', () => {
    render(<SectorReturnBasisPanel data={defence} nifty500={nifty500} />)
    // 12M index return = +7.4%
    expect(screen.getByText('+7.4%')).toBeTruthy()
  })

  it('toggling to Bottom-up switches to the free-float figures', () => {
    render(<SectorReturnBasisPanel data={defence} nifty500={nifty500} />)
    fireEvent.click(screen.getByRole('button', { name: 'Bottom-up' }))
    // 12M bottom-up = +19.1%
    expect(screen.getByText('+19.1%')).toBeTruthy()
  })

  it('renders a placeholder when no data', () => {
    render(<SectorReturnBasisPanel data={null} nifty500={nifty500} />)
    expect(screen.getByText(/No return data/i)).toBeTruthy()
  })
})
