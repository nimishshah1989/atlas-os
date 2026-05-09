// Tests for src/components/strategy/BreadthGateSlider.tsx

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BreadthGateSlider } from '@/components/strategy/BreadthGateSlider'
import type { BreadthGate } from '@/lib/rule-catalogs'

const PCT_GATE: BreadthGate = {
  key: 'pct_above_ema_50',
  label: 'Stocks above EMA-50',
  min: 0,
  max: 100,
  step: 1,
  fmt: 'pct',
  help: 'Percentage of universe trading above their 50-day EMA',
}

const RATIO_GATE: BreadthGate = {
  key: 'ad_ratio',
  label: 'Advance / Decline ratio',
  min: 0,
  max: 3,
  step: 0.05,
  fmt: 'ratio',
  help: 'Ratio of advancing to declining stocks (latest day)',
}

const FRAC_GATE: BreadthGate = {
  key: 'pct_in_strong_states',
  label: 'Pct in Leader/Strong states',
  min: 0,
  max: 1,
  step: 0.01,
  fmt: 'frac',
  help: 'Fraction of universe in Leader or Strong RS state',
}

describe('BreadthGateSlider — null = off', () => {
  it('renders gate label', () => {
    render(<BreadthGateSlider gate={PCT_GATE} value={null} onChange={() => {}} />)
    expect(screen.getByText('Stocks above EMA-50')).toBeDefined()
  })

  it('does not render slider input when value is null', () => {
    render(<BreadthGateSlider gate={PCT_GATE} value={null} onChange={() => {}} />)
    expect(screen.queryByRole('slider')).toBeNull()
  })

  it('toggle switch has aria-checked=false when value is null', () => {
    render(<BreadthGateSlider gate={PCT_GATE} value={null} onChange={() => {}} />)
    const toggle = screen.getByRole('switch')
    expect(toggle.getAttribute('aria-checked')).toBe('false')
  })

  it('clicking toggle calls onChange with a number (midpoint) when was null', async () => {
    const onChange = vi.fn()
    render(<BreadthGateSlider gate={PCT_GATE} value={null} onChange={onChange} />)
    await userEvent.click(screen.getByRole('switch'))
    expect(onChange).toHaveBeenCalledOnce()
    expect(typeof onChange.mock.calls[0][0]).toBe('number')
  })
})

describe('BreadthGateSlider — value set = visible', () => {
  it('renders slider input when value is set', () => {
    render(<BreadthGateSlider gate={PCT_GATE} value={60} onChange={() => {}} />)
    expect(screen.getByRole('slider')).toBeDefined()
  })

  it('toggle switch has aria-checked=true when value is set', () => {
    render(<BreadthGateSlider gate={PCT_GATE} value={60} onChange={() => {}} />)
    const toggle = screen.getByRole('switch')
    expect(toggle.getAttribute('aria-checked')).toBe('true')
  })

  it('clicking toggle calls onChange with null when was set', async () => {
    const onChange = vi.fn()
    render(<BreadthGateSlider gate={PCT_GATE} value={60} onChange={onChange} />)
    await userEvent.click(screen.getByRole('switch'))
    expect(onChange).toHaveBeenCalledWith(null)
  })
})

describe('BreadthGateSlider — format by fmt', () => {
  it('formats pct gate as percentage', () => {
    render(<BreadthGateSlider gate={PCT_GATE} value={60} onChange={() => {}} />)
    const display = screen.getByTestId('gate-value-pct_above_ema_50')
    expect(display.textContent).toContain('60%')
  })

  it('formats ratio gate with 2 decimals', () => {
    render(<BreadthGateSlider gate={RATIO_GATE} value={1.2} onChange={() => {}} />)
    const display = screen.getByTestId('gate-value-ad_ratio')
    expect(display.textContent).toContain('1.20')
  })

  it('formats frac gate with 2 decimals', () => {
    render(<BreadthGateSlider gate={FRAC_GATE} value={0.6} onChange={() => {}} />)
    const display = screen.getByTestId('gate-value-pct_in_strong_states')
    expect(display.textContent).toContain('0.60')
  })

  it('shows help text', () => {
    render(<BreadthGateSlider gate={PCT_GATE} value={null} onChange={() => {}} />)
    expect(screen.getByText('Percentage of universe trading above their 50-day EMA')).toBeDefined()
  })
})
