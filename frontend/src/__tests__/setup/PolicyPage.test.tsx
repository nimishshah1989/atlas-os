// Tests for /setup/policy components:
//   - PolicyPageClient (selector + save wiring in setup/PolicyPageClient.tsx)
//
// The page shell is RSC; we test the client island directly.
// Covers:
//   - Renders PolicyEditor with the supplied policy
//   - Portfolio selector renders with "House Default" option
//   - Selector shows each portfolio in the list
//   - onSave wires to POST /api/policy; success shows confirmation + updated policy
//   - onSave error shows error message without losing the editor
//   - Changing selector to a portfolio triggers onPortfolioChange callback

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { PolicyPageClient } from '@/components/setup/PolicyPageClient'
import type { EffectivePolicy } from '@/components/portfolio/PolicyPanel'
import type { PortfolioListRow } from '@/lib/queries/portfolios'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makePolicy(): EffectivePolicy {
  return {
    cash_floor_pct:         { value: '5', source: 'inherited' },
    respect_regime_cap:     { value: true, source: 'inherited' },
    max_per_stock_pct:      { value: '8', source: 'inherited' },
    max_per_sector_pct:     { value: '20', source: 'inherited' },
    max_small_cap_pct:      { value: '30', source: 'inherited' },
    min_holdings:           { value: '10', source: 'inherited' },
    max_positions:          { value: '25', source: 'inherited' },
    buy_states:             { value: ['stage_1', 'stage_2a'], source: 'inherited' },
    min_within_state_rank:  { value: '0.60', source: 'inherited' },
    min_rs_rank:            { value: '0.70', source: 'inherited' },
    hard_stop_pct:          { value: '8', source: 'inherited' },
    state_exit_trim:        { value: 'stage_3', source: 'inherited' },
    state_exit_full:        { value: 'stage_4', source: 'inherited' },
    trailing_stop_pct:      { value: null, source: 'inherited' },
    instrument_universe:    { value: 'direct_equity', source: 'inherited' },
    benchmark:              { value: 'NIFTY_500', source: 'inherited' },
    rebalance_cadence:      { value: 'weekly', source: 'inherited' },
  }
}

const PORTFOLIOS: PortfolioListRow[] = [
  {
    id: 'p-uuid-1',
    name: 'Banking Leaders',
    type: 'static',
    instrument_count: 10,
    latest_sharpe: '1.2',
    paper_trading_active: false,
    created_at: new Date('2026-01-01'),
  },
  {
    id: 'p-uuid-2',
    name: 'Tech Core',
    type: 'rule-based',
    instrument_count: null,
    latest_sharpe: null,
    paper_trading_active: false,
    created_at: new Date('2026-02-01'),
  },
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderClient(overrides: {
  portfolioId?: string | null
  onPortfolioChange?: (id: string | null) => void
} = {}) {
  const onPortfolioChange = overrides.onPortfolioChange ?? vi.fn()
  return render(
    <PolicyPageClient
      policy={makePolicy()}
      portfolioId={overrides.portfolioId ?? null}
      portfolios={PORTFOLIOS}
      onPortfolioChange={onPortfolioChange}
    />,
  )
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PolicyPageClient — portfolio selector', () => {
  it('renders a "House Default" option in the selector', () => {
    renderClient()
    expect(screen.getByRole('option', { name: /house default/i })).toBeInTheDocument()
  })

  it('renders each portfolio by name in the selector', () => {
    renderClient()
    expect(screen.getByRole('option', { name: /Banking Leaders/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Tech Core/i })).toBeInTheDocument()
  })

  it('calls onPortfolioChange with selected portfolio id when changed', () => {
    const onPortfolioChange = vi.fn()
    renderClient({ onPortfolioChange })
    const select = screen.getByRole('combobox', { name: /editing policy for/i })
    fireEvent.change(select, { target: { value: 'p-uuid-1' } })
    expect(onPortfolioChange).toHaveBeenCalledWith('p-uuid-1')
  })

  it('calls onPortfolioChange with null when "House Default" selected', () => {
    const onPortfolioChange = vi.fn()
    renderClient({ portfolioId: 'p-uuid-1', onPortfolioChange })
    const select = screen.getByRole('combobox', { name: /editing policy for/i })
    fireEvent.change(select, { target: { value: '' } })
    expect(onPortfolioChange).toHaveBeenCalledWith(null)
  })
})

describe('PolicyPageClient — PolicyEditor rendered', () => {
  it('renders the PolicyEditor (policy group headings visible)', () => {
    renderClient()
    expect(screen.getByText(/deployment/i)).toBeInTheDocument()
  })
})

describe('PolicyPageClient — save wiring (house default)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('POSTs to /api/policy with portfolioId=null and changes on save', async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: makePolicy() }),
    })
    vi.stubGlobal('fetch', mockFetch)

    renderClient({ portfolioId: null })

    // The PolicyEditor Save button is only enabled after a change.
    // Simulate a save by directly firing the onSave that PolicyEditor calls.
    // We find the Save button is disabled (no changes yet) — this is correct
    // per spec. We just verify fetch would be called correctly.
    // For a unit test, mock-trigger the save via a change + click.
    // Change cash_floor_pct:
    const input = screen.getByTestId('input-cash_floor_pct')
    fireEvent.change(input, { target: { value: '7' } })

    const saveBtn = screen.getByRole('button', { name: /save/i })
    fireEvent.click(saveBtn)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/policy',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
        }),
      )
    })

    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.portfolioId).toBeNull()
    expect(body.changes).toHaveProperty('cash_floor_pct')
  })

  it('shows confirmation after successful save', async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: makePolicy() }),
    })
    vi.stubGlobal('fetch', mockFetch)

    renderClient({ portfolioId: null })

    const input = screen.getByTestId('input-cash_floor_pct')
    fireEvent.change(input, { target: { value: '7' } })
    fireEvent.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() => {
      expect(screen.getByTestId('save-success')).toBeInTheDocument()
    })
  })

  it('shows error message (from error_code) without losing editor on API error', async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      json: async () => ({
        error_code: 'policy_violation',
        message: 'max_per_stock_pct must be < max_per_sector_pct',
      }),
    })
    vi.stubGlobal('fetch', mockFetch)

    renderClient({ portfolioId: null })

    const input = screen.getByTestId('input-cash_floor_pct')
    fireEvent.change(input, { target: { value: '7' } })
    fireEvent.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() => {
      expect(screen.getByTestId('save-error')).toBeInTheDocument()
      expect(screen.getByTestId('save-error')).toHaveTextContent(
        'max_per_stock_pct must be < max_per_sector_pct',
      )
    })

    // PolicyEditor is still present
    expect(screen.getByText(/deployment/i)).toBeInTheDocument()
  })
})
