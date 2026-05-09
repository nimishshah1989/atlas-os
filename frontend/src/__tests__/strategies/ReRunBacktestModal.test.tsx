// Tests for ReRunBacktestModal component.
// Covers: renders with defaults, end-before-start inline error, capital below min inline error,
//         submit calls server action with correct payload, ESC closes, cancel closes.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock server actions — must be hoisted before importing the component.
vi.mock('@/app/strategies/[id]/actions', () => ({
  rerunBacktest: vi.fn(),
  getBacktestRunStatus: vi.fn(),
}))

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}))

import { rerunBacktest } from '@/app/strategies/[id]/actions'
import { ReRunBacktestModal } from '@/components/strategy/ReRunBacktestModal'

const STRATEGY_ID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
const STRATEGY_NAME = 'Momentum Blend v3'
const mockClose = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
})

function renderModal() {
  return render(
    <ReRunBacktestModal
      strategyId={STRATEGY_ID}
      strategyName={STRATEGY_NAME}
      onClose={mockClose}
    />,
  )
}

describe('ReRunBacktestModal', () => {
  it('renders with correct title, strategy name, and default inputs', () => {
    renderModal()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Re-run Backtest/i })).toBeInTheDocument()
    expect(screen.getByText(STRATEGY_NAME)).toBeInTheDocument()
    expect(screen.getByLabelText(/Start Date/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/End Date/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Initial Capital/i)).toBeInTheDocument()
    // Default capital is 1,000,000
    expect(screen.getByLabelText(/Initial Capital/i)).toHaveValue(1_000_000)
  })

  it('shows inline error when end date is before start date on submit', async () => {
    renderModal()
    const startInput = screen.getByLabelText(/Start Date/i)
    const endInput = screen.getByLabelText(/End Date/i)

    fireEvent.change(startInput, { target: { value: '2024-01-01' } })
    fireEvent.change(endInput, { target: { value: '2023-01-01' } })

    fireEvent.submit(startInput.closest('form')!)

    await waitFor(() => {
      expect(screen.getByText('End date must be after start date')).toBeInTheDocument()
    })
    expect(rerunBacktest).not.toHaveBeenCalled()
  })

  it('shows inline error when capital is below minimum', async () => {
    renderModal()
    const capitalInput = screen.getByLabelText(/Initial Capital/i)
    fireEvent.change(capitalInput, { target: { value: '50000' } })

    fireEvent.submit(capitalInput.closest('form')!)

    await waitFor(() => {
      expect(screen.getByText(/Capital must be ≥/i)).toBeInTheDocument()
    })
    expect(rerunBacktest).not.toHaveBeenCalled()
  })

  it('calls rerunBacktest with correct payload on valid submit', async () => {
    vi.mocked(rerunBacktest).mockResolvedValueOnce({
      ok: true,
      compute_run_id: 'run-xyz-456',
    })

    renderModal()
    const startInput = screen.getByLabelText(/Start Date/i)
    const endInput = screen.getByLabelText(/End Date/i)
    const capitalInput = screen.getByLabelText(/Initial Capital/i)

    fireEvent.change(startInput, { target: { value: '2022-01-01' } })
    fireEvent.change(endInput, { target: { value: '2024-12-31' } })
    fireEvent.change(capitalInput, { target: { value: '5000000' } })

    fireEvent.submit(startInput.closest('form')!)

    await waitFor(() => {
      expect(rerunBacktest).toHaveBeenCalledWith(
        STRATEGY_ID,
        '2022-01-01',
        '2024-12-31',
        5_000_000,
      )
    })
  })

  it('shows top error banner on 409 conflict without closing modal', async () => {
    vi.mocked(rerunBacktest).mockResolvedValueOnce({
      ok: false,
      error: 'A backtest is already in progress',
      error_code: 'already_running',
      existing_run_id: 'existing-run-aabbcc',
    })

    renderModal()
    const form = screen.getByLabelText(/Start Date/i).closest('form')!

    // Ensure dates are valid
    fireEvent.change(screen.getByLabelText(/Start Date/i), { target: { value: '2022-01-01' } })
    fireEvent.change(screen.getByLabelText(/End Date/i), { target: { value: '2024-12-31' } })
    fireEvent.submit(form)

    await waitFor(() => {
      expect(screen.getByText(/already running/i)).toBeInTheDocument()
    })
    // Modal stays open
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(mockClose).not.toHaveBeenCalled()
  })

  it('closes on ESC key press', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.keyboard('{Escape}')
    expect(mockClose).toHaveBeenCalledTimes(1)
  })

  it('closes on Cancel button click', async () => {
    renderModal()
    fireEvent.click(screen.getByRole('button', { name: /Cancel/i }))
    expect(mockClose).toHaveBeenCalledTimes(1)
  })

  it('closes on overlay click (click-outside)', async () => {
    renderModal()
    const overlay = screen.getByRole('dialog').parentElement!
    fireEvent.click(overlay)
    expect(mockClose).toHaveBeenCalledTimes(1)
  })

  it('has correct ARIA attributes', () => {
    renderModal()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAttribute('aria-labelledby', 'rerun-backtest-title')
  })
})
