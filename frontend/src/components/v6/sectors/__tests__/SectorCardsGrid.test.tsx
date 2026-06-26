// frontend/src/components/v6/sectors/__tests__/SectorCardsGrid.test.tsx
// Tests for SectorCardsGrid component.
//
// Coverage:
//   - Empty state renders correctly
//   - Cards sorted OW > NW > UW by default
//   - Each card renders sector name, verdict chip, and return metrics
//   - Cards link to /sectors/[name]
//   - Negative returns formatted correctly
//   - Null returns shown as em-dash

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'

// ── Module mocks (must be before imports that trigger module evaluation) ──────
// Mock the query module FIRST to prevent sectors.ts → db.ts → postgres from
// attempting a real Supabase connection during worker initialization.

vi.mock('@/lib/queries/v6/sectors', () => ({}))
vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({ default: vi.fn() }))

// ── next/link mock ────────────────────────────────────────────────────────────

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode; [k: string]: unknown }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}))

// ── Import AFTER mock ─────────────────────────────────────────────────────────

import { SectorCardsGrid } from '../SectorCardsGrid'
import type { SectorCardRow } from '@/lib/queries/v6/sectors'

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeCard(overrides: Partial<SectorCardRow> = {}): SectorCardRow {
  return {
    as_of_date: '2026-05-27',
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

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('SectorCardsGrid', () => {
  it('renders empty state when no cards', () => {
    render(<SectorCardsGrid cards={[]} />)
    expect(screen.getByText(/No sector card data available/i)).toBeTruthy()
  })

  it('renders a card for each sector', () => {
    const cards = [
      makeCard({ sector_name: 'Energy', verdict_abbr: 'OW' }),
      makeCard({ sector_name: 'IT',     verdict_abbr: 'UW', rs_3m: -0.051 }),
      makeCard({ sector_name: 'Auto',   verdict_abbr: 'NW', rs_3m: 0.01 }),
    ]
    render(<SectorCardsGrid cards={cards} />)
    expect(screen.getByTestId('sector-card-Energy')).toBeTruthy()
    expect(screen.getByTestId('sector-card-IT')).toBeTruthy()
    expect(screen.getByTestId('sector-card-Auto')).toBeTruthy()
  })

  it('sorts OW before NW before UW', () => {
    const cards = [
      makeCard({ sector_name: 'IT',     verdict_abbr: 'UW', rs_3m: -0.05 }),
      makeCard({ sector_name: 'Auto',   verdict_abbr: 'NW', rs_3m: 0.01 }),
      makeCard({ sector_name: 'Energy', verdict_abbr: 'OW', rs_3m: 0.084 }),
    ]
    render(<SectorCardsGrid cards={cards} />)
    const grid = screen.getByTestId('sector-cards-grid')
    const cardElements = grid.querySelectorAll('[data-testid^="sector-card-"]')
    expect(cardElements[0].getAttribute('data-testid')).toBe('sector-card-Energy')
    expect(cardElements[2].getAttribute('data-testid')).toBe('sector-card-IT')
  })

  it('links to /sectors/[name]', () => {
    render(<SectorCardsGrid cards={[makeCard({ sector_name: 'Energy' })]} />)
    const link = screen.getByTestId('sector-card-Energy') as HTMLAnchorElement
    expect(link.getAttribute('href')).toBe('/sectors/Energy')
  })

  it('renders RS and return values with sign', () => {
    render(<SectorCardsGrid cards={[makeCard()]} />)
    // rs_3m = 0.084 → +8.4pp
    expect(screen.getByText('+8.4pp')).toBeTruthy()
    // ret_1m = 0.068 → +6.8%
    expect(screen.getByText('+6.8%')).toBeTruthy()
  })

  it('renders negative return correctly', () => {
    render(<SectorCardsGrid cards={[
      makeCard({ sector_name: 'IT', verdict_abbr: 'UW', ret_1m: -0.059, rs_3m: -0.051 }),
    ]} />)
    expect(screen.getByText('-5.9%')).toBeTruthy()
    expect(screen.getByText('-5.1pp')).toBeTruthy()
  })

  it('renders null returns as em-dash', () => {
    render(<SectorCardsGrid cards={[makeCard({ ret_1m: null, rs_3m: null })]} />)
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThan(0)
  })

  it('shows constituent count and buy signals', () => {
    render(<SectorCardsGrid cards={[makeCard({ constituent_count: 62, buy_signal_count: 14 })]} />)
    expect(screen.getByText(/62 stocks.*14 BUY open/)).toBeTruthy()
  })

  it('does not show buy signals text when buy_signal_count is 0', () => {
    render(<SectorCardsGrid cards={[makeCard({ buy_signal_count: 0 })]} />)
    expect(screen.getByText(/62 stocks$/)).toBeTruthy()
  })
})
