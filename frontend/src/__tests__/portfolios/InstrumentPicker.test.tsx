// Tests for src/components/portfolio/InstrumentPicker.tsx
// Covers: renders tabs, filter narrows list, selecting calls onSelect.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { InstrumentPicker, type SelectedInstrument } from '@/components/portfolio/InstrumentPicker'
import type { StockPickerRow, ETFPickerRow, FundPickerRow } from '@/lib/queries/instruments'

const STOCKS: StockPickerRow[] = [
  { instrument_id: 'uuid-hdfc', symbol: 'HDFCBANK', company_name: 'HDFC Bank', tier: 'Large', sector: 'Banks', rs_state: 'Leader', effective_to: null },
  { instrument_id: 'uuid-infosys', symbol: 'INFY', company_name: 'Infosys', tier: 'Large', sector: 'IT', rs_state: 'Strong', effective_to: null },
  { instrument_id: 'uuid-smallco', symbol: 'SMALLCO', company_name: 'Small Co', tier: 'Small', sector: 'Chemicals', rs_state: null, effective_to: null },
]

const ETFS: ETFPickerRow[] = [
  { ticker: 'NIFTYBEES', etf_name: 'Nippon Nifty BeES', fund_house: 'Nippon', theme: 'Broad', linked_sector: null, asset_class: 'Equity', effective_to: null },
  { ticker: 'BANKBEES', etf_name: 'Nippon Bank BeES', fund_house: 'Nippon', theme: 'Sectoral', linked_sector: 'Banks', asset_class: 'Equity', effective_to: null },
]

const FUNDS: FundPickerRow[] = [
  { mstar_id: 'F0001', scheme_name: 'Mirae Large Cap Growth', amc: 'Mirae', broad_category: 'Equity', category_name: 'Large Cap', effective_to: null },
  { mstar_id: 'F0002', scheme_name: 'HDFC Mid Cap', amc: 'HDFC AMC', broad_category: 'Equity', category_name: 'Mid Cap', effective_to: null },
]

function renderPicker(
  overrides: Partial<Parameters<typeof InstrumentPicker>[0]> = {},
) {
  const onSelect = vi.fn()
  const props = {
    stocks: STOCKS,
    etfs: ETFS,
    funds: FUNDS,
    selectedIds: new Set<string>(),
    onSelect,
    ...overrides,
  }
  const { rerender } = render(<InstrumentPicker {...props} />)
  return { onSelect, rerender, props }
}

describe('InstrumentPicker', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders all three tabs', () => {
    renderPicker()
    expect(screen.getByText(/Stocks \(\d+\)/)).toBeInTheDocument()
    expect(screen.getByText(/ETFs \(\d+\)/)).toBeInTheDocument()
    expect(screen.getByText(/Mutual Funds \(\d+\)/)).toBeInTheDocument()
  })

  it('defaults to Stocks tab and shows stock rows', () => {
    renderPicker()
    expect(screen.getByText('HDFCBANK')).toBeInTheDocument()
    expect(screen.getByText('INFY')).toBeInTheDocument()
  })

  it('switches to ETFs tab and shows ETF rows', () => {
    renderPicker()
    fireEvent.click(screen.getByText(/ETFs \(\d+\)/))
    expect(screen.getByText('NIFTYBEES')).toBeInTheDocument()
    expect(screen.getByText('BANKBEES')).toBeInTheDocument()
  })

  it('switches to Mutual Funds tab and shows fund rows', () => {
    renderPicker()
    fireEvent.click(screen.getByText(/Mutual Funds \(\d+\)/))
    expect(screen.getByText('Mirae Large Cap Growth')).toBeInTheDocument()
    expect(screen.getByText('HDFC Mid Cap')).toBeInTheDocument()
  })

  it('search filter narrows stock list', () => {
    renderPicker()
    const searchInput = screen.getByPlaceholderText(/search stocks/i)
    fireEvent.change(searchInput, { target: { value: 'HDFC' } })
    expect(screen.getByText('HDFCBANK')).toBeInTheDocument()
    expect(screen.queryByText('INFY')).not.toBeInTheDocument()
  })

  it('search with no matches shows empty state', () => {
    renderPicker()
    const searchInput = screen.getByPlaceholderText(/search stocks/i)
    fireEvent.change(searchInput, { target: { value: 'XXXXXXXXXX' } })
    expect(screen.getByText(/No matches/)).toBeInTheDocument()
  })

  it('clicking a row calls onSelect with correct shape', () => {
    const { onSelect } = renderPicker()
    fireEvent.click(screen.getByText('HDFCBANK').closest('tr')!)
    expect(onSelect).toHaveBeenCalledTimes(1)
    const arg: SelectedInstrument = onSelect.mock.calls[0][0]
    expect(arg.instrument_id).toBe('uuid-hdfc')
    expect(arg.instrument_type).toBe('stock')
    expect(arg.display_name).toBe('HDFCBANK')
  })

  it('already-selected row is muted and does not call onSelect on click', () => {
    const { onSelect } = renderPicker({ selectedIds: new Set(['uuid-hdfc']) })
    const hdfcRow = screen.getByText('HDFCBANK').closest('tr')!
    expect(hdfcRow.className).toContain('opacity-40')
    fireEvent.click(hdfcRow)
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('tier filter chip narrows list to matching tier', () => {
    renderPicker()
    // Click "Small" filter chip
    const smallChip = screen.getByRole('button', { name: 'Small' })
    fireEvent.click(smallChip)
    expect(screen.getByText('SMALLCO')).toBeInTheDocument()
    expect(screen.queryByText('HDFCBANK')).not.toBeInTheDocument()
  })

  it('clicking active filter chip toggles it off (deselects)', () => {
    renderPicker()
    const largeChip = screen.getByRole('button', { name: 'Large' })
    fireEvent.click(largeChip) // activate
    fireEvent.click(largeChip) // deactivate
    // All stocks should be visible again
    expect(screen.getByText('HDFCBANK')).toBeInTheDocument()
    expect(screen.getByText('SMALLCO')).toBeInTheDocument()
  })
})
