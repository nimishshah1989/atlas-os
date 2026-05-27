// frontend/src/components/v6/__tests__/IndustrySnapshot.test.tsx
//
// 4 test cases:
//   1. Renders 3 stat tiles (Leaders, Avoid, Total in scope)
//   2. Renders AMC leaderboard with N rows
//   3. Empty leaderboard: shows "Insufficient data" placeholder
//   4. ARIA labels on stat tiles

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { IndustrySnapshot } from '../IndustrySnapshot'
import type { IndustrySnapshot as IndustrySnapshotData } from '@/lib/queries/v6/industry_snapshot'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeSnapshot(
  overrides: Partial<IndustrySnapshotData> = {},
): IndustrySnapshotData {
  return {
    asset_class: 'funds',
    n_total: 120,
    n_atlas_leaders: 18,
    n_avoid: 12,
    pct_above_benchmark_3y: null,
    median_expense: '0.92',
    median_aum_cr: '2450',
    amc_leaderboard: [
      { amc: 'Mirae Asset', avg_composite: '72.50', n_funds: 8 },
      { amc: 'HDFC AMC', avg_composite: '69.10', n_funds: 12 },
      { amc: 'Axis AMC', avg_composite: '65.80', n_funds: 10 },
    ],
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Test 1: Renders 3 stat tiles
// ---------------------------------------------------------------------------

describe('IndustrySnapshot — stat tiles', () => {
  it('renders 3 primary stat tiles with correct values', () => {
    render(<IndustrySnapshot snapshot={makeSnapshot()} />)

    // The three primary stat tiles
    expect(screen.getByText('18')).toBeInTheDocument()   // n_atlas_leaders
    expect(screen.getByText('12')).toBeInTheDocument()   // n_avoid
    expect(screen.getByText('120')).toBeInTheDocument()  // n_total

    // Labels
    expect(screen.getByText('Atlas Leaders')).toBeInTheDocument()
    expect(screen.getByText('Atlas Avoid')).toBeInTheDocument()
    expect(screen.getByText('Total in scope')).toBeInTheDocument()
  })

  it('renders median expense and AUM tiles', () => {
    render(<IndustrySnapshot snapshot={makeSnapshot()} />)

    expect(screen.getByText('0.92%')).toBeInTheDocument()
    expect(screen.getByText('₹2450 Cr')).toBeInTheDocument()
    expect(screen.getByText('Avg Expense Ratio')).toBeInTheDocument()
    expect(screen.getByText('Avg AUM')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 2: Renders AMC leaderboard with N rows
// ---------------------------------------------------------------------------

describe('IndustrySnapshot — AMC leaderboard', () => {
  it('renders leaderboard rows for all AMC entries', () => {
    render(<IndustrySnapshot snapshot={makeSnapshot()} />)

    // All AMC names appear
    expect(screen.getByText('Mirae Asset')).toBeInTheDocument()
    expect(screen.getByText('HDFC AMC')).toBeInTheDocument()
    expect(screen.getByText('Axis AMC')).toBeInTheDocument()

    // Composite scores appear
    expect(screen.getByText('72.5')).toBeInTheDocument()
    expect(screen.getByText('69.1')).toBeInTheDocument()

    // Rank numbers 1-3 appear
    expect(screen.getByText('1.')).toBeInTheDocument()
    expect(screen.getByText('2.')).toBeInTheDocument()
    expect(screen.getByText('3.')).toBeInTheDocument()
  })

  it('renders ETF leaderboard with "ETFs" label in count column', () => {
    const etfSnap = makeSnapshot({
      asset_class: 'etfs',
      amc_leaderboard: [
        { amc: 'Nippon India ETF', avg_composite: '68.00', n_funds: 5 },
        { amc: 'HDFC ETF', avg_composite: '65.50', n_funds: 4 },
      ],
    })
    render(<IndustrySnapshot snapshot={etfSnap} />)

    expect(screen.getByText('ETFs Industry')).toBeInTheDocument()
    expect(screen.getByText('Nippon India ETF')).toBeInTheDocument()

    // Count column shows "5 ETFs" (not "5 funds")
    const countLabels = screen.getAllByText(/\d+ ETFs/)
    expect(countLabels.length).toBeGreaterThan(0)
  })
})

// ---------------------------------------------------------------------------
// Test 3: Empty leaderboard shows "Insufficient data"
// ---------------------------------------------------------------------------

describe('IndustrySnapshot — empty leaderboard', () => {
  it('shows "Insufficient data" placeholder when amc_leaderboard is empty', () => {
    const snap = makeSnapshot({ amc_leaderboard: [] })
    render(<IndustrySnapshot snapshot={snap} />)

    expect(screen.getByText('Insufficient data')).toBeInTheDocument()

    // No AMC names should be visible
    expect(screen.queryByText('Mirae Asset')).toBeNull()
  })

  it('does not render leaderboard column headers when leaderboard is empty', () => {
    const snap = makeSnapshot({ amc_leaderboard: [] })
    const { container } = render(<IndustrySnapshot snapshot={snap} />)

    // Column header row should not exist (it's inside the non-empty branch)
    const leaderboardDiv = container.querySelector('[aria-label="AMC leaderboard"]')
    expect(leaderboardDiv).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Test 4: ARIA labels on stat tiles
// ---------------------------------------------------------------------------

describe('IndustrySnapshot — ARIA labels', () => {
  it('stat tiles have descriptive aria-label attributes', () => {
    render(<IndustrySnapshot snapshot={makeSnapshot()} />)

    expect(
      screen.getByRole('generic', { name: 'Atlas Leaders stat tile' })
        ?? document.querySelector('[aria-label="Atlas Leaders stat tile"]'),
    ).toBeTruthy()

    // All three primary tiles have aria-labels
    const leadTile = document.querySelector('[aria-label="Atlas Leaders stat tile"]')
    const avoidTile = document.querySelector('[aria-label="Atlas Avoid stat tile"]')
    const totalTile = document.querySelector('[aria-label="Total in scope stat tile"]')

    expect(leadTile).not.toBeNull()
    expect(avoidTile).not.toBeNull()
    expect(totalTile).not.toBeNull()
  })

  it('section has aria-label for screen readers', () => {
    render(<IndustrySnapshot snapshot={makeSnapshot()} />)

    const section = document.querySelector('[aria-label="Funds Industry snapshot"]')
    expect(section).not.toBeNull()
  })

  it('ETFs variant has correct section aria-label', () => {
    render(<IndustrySnapshot snapshot={makeSnapshot({ asset_class: 'etfs' })} />)

    const section = document.querySelector('[aria-label="ETFs Industry snapshot"]')
    expect(section).not.toBeNull()
  })
})
