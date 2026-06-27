// frontend/src/components/v6/sectors/__tests__/SectorHeroReadout.test.tsx
//
// H4 regression: the Leading/Lagging badge count must reflect the TRUE number of
// sectors in the quadrant, not the 4-/5-row display slice. Previously the hero
// badge read "4 leading" while the RRG legend read "Leading 15" — a contradiction.
// (Post-Wave-1: the readout takes corrected SectorHeroRow[] and classifies
// leading/lagging by the sign of 3m RS vs Nifty 500, not a stale RRG quadrant.)

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode; [k: string]: unknown }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}))

import { SectorHeroReadout, type SectorHeroRow } from '../SectorHeroReadout'

function makeRow(overrides: Partial<SectorHeroRow> = {}): SectorHeroRow {
  return {
    sector_name: 'Energy',
    ret_1m: 0.068,
    ret_3m: 0.142,
    rs_1m: 0.042,
    rs_3m: 0.084,
    pct_above_ema21: 0.78,
    buy_signal_count: 14,
    ...overrides,
  }
}

describe('SectorHeroReadout — H4 leading count (true count, not display slice)', () => {
  it('badge reflects all 6 leading sectors even though only 4 rows render', () => {
    // 6 rows with rs_3m > 0 AND rs_1m > rs_3m (rising momentum) → all Leading, none
    // weakening, so the "6 sectors" count is unique to the Leading badge.
    const rows = Array.from({ length: 6 }, (_, i) =>
      makeRow({ sector_name: `Sector ${i}`, rs_1m: 0.3, rs_3m: 0.2 - i * 0.01 }),
    )
    render(<SectorHeroReadout rows={rows} />)
    // True count, not capped at the 4-row slice.
    expect(screen.getByText(/6 sectors/)).toBeInTheDocument()
    // "+ N others" must also use the true count (5), not slice-1 (3).
    expect(screen.getByText(/\+ 5 others carrying the tape/)).toBeInTheDocument()
  })
})
