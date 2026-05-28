// frontend/src/components/v6/sectors/__tests__/SectorBreadthMVPanel.test.tsx
// Tests for SectorBreadthMVPanel and SectorHeroReadout (with rrg prop — M14).
//
// Coverage:
//   - SectorBreadthMVPanel: empty state, renders per-sector cards, EMA labels
//   - SectorHeroReadout: uses quadrant_current from rrg data (M14)

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('@/lib/queries/v6/sectors', () => ({}))
vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({ default: vi.fn() }))

import { SectorBreadthMVPanel } from '../SectorBreadthMVPanel'
import { SectorHeroReadout } from '../SectorHeroReadout'
import type { SectorBreadthMVRow, SectorCardRow, SectorRRGRow } from '@/lib/queries/v6/sectors'

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeBreadthRow(overrides: Partial<SectorBreadthMVRow> = {}): SectorBreadthMVRow {
  return {
    as_of_date: '2026-05-27',
    sector_name: 'Energy',
    constituent_count: 62,
    pct_above_ema20: 0.72,
    pct_above_ema50: 0.65,
    pct_above_ema200: 0.55,
    pct_at_52wh: 0.18,
    breadth_by_window: [],
    breadth_by_strength: null,
    top_movers: [{ symbol: 'ONGC', ret_pct: 4.2 }],
    bottom_movers: [],
    ...overrides,
  }
}

function makeCardRow(overrides: Partial<SectorCardRow> = {}): SectorCardRow {
  return {
    as_of_date: '2026-05-27',
    sector_name: 'Energy',
    constituent_count: 62,
    ret_1w: 0.02,
    ret_1m: 0.05,
    ret_3m: 0.12,
    ret_6m: 0.18,
    ret_12m: 0.25,
    rs_1m: 0.03,
    rs_3m: 0.08,
    rs_6m: 0.10,
    vol_60d_ann: 0.22,
    pct_above_ema20: 0.72,
    pct_above_ema200: 0.55,
    pct_at_52wh: 0.18,
    hhi_concentration: 0.12,
    buy_signal_count: 4,
    confidence_distribution: { H: 2, M: 1, L: 1 },
    verdict: 'Overweight',
    verdict_abbr: 'OW',
    ...overrides,
  }
}

function makeRRGRow(overrides: Partial<SectorRRGRow> = {}): SectorRRGRow {
  return {
    as_of_date: '2026-05-27',
    sector_name: 'Energy',
    rs_ratio_current: 105.2,
    rs_momentum_current: 2.4,
    quadrant_current: 'Leading',
    trail_6w: [],
    constituent_count: 62,
    ...overrides,
  }
}

// ── SectorBreadthMVPanel tests ─────────────────────────────────────────────────

describe('SectorBreadthMVPanel', () => {
  it('renders empty state when rows is empty', () => {
    render(<SectorBreadthMVPanel rows={[]} />)
    expect(screen.getByText(/Breadth data unavailable/i)).toBeTruthy()
  })

  it('renders a card for each sector row', () => {
    const rows = [
      makeBreadthRow({ sector_name: 'Energy' }),
      makeBreadthRow({ sector_name: 'IT', top_movers: [] }),
    ]
    render(<SectorBreadthMVPanel rows={rows} />)
    expect(screen.getByText('Energy')).toBeTruthy()
    expect(screen.getByText('IT')).toBeTruthy()
  })

  it('renders EMA gauge labels', () => {
    render(<SectorBreadthMVPanel rows={[makeBreadthRow()]} />)
    expect(screen.getAllByText(/Above EMA20/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Above EMA50/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Above EMA200/).length).toBeGreaterThan(0)
  })

  it('renders top movers when present', () => {
    const row = makeBreadthRow({ top_movers: [{ symbol: 'ONGC', ret_pct: 4.2 }] })
    render(<SectorBreadthMVPanel rows={[row]} />)
    expect(screen.getByText(/ONGC/)).toBeTruthy()
  })

  it('renders constituent count', () => {
    render(<SectorBreadthMVPanel rows={[makeBreadthRow({ constituent_count: 42 })]} />)
    expect(screen.getByText(/42 stocks/)).toBeTruthy()
  })

  it('renders the panel testid', () => {
    render(<SectorBreadthMVPanel rows={[makeBreadthRow()]} />)
    expect(screen.getByTestId('sector-breadth-mv-panel')).toBeTruthy()
  })
})

// ── SectorHeroReadout with rrg prop (M14) ────────────────────────────────────

describe('SectorHeroReadout with rrg quadrant data', () => {
  it('uses quadrant_current from rrg to classify leading sectors', () => {
    const cards = [
      makeCardRow({ sector_name: 'Energy', rs_3m: -0.05 }), // negative rs, but RRG says Leading
      makeCardRow({ sector_name: 'IT', rs_3m: 0.08, verdict_abbr: 'OW' }),
    ]
    const rrg = [
      makeRRGRow({ sector_name: 'Energy', quadrant_current: 'Leading' }),
      makeRRGRow({ sector_name: 'IT', quadrant_current: 'Lagging' }),
    ]
    render(<SectorHeroReadout cards={cards} rrg={rrg} />)
    // Energy should appear in leading column despite negative rs_3m (M14 fix)
    const leadingTitle = screen.getByTestId('leading-title')
    expect(leadingTitle.textContent).toContain('Energy')
  })

  it('falls back to rs_3m heuristic when rrg is not provided', () => {
    const cards = [
      makeCardRow({ sector_name: 'Energy', rs_3m: 0.12, verdict_abbr: 'OW' }),
    ]
    render(<SectorHeroReadout cards={cards} />)
    const leadingTitle = screen.getByTestId('leading-title')
    expect(leadingTitle.textContent).toContain('Energy')
  })

  it('renders empty state when cards is empty', () => {
    const { container } = render(<SectorHeroReadout cards={[]} />)
    expect(container.firstChild).toBeNull()
  })
})
