// frontend/src/components/v6/sectors/__tests__/SectorHeroReadout.test.tsx
//
// H4 regression: the Leading/Lagging badge count must reflect the TRUE number of
// sectors in the quadrant, not the 4-/5-row display slice. Previously the hero
// badge read "4 leading" while the RRG legend read "Leading 15" — a contradiction.

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'

vi.mock('@/lib/queries/v6/sectors', () => ({}))
vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({ default: vi.fn() }))
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode; [k: string]: unknown }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}))

import { SectorHeroReadout } from '../SectorHeroReadout'
import type { SectorCardRow } from '@/lib/queries/v6/sectors'

function makeCard(overrides: Partial<SectorCardRow> = {}): SectorCardRow {
  return {
    as_of_date: '2026-05-29',
    sector_name: 'Energy',
    constituent_count: 62,
    ret_1w: 0.018,
    ret_1m: 0.068,
    ret_3m: 0.142,
    ret_6m: 0.21,
    ret_12m: 0.246,
    rs_1m: 0.042,
    rs_3m: 0.084,
    rs_6m: 0.062,
    vol_60d_ann: 0.142,
    pct_above_ema21: 0.78,
    pct_above_ema200: 0.65,
    pct_at_52wh: 0.42,
    hhi_concentration: 0.12,
    buy_signal_count: 14,
    confidence_distribution: { H: 6, M: 5, L: 3 },
    verdict: 'Overweight',
    verdict_abbr: 'OW',
    ...overrides,
  }
}

describe('SectorHeroReadout — H4 leading count (true count, not display slice)', () => {
  it('badge reflects all 6 leading sectors even though only 4 rows render', () => {
    // 6 cards with rs_3m > 0 → all classified Leading via the fallback heuristic.
    const cards = Array.from({ length: 6 }, (_, i) =>
      makeCard({ sector_name: `Sector ${i}`, rs_3m: 0.2 - i * 0.01 }),
    )
    render(<SectorHeroReadout cards={cards} />)
    // True count, not capped at the 4-row slice.
    expect(screen.getByText(/6 sectors/)).toBeInTheDocument()
    // "+ N others" must also use the true count (5), not slice-1 (3).
    expect(screen.getByText(/\+ 5 others carrying the tape/)).toBeInTheDocument()
  })
})
