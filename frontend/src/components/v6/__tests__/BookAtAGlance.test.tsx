// frontend/src/components/v6/__tests__/BookAtAGlance.test.tsx
//
// 4 test cases:
//   1. Renders null (silent absence) when totalHeld is 0
//   2. Renders verdict counts correctly
//   3. Renders flipped positions when present
//   4. Renders CTA link to /v6/screening?filter=unacted

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BookAtAGlance } from '../BookAtAGlance'
import type { BookDiff } from '@/lib/queries/v6/book_diff'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const EMPTY_BOOK_DIFF: BookDiff = {
  held_iids_flipped: [],
  held_drift_warns: [],
}

const BOOK_DIFF_WITH_FLIPS: BookDiff = {
  held_iids_flipped: [
    {
      instrument_id: 'uuid-tcs',
      ticker: 'TCS',
      yesterday_action: 'NEUTRAL',
      today_action: 'POSITIVE',
      date_changed: '2026-05-26',
    },
    {
      instrument_id: 'uuid-infy',
      ticker: 'INFY',
      yesterday_action: 'POSITIVE',
      today_action: 'NEGATIVE',
      date_changed: '2026-05-26',
    },
  ],
  held_drift_warns: [],
}

const VERDICT_WITH_HOLDINGS = { positive: 5, neutral: 3, negative: 2 }
const VERDICT_EMPTY = { positive: 0, neutral: 0, negative: 0 }

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('BookAtAGlance', () => {
  it('renders null (silent absence) when book is empty', () => {
    const { container } = render(
      <BookAtAGlance bookDiff={EMPTY_BOOK_DIFF} heldByVerdict={VERDICT_EMPTY} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders POSITIVE / NEUTRAL / NEGATIVE counts with correct values', () => {
    render(
      <BookAtAGlance bookDiff={EMPTY_BOOK_DIFF} heldByVerdict={VERDICT_WITH_HOLDINGS} />,
    )
    // Each stat pill renders count + label
    expect(screen.getByText('5')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('POSITIVE')).toBeInTheDocument()
    expect(screen.getByText('NEUTRAL')).toBeInTheDocument()
    expect(screen.getByText('NEGATIVE')).toBeInTheDocument()
  })

  it('renders flipped positions list when flips exist', () => {
    render(
      <BookAtAGlance bookDiff={BOOK_DIFF_WITH_FLIPS} heldByVerdict={VERDICT_WITH_HOLDINGS} />,
    )
    expect(screen.getByText('TCS')).toBeInTheDocument()
    expect(screen.getByText('INFY')).toBeInTheDocument()
    expect(screen.getByText(/2 flipped overnight/i)).toBeInTheDocument()
  })

  it('renders CTA link pointing to /v6/screening?filter=unacted', () => {
    render(
      <BookAtAGlance bookDiff={EMPTY_BOOK_DIFF} heldByVerdict={VERDICT_WITH_HOLDINGS} />,
    )
    const link = screen.getByRole('link', { name: /view calls you haven.t acted on/i })
    expect(link).toHaveAttribute('href', '/v6/screening?filter=unacted')
  })
})
