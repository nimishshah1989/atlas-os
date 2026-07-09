// frontend/src/components/sectors/__tests__/SectorStock2x2.test.tsx
// Tests for SectorStock2x2 component.
//
// Coverage:
//   - Momentum×Quality quad plots only stocks with BOTH d_tech and d_fund
//   - Stocks visible in Strength×Leadership but missing a score are named in an
//     honest exclusion caption on the Momentum×Quality quad (not fabricated)
//   - No caption when nothing is excluded

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'

vi.mock('@/lib/queries/sector_lens', () => ({}))
vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({ default: vi.fn() }))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div data-testid="rc">{children}</div>,
  ScatterChart: ({ children }: { children: ReactNode }) => <svg data-testid="scatter-chart">{children}</svg>,
  Scatter: ({ children }: { children?: ReactNode }) => <g data-testid="scatter">{children}</g>,
  XAxis: () => null,
  YAxis: () => null,
  ZAxis: () => null,
  CartesianGrid: () => null,
  ReferenceLine: () => null,
  Tooltip: () => null,
  Cell: () => null,
}))

import { SectorStock2x2 } from '../SectorStock2x2'
import type { SectorStock } from '@/lib/queries/sector_lens'

function makeStock(symbol: string, overrides: Partial<SectorStock> = {}): SectorStock {
  return {
    symbol, name: symbol, cap: 'large',
    d_tech: 5, d_fund: 5, d_cat: null, d_flow: null, d_val: null,
    lead: 0, strength: 5,
    ret_1d: null, ret_1w: null, ret_1m: null, ret_3m: null, ret_6m: null, ret_12m: null,
    rs_1m: null, rs_3m: null, rs_6m: null, rs_sector_3m: null,
    liq_cr: null, ff_weight: null,
    ...overrides,
  }
}

describe('SectorStock2x2', () => {
  it('plots only stocks with both d_tech and d_fund on the Momentum×Quality quad', () => {
    const stocks = [
      makeStock('FULL', { d_tech: 5, d_fund: 5, strength: 5 }),
      makeStock('NOFUND', { d_tech: 6, d_fund: null, strength: 6 }),
      makeStock('NOTECH_NOSTR', { d_tech: null, d_fund: 7, strength: null }),
    ]
    render(<SectorStock2x2 stocks={stocks} />)
    expect(screen.getByText('· 1 plotted')).toBeTruthy()
  })

  it('names a stock excluded from Momentum×Quality but visible in Strength×Leadership, without a stand-in score', () => {
    const stocks = [
      makeStock('FULL', { d_tech: 5, d_fund: 5, strength: 5 }),
      makeStock('NOFUND', { d_tech: 6, d_fund: null, strength: 6 }),
    ]
    render(<SectorStock2x2 stocks={stocks} />)
    expect(screen.getByText(/1 excluded/)).toBeTruthy()
    expect(screen.getByText(/no fundamental score/)).toBeTruthy()
    expect(screen.getByText(/NOFUND/)).toBeTruthy()
  })

  it('does not caption a stock missing both scores (not visible in the other chart either)', () => {
    const stocks = [
      makeStock('FULL', { d_tech: 5, d_fund: 5, strength: 5 }),
      makeStock('GHOST', { d_tech: null, d_fund: null, strength: null }),
    ]
    render(<SectorStock2x2 stocks={stocks} />)
    expect(screen.queryByText(/excluded/)).toBeNull()
  })

  it('renders no caption when nothing is excluded', () => {
    const stocks = [makeStock('FULL', { d_tech: 5, d_fund: 5, strength: 5 })]
    render(<SectorStock2x2 stocks={stocks} />)
    expect(screen.queryByText(/excluded/)).toBeNull()
  })
})
