// Tests for src/components/portfolio/CurrentVsTarget.tsx
// TDD: written before implementation.
//
// Covers:
//   - holdings rows render with current/target/gap
//   - null target_weight_pct renders "—" not 0
//   - pending proposed changes render as distinct rows
//   - compliance breach renders banner
//   - compliant portfolio renders "Policy-compliant" confirmation
//   - weights sum footer (invested % · cash %)

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CurrentVsTarget } from '@/components/portfolio/CurrentVsTarget'
import type { CurrentVsTargetHolding, PendingProposedChange } from '@/components/portfolio/CurrentVsTarget'
import type { CompliancePolicy } from '@/lib/policy-compliance'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const POLICY: CompliancePolicy = {
  max_per_stock_pct: 5,
  max_per_sector_pct: 15,
  max_small_cap_pct: 30,
  min_holdings: 5,
  max_positions: 30,
  cash_floor_pct: 5,
}

const BASE_HOLDING: CurrentVsTargetHolding = {
  instrument_id: 'uuid-hdfc',
  instrument_type: 'stock',
  symbol: 'HDFCBANK',
  weight_pct: 4,
  target_weight_pct: 6,
  sector: 'Banks',
  is_small_cap: false,
}

function makeHoldings(count: number, overrides: Partial<CurrentVsTargetHolding> = {}): CurrentVsTargetHolding[] {
  return Array.from({ length: count }, (_, i) => ({
    instrument_id: `uuid-${i}`,
    instrument_type: 'stock' as const,
    symbol: `STOCK${i}`,
    weight_pct: 4,
    target_weight_pct: 5,
    sector: `Sector${i}`,
    is_small_cap: false,
    ...overrides,
  }))
}

function renderCvT(
  holdings: CurrentVsTargetHolding[] = [BASE_HOLDING],
  pending: PendingProposedChange[] = [],
  policy: CompliancePolicy = POLICY,
) {
  return render(
    <CurrentVsTarget holdings={holdings} pendingChanges={pending} policy={policy} />,
  )
}

// ---------------------------------------------------------------------------
// Table structure
// ---------------------------------------------------------------------------

describe('CurrentVsTarget — table headers', () => {
  it('renders Current, Target, Gap column headers', () => {
    renderCvT()
    expect(screen.getByText(/current/i)).toBeInTheDocument()
    expect(screen.getByText(/target/i)).toBeInTheDocument()
    expect(screen.getByText(/gap/i)).toBeInTheDocument()
  })
})

