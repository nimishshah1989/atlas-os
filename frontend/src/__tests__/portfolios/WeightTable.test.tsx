// Tests for src/components/portfolio/WeightTable.tsx
// Covers: equal-weight on init, sum indicator green at 100%,
//         normalize button behavior, remove button.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { WeightTable } from '@/components/portfolio/WeightTable'
import type { SelectedInstrument } from '@/components/portfolio/InstrumentPicker'

const SELECTED_TWO: SelectedInstrument[] = [
  { instrument_id: 'uuid-a', instrument_type: 'stock', display_name: 'HDFCBANK', meta: 'Large · Banks' },
  { instrument_id: 'uuid-b', instrument_type: 'etf', display_name: 'NIFTYBEES', meta: 'Broad' },
]

const SELECTED_THREE: SelectedInstrument[] = [
  ...SELECTED_TWO,
  { instrument_id: 'uuid-c', instrument_type: 'fund', display_name: 'Mirae Large Cap', meta: 'Equity · Large Cap' },
]

function renderTable(
  selected: SelectedInstrument[] = SELECTED_TWO,
  overrides: Partial<Parameters<typeof WeightTable>[0]> = {},
) {
  const onWeightsChange = vi.fn()
  const onRemove = vi.fn()
  render(
    <WeightTable
      selected={selected}
      onWeightsChange={onWeightsChange}
      onRemove={onRemove}
      {...overrides}
    />,
  )
  return { onWeightsChange, onRemove }
}

describe('WeightTable', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows empty state when no instruments are selected', () => {
    renderTable([])
    expect(screen.getByText(/No instruments selected/)).toBeInTheDocument()
  })

  it('initializes with equal weights summing to 100', () => {
    renderTable()
    // Two instruments: each should be 50.0000
    const inputs = screen.getAllByRole('spinbutton')
    expect(inputs).toHaveLength(2)
    const v1 = parseFloat((inputs[0] as HTMLInputElement).value)
    const v2 = parseFloat((inputs[1] as HTMLInputElement).value)
    expect(v1 + v2).toBeCloseTo(100, 1)
  })

  it('shows green sum indicator at exactly 100%', () => {
    renderTable()
    // Equal weights with 2 instruments = 100% (two 50s)
    expect(screen.getByText(/Sums to 100%/)).toBeInTheDocument()
  })

  it('shows amber indicator when weights do not sum to 100', async () => {
    renderTable()
    const inputs = screen.getAllByRole('spinbutton')
    // Change first to 30 (sum becomes 30 + 50 = 80)
    fireEvent.change(inputs[0], { target: { value: '30' } })
    await waitFor(() => {
      expect(screen.getByText(/allocated/)).toBeInTheDocument()
    })
  })

  it('normalize button redistributes weights to 100%', async () => {
    renderTable()
    const inputs = screen.getAllByRole('spinbutton')
    // Set weights to 30 + 50 = 80 (not normalized)
    fireEvent.change(inputs[0], { target: { value: '30' } })
    await waitFor(() => {
      expect(screen.getByText(/allocated/)).toBeInTheDocument()
    })
    fireEvent.click(screen.getByText('Auto-Normalize'))
    await waitFor(() => {
      expect(screen.getByText(/Sums to 100%/)).toBeInTheDocument()
    })
  })

  it('remove button calls onRemove with correct instrument_id', () => {
    const { onRemove } = renderTable()
    const removeButtons = screen.getAllByRole('button', { name: /Remove/ })
    fireEvent.click(removeButtons[0])
    expect(onRemove).toHaveBeenCalledWith('uuid-a')
  })

  it('renders all instrument types (stock, etf, fund)', () => {
    renderTable(SELECTED_THREE)
    expect(screen.getByText('HDFCBANK')).toBeInTheDocument()
    expect(screen.getByText('NIFTYBEES')).toBeInTheDocument()
    expect(screen.getByText('Mirae Large Cap')).toBeInTheDocument()
    // Three inputs for three instruments
    const inputs = screen.getAllByRole('spinbutton')
    expect(inputs).toHaveLength(3)
  })

  it('calls onWeightsChange when a weight is edited', async () => {
    const { onWeightsChange } = renderTable()
    const inputs = screen.getAllByRole('spinbutton')
    fireEvent.change(inputs[0], { target: { value: '60' } })
    await waitFor(() => {
      expect(onWeightsChange).toHaveBeenCalled()
    })
  })
})
