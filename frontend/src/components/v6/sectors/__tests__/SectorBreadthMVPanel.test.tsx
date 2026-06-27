// frontend/src/components/v6/sectors/__tests__/SectorBreadthMVPanel.test.tsx
// Tests for SectorBreadthMVPanel: empty state, per-sector cards, EMA labels,
// top movers, constituent count, testid.
// (SectorHeroReadout has its own spec — SectorHeroReadout.test.tsx — now that it
// classifies leading/lagging from corrected RS, not the retired rrg quadrant.)

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('@/lib/queries/v6/sectors', () => ({}))
vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({ default: vi.fn() }))

import { SectorBreadthMVPanel } from '../SectorBreadthMVPanel'
import type { SectorBreadthMVRow } from '@/lib/queries/v6/sectors'

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeBreadthRow(overrides: Partial<SectorBreadthMVRow> = {}): SectorBreadthMVRow {
  return {
    as_of_date: '2026-05-27',
    sector_name: 'Energy',
    constituent_count: 62,
    pct_above_ema21: 0.72,
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
    expect(screen.getAllByText(/Above EMA21/).length).toBeGreaterThan(0)
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
