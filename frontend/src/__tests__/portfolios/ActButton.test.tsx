// Tests for src/components/portfolio/ActButton.tsx
// Covers: disabled state with no portfolio, sized suggestion display,
//         constraint label rendering, submit flow (success + error).

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ActButton } from '@/components/portfolio/ActButton'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderNoPortfolio() {
  return render(
    <ActButton
      portfolioId={undefined}
      portfolioName={undefined}
      instrumentId="uuid-instrument-abc"
      suggestedPct={null}
      bindingConstraint={null}
      sectorGapApplied={false}
    />,
  )
}

function renderWithPortfolio(overrides: {
  suggestedPct?: string | null
  bindingConstraint?: string | null
  portfolioName?: string
  sectorGapApplied?: boolean
} = {}) {
  const {
    suggestedPct = '5.0',
    bindingConstraint = 'max_per_stock',
    portfolioName = 'My Portfolio',
    sectorGapApplied = false,
  } = overrides
  return render(
    <ActButton
      portfolioId="portfolio-uuid-123"
      portfolioName={portfolioName}
      instrumentId="uuid-instrument-abc"
      suggestedPct={suggestedPct}
      bindingConstraint={bindingConstraint}
      sectorGapApplied={sectorGapApplied}
    />,
  )
}

// ---------------------------------------------------------------------------
// Tests: disabled / no-portfolio state
// ---------------------------------------------------------------------------

describe('ActButton — no portfolio selected', () => {
  it('renders a disabled button with honest message', () => {
    renderNoPortfolio()
    // Should show some message about selecting a portfolio
    expect(screen.getByText(/select a portfolio/i)).toBeInTheDocument()
  })

  it('does not show any size number', () => {
    renderNoPortfolio()
    expect(screen.queryByText(/%/)).not.toBeInTheDocument()
  })

  it('button is disabled or not clickable', () => {
    renderNoPortfolio()
    // Find the button or a disabled element
    const btn = screen.queryByRole('button')
    if (btn) {
      expect(btn).toBeDisabled()
    } else {
      // Could also render as a non-button element in the disabled state
      expect(screen.getByText(/select a portfolio/i)).toBeInTheDocument()
    }
  })
})

// ---------------------------------------------------------------------------
// Tests: active portfolio with suggestion
// ---------------------------------------------------------------------------

describe('ActButton — with active portfolio', () => {
  it('shows portfolio name in the button label', () => {
    renderWithPortfolio({ portfolioName: 'Banking Leaders' })
    expect(screen.getByText(/Banking Leaders/)).toBeInTheDocument()
  })

  it('shows the suggested percentage', () => {
    renderWithPortfolio({ suggestedPct: '5.0', bindingConstraint: 'max_per_stock' })
    expect(screen.getByText(/5\.0%/)).toBeInTheDocument()
  })

  it('shows "stock-cap-bound" label for max_per_stock constraint', () => {
    renderWithPortfolio({ bindingConstraint: 'max_per_stock' })
    expect(screen.getByText(/stock-cap-bound/)).toBeInTheDocument()
  })

  it('shows "gap-bound" label for target_gap constraint', () => {
    renderWithPortfolio({ bindingConstraint: 'target_gap' })
    expect(screen.getByText(/gap-bound/)).toBeInTheDocument()
  })

  it('shows "regime-cap-bound" label for regime_cap constraint', () => {
    renderWithPortfolio({ bindingConstraint: 'regime_cap' })
    expect(screen.getByText(/regime-cap-bound/)).toBeInTheDocument()
  })

  it('disables submit button when suggestedPct is "0.0"', () => {
    renderWithPortfolio({ suggestedPct: '0.0', bindingConstraint: 'regime_cap' })
    const btn = screen.getByRole('button')
    expect(btn).toBeDisabled()
  })

  it('disables submit button when suggestedPct is null', () => {
    renderWithPortfolio({ suggestedPct: null, bindingConstraint: null })
    const btn = screen.getByRole('button')
    expect(btn).toBeDisabled()
  })
})

// ---------------------------------------------------------------------------
// Tests: click / POST flow
// ---------------------------------------------------------------------------

describe('ActButton — submit flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls fetch POST on click and shows confirmation on success', async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: { id: 'new-proposal-id', status: 'pending' } }),
    })
    vi.stubGlobal('fetch', mockFetch)

    renderWithPortfolio()
    const btn = screen.getByRole('button')
    fireEvent.click(btn)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/portfolio/propose',
        expect.objectContaining({ method: 'POST' }),
      )
    })

    await waitFor(() => {
      expect(screen.getByText(/proposed/i)).toBeInTheDocument()
    })
  })

  it('shows error message on API error response', async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      json: async () => ({ error_code: 'validation_error', message: 'Bad input' }),
    })
    vi.stubGlobal('fetch', mockFetch)

    renderWithPortfolio()
    const btn = screen.getByRole('button')
    fireEvent.click(btn)

    await waitFor(() => {
      expect(screen.getByText(/Bad input/i)).toBeInTheDocument()
    })
  })

  it('shows error message on network failure', async () => {
    const mockFetch = vi.fn().mockRejectedValueOnce(new Error('Network failure'))
    vi.stubGlobal('fetch', mockFetch)

    renderWithPortfolio()
    const btn = screen.getByRole('button')
    fireEvent.click(btn)

    await waitFor(() => {
      expect(screen.getByText(/Network failure/i)).toBeInTheDocument()
    })
  })

  it('disables button while request is in flight', async () => {
    let resolveFetch!: (v: unknown) => void
    const mockFetch = vi.fn().mockReturnValueOnce(
      new Promise((resolve) => { resolveFetch = resolve }),
    )
    vi.stubGlobal('fetch', mockFetch)

    renderWithPortfolio()
    const btn = screen.getByRole('button')
    fireEvent.click(btn)

    // While pending, button should be disabled
    expect(btn).toBeDisabled()

    resolveFetch({
      ok: true,
      json: async () => ({ data: { id: 'id', status: 'pending' } }),
    })
  })
})

// ---------------------------------------------------------------------------
// Tests: sectorGapApplied caveat
// ---------------------------------------------------------------------------

describe('ActButton — sector-gap caveat', () => {
  it('shows sector-gap caveat when sectorGapApplied is false', () => {
    renderWithPortfolio({ sectorGapApplied: false, suggestedPct: '4.0' })
    expect(screen.getByText(/sector-gap not yet applied/i)).toBeInTheDocument()
  })

  it('does not show sector-gap caveat when sectorGapApplied is true', () => {
    renderWithPortfolio({ sectorGapApplied: true, suggestedPct: '4.0' })
    expect(screen.queryByText(/sector-gap not yet applied/i)).not.toBeInTheDocument()
  })

  it('aria-label includes sector-gap caveat when sectorGapApplied is false', () => {
    renderWithPortfolio({
      sectorGapApplied: false,
      suggestedPct: '4.0',
      portfolioName: 'Banking Leaders',
    })
    const btn = screen.getByRole('button')
    expect(btn).toHaveAttribute(
      'aria-label',
      expect.stringContaining('sector-gap not yet applied'),
    )
  })

  it('aria-label does not mention sector-gap when sectorGapApplied is true', () => {
    renderWithPortfolio({
      sectorGapApplied: true,
      suggestedPct: '4.0',
      portfolioName: 'Banking Leaders',
    })
    const btn = screen.getByRole('button')
    expect(btn).not.toHaveAttribute(
      'aria-label',
      expect.stringContaining('sector-gap not yet applied'),
    )
  })
})