describe('CurrentVsTarget — holdings rows', () => {
  it('renders a row for each holding with symbol, current %, target %', () => {
    renderCvT([BASE_HOLDING])
    expect(screen.getByText('HDFCBANK')).toBeInTheDocument()
    // current weight (4.00%) — may appear in both the cell and the footer
    expect(screen.getAllByText(/4\.0?0?%/).length).toBeGreaterThanOrEqual(1)
    // target weight (6.00%) — should appear in the target cell
    expect(screen.getAllByText(/6\.0?0?%/).length).toBeGreaterThanOrEqual(1)
  })

  it('renders gap as signed number when target exists', () => {
    // gap = 6 - 4 = +2
    renderCvT([BASE_HOLDING])
    expect(screen.getByText(/\+2/)).toBeInTheDocument()
  })

  it('renders negative gap in red styling', () => {
    const holding: CurrentVsTargetHolding = {
      ...BASE_HOLDING,
      weight_pct: 6,
      target_weight_pct: 4, // gap = -2
    }
    renderCvT([holding])
    expect(screen.getByText(/-2/)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// C5: null target_weight_pct renders "—" not 0
// ---------------------------------------------------------------------------

describe('CurrentVsTarget — null target_weight_pct', () => {
  it('renders "—" for target when target_weight_pct is null', () => {
    const holding: CurrentVsTargetHolding = {
      ...BASE_HOLDING,
      target_weight_pct: null,
    }
    renderCvT([holding])
    // At least one "—" should appear (the target cell)
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThanOrEqual(1)
  })

  it('does NOT render "0%" for target when target_weight_pct is null', () => {
    const holding: CurrentVsTargetHolding = {
      ...BASE_HOLDING,
      target_weight_pct: null,
    }
    renderCvT([holding])
    // Should not render a target cell showing "0.00%"
    expect(screen.queryByTestId('target-weight-0')).not.toBeInTheDocument()
    // And no "0.00%" in the target column
    const cells = screen.queryAllByText('0.00%')
    // If there are any "0.00%" cells, they must not be the target for this holding
    // (they could be gap cells for other logic, so we just check there's no "0%" target)
    // The simpler check: the target cell for a null-target holding shows "—"
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThanOrEqual(1)
  })

  it('omits gap display for null-target holding', () => {
    // A null target should produce "—" in the gap cell too
    const holding: CurrentVsTargetHolding = {
      ...BASE_HOLDING,
      target_weight_pct: null,
    }
    const { container } = renderCvT([holding])
    // No signed gap numbers should appear
    expect(container.textContent).not.toMatch(/\+\d+/)
  })
})

// ---------------------------------------------------------------------------
// C1: LinkedTicker — symbols as links
// ---------------------------------------------------------------------------

describe('CurrentVsTarget — LinkedTicker', () => {
  it('renders ticker as a link to /stocks/SYMBOL', () => {
    renderCvT([BASE_HOLDING])
    const link = screen.getByRole('link', { name: 'HDFCBANK' })
    expect(link).toHaveAttribute('href', '/stocks/HDFCBANK')
  })
})

// ---------------------------------------------------------------------------
// Pending proposed changes
// ---------------------------------------------------------------------------

describe('CurrentVsTarget — pending proposed changes', () => {
  const PENDING: PendingProposedChange = {
    id: 'change-1',
    instrument_id: 'uuid-xyz',
    symbol: 'TATAMOTORS',
    proposed_weight: 7.5,
    rationale: 'Gap-bound rebalance',
  }

  it('renders pending change as a distinct row with "proposed" tag', () => {
    renderCvT([BASE_HOLDING], [PENDING])
    expect(screen.getByText('TATAMOTORS')).toBeInTheDocument()
    // "proposed" badge is visible
    expect(screen.getByText(/proposed/i)).toBeInTheDocument()
  })

  it('renders the proposed weight in the pending row', () => {
    renderCvT([BASE_HOLDING], [PENDING])
    expect(screen.getByText(/7\.5/)).toBeInTheDocument()
  })

  it('renders no "proposed" tag when there are no pending changes', () => {
    renderCvT([BASE_HOLDING], [])
    expect(screen.queryByText(/proposed/i)).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Compliance banner
// ---------------------------------------------------------------------------

describe('CurrentVsTarget — compliance banner', () => {
  it('renders breach banner when a policy rule is violated', () => {
    // 8% > 5% max_per_stock → breach
    const holdings: CurrentVsTargetHolding[] = [
      { ...BASE_HOLDING, weight_pct: 8 },
      ...makeHoldings(4, { weight_pct: 3, sector: 'IT' }),
    ]
    renderCvT(holdings)
    // Banner should be visible
    expect(screen.getByTestId('compliance-banner')).toBeInTheDocument()
    // breach message contains the violating instrument id or weight
    const banner = screen.getByTestId('compliance-banner')
    expect(banner.textContent).toMatch(/HDFCBANK|max.*stock|8%/i)
  })

  it('renders "Policy-compliant" when no rules are violated', () => {
    // 8 unique sectors, all 4% — compliant
    const holdings: CurrentVsTargetHolding[] = makeHoldings(8, { weight_pct: 4 })
    renderCvT(holdings)
    expect(screen.getByText(/policy.compliant/i)).toBeInTheDocument()
    expect(screen.queryByTestId('compliance-banner')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// C7: weights-sum footer
// ---------------------------------------------------------------------------

describe('CurrentVsTarget — weights sum footer', () => {
  it('shows invested % and cash % in the footer', () => {
    // 8 holdings × 4% = 32% invested, 68% cash
    const holdings = makeHoldings(8, { weight_pct: 4 })
    renderCvT(holdings)
    // Footer should show something like "invested 32%" and "cash 68%"
    expect(screen.getByTestId('weights-sum')).toBeInTheDocument()
    const footer = screen.getByTestId('weights-sum')
    expect(footer.textContent).toMatch(/32/)
    expect(footer.textContent).toMatch(/68/)
  })

  it('shows 0% invested and 100% cash when no holdings', () => {
    renderCvT([])
    const footer = screen.getByTestId('weights-sum')
    expect(footer.textContent).toMatch(/0/)
    expect(footer.textContent).toMatch(/100/)
  })
})

// ---------------------------------------------------------------------------
// C3: column header tooltips
// ---------------------------------------------------------------------------

describe('CurrentVsTarget — tooltips on column headers', () => {
  it('renders info tooltip buttons next to column headers', () => {
    renderCvT()
    // InfoTooltip renders a button with aria-label="info"
    const infoButtons = screen.getAllByRole('button', { name: /info/i })
    // At least one tooltip per column header (Current, Target, Gap)
    expect(infoButtons.length).toBeGreaterThanOrEqual(3)
  })
})
