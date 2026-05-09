// Tests for ReRunBacktestButton component.
// Covers: button renders, clicking opens modal, modal closes on cancel.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

// Mock the modal and server actions so we test only button behavior.
vi.mock('@/components/strategy/ReRunBacktestModal', () => ({
  ReRunBacktestModal: ({ onClose, strategyName }: { onClose: () => void; strategyName: string }) => (
    <div role="dialog" data-testid="mock-modal">
      <span>Modal for {strategyName}</span>
      <button type="button" onClick={onClose}>Cancel</button>
    </div>
  ),
}))

import { ReRunBacktestButton } from '@/components/strategy/ReRunBacktestButton'

const STRATEGY_ID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
const STRATEGY_NAME = 'Sector Rotation v2'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ReRunBacktestButton', () => {
  it('renders a button with correct label', () => {
    render(<ReRunBacktestButton strategyId={STRATEGY_ID} strategyName={STRATEGY_NAME} />)
    expect(screen.getByRole('button', { name: /Re-run Backtest/i })).toBeInTheDocument()
  })

  it('clicking the button opens the modal', async () => {
    render(<ReRunBacktestButton strategyId={STRATEGY_ID} strategyName={STRATEGY_NAME} />)
    expect(screen.queryByTestId('mock-modal')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Re-run Backtest/i }))

    await waitFor(() => {
      expect(screen.getByTestId('mock-modal')).toBeInTheDocument()
      expect(screen.getByText(`Modal for ${STRATEGY_NAME}`)).toBeInTheDocument()
    })
  })

  it('modal closes when cancel is clicked', async () => {
    render(<ReRunBacktestButton strategyId={STRATEGY_ID} strategyName={STRATEGY_NAME} />)
    fireEvent.click(screen.getByRole('button', { name: /Re-run Backtest/i }))

    await waitFor(() => expect(screen.getByTestId('mock-modal')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /Cancel/i }))

    await waitFor(() => {
      expect(screen.queryByTestId('mock-modal')).not.toBeInTheDocument()
    })
  })

  it('disabled prop disables the button', () => {
    render(<ReRunBacktestButton strategyId={STRATEGY_ID} strategyName={STRATEGY_NAME} disabled />)
    expect(screen.getByRole('button', { name: /Re-run Backtest/i })).toBeDisabled()
  })

  it('disabled button does not open modal when clicked', async () => {
    render(<ReRunBacktestButton strategyId={STRATEGY_ID} strategyName={STRATEGY_NAME} disabled />)
    fireEvent.click(screen.getByRole('button', { name: /Re-run Backtest/i }))
    expect(screen.queryByTestId('mock-modal')).not.toBeInTheDocument()
  })
})
