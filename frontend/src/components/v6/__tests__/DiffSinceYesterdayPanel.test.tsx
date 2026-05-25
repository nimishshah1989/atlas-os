// frontend/src/components/v6/__tests__/DiffSinceYesterdayPanel.test.tsx
//
// 5 test cases:
//   1. Empty state renders "No changes since yesterday's snapshot"
//   2. New cells firing section renders cell IDs
//   3. Dormant cells section renders
//   4. Held iids flipped section renders ticker + state-change badges
//   5. DriftWarnChip renders with correct count and correct link

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DiffSinceYesterdayPanel } from '../DiffSinceYesterdayPanel'
import type { MatrixDiff } from '@/lib/queries/v6/matrix_diff'
import type { BookDiff } from '@/lib/queries/v6/book_diff'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const EMPTY_MATRIX_DIFF: MatrixDiff = {
  new_cells_firing: [],
  cells_dormant: [],
  new_drift_warns: [],
}

const EMPTY_BOOK_DIFF: BookDiff = {
  held_iids_flipped: [],
  held_drift_warns: [],
}

const MATRIX_WITH_NEW_FIRING: MatrixDiff = {
  new_cells_firing: [
    {
      cell_id: 'Mid_12m_Pullback',
      cap_tier: 'Mid',
      tenure: '12m',
      action: 'POSITIVE',
      grade: 'AA',
      confidence_unconditional: '0.82',
      date_changed: '2026-05-26',
    },
  ],
  cells_dormant: [],
  new_drift_warns: [],
}

const MATRIX_WITH_DORMANT: MatrixDiff = {
  new_cells_firing: [],
  cells_dormant: [
    {
      cell_id: 'Large_3m_Breakout',
      cap_tier: 'Large',
      tenure: '3m',
      action: 'POSITIVE',
      grade: 'A',
      confidence_unconditional: '0.71',
      date_changed: '2026-05-25',
    },
  ],
  new_drift_warns: [],
}

const BOOK_WITH_FLIPS: BookDiff = {
  held_iids_flipped: [
    {
      instrument_id: 'uuid-reliance',
      ticker: 'RELIANCE',
      yesterday_action: 'NEUTRAL',
      today_action: 'POSITIVE',
      date_changed: '2026-05-26',
    },
  ],
  held_drift_warns: [],
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('DiffSinceYesterdayPanel', () => {
  it('renders empty-state microcopy when no changes exist', () => {
    render(
      <DiffSinceYesterdayPanel
        matrixDiff={EMPTY_MATRIX_DIFF}
        bookDiff={EMPTY_BOOK_DIFF}
        activeCellsToday={12}
        signalCallsOvernight={47}
        driftWarnCount={0}
      />,
    )
    expect(screen.getByText(/no changes since yesterday/i)).toBeInTheDocument()
  })

  it('renders new cells firing section with cell ID link', () => {
    render(
      <DiffSinceYesterdayPanel
        matrixDiff={MATRIX_WITH_NEW_FIRING}
        bookDiff={EMPTY_BOOK_DIFF}
        activeCellsToday={13}
        signalCallsOvernight={50}
        driftWarnCount={0}
      />,
    )
    expect(screen.getByText('Mid_12m_Pullback')).toBeInTheDocument()
    expect(screen.getByText(/new cells firing/i)).toBeInTheDocument()
  })

  it('renders cells gone dormant section', () => {
    render(
      <DiffSinceYesterdayPanel
        matrixDiff={MATRIX_WITH_DORMANT}
        bookDiff={EMPTY_BOOK_DIFF}
        activeCellsToday={11}
        signalCallsOvernight={30}
        driftWarnCount={0}
      />,
    )
    expect(screen.getByText('Large_3m_Breakout')).toBeInTheDocument()
    expect(screen.getByText(/cells gone dormant/i)).toBeInTheDocument()
  })

  it('renders held positions flipped section with ticker and state badges', () => {
    render(
      <DiffSinceYesterdayPanel
        matrixDiff={EMPTY_MATRIX_DIFF}
        bookDiff={BOOK_WITH_FLIPS}
        activeCellsToday={12}
        signalCallsOvernight={47}
        driftWarnCount={0}
      />,
    )
    expect(screen.getByText('RELIANCE')).toBeInTheDocument()
    expect(screen.getByText(/held positions flipped/i)).toBeInTheDocument()
    // Both state badges should render
    const neutralBadges = screen.getAllByText('NEUTRAL')
    expect(neutralBadges.length).toBeGreaterThan(0)
    const posBadges = screen.getAllByText('POSITIVE')
    expect(posBadges.length).toBeGreaterThan(0)
  })

  it('renders drift_warn chip with count and link to methodology anchor (D.12)', () => {
    render(
      <DiffSinceYesterdayPanel
        matrixDiff={EMPTY_MATRIX_DIFF}
        bookDiff={EMPTY_BOOK_DIFF}
        activeCellsToday={12}
        signalCallsOvernight={47}
        driftWarnCount={3}
      />,
    )
    const chip = screen.getByRole('link', { name: /3 cells in drift_warn/i })
    expect(chip).toBeInTheDocument()
    expect(chip).toHaveAttribute('href', '/methodology#drift-warn-section')
  })
})
