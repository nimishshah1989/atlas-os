// Tests for src/components/strategy/KPICard.tsx

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { KPICard } from '@/components/strategy/KPICard'

describe('KPICard', () => {
  it('renders label and value', () => {
    render(<KPICard label="Sharpe Ratio" value="1.42" />)
    expect(screen.getByText('Sharpe Ratio')).toBeTruthy()
    expect(screen.getByText('1.42')).toBeTruthy()
  })

  it('renders — when value is null', () => {
    render(<KPICard label="Max Drawdown" value={null} />)
    expect(screen.getByText('—')).toBeTruthy()
  })

  it('renders positive delta in green class', () => {
    const { container } = render(
      <KPICard label="Alpha" value="+2.3%" delta="+2.3% vs benchmark" deltaPositive={true} />
    )
    const delta = container.querySelector('.text-signal-pos')
    expect(delta).toBeTruthy()
    expect(delta?.textContent).toContain('+2.3% vs benchmark')
  })

  it('renders negative delta in red class', () => {
    const { container } = render(
      <KPICard label="Alpha" value="-1.2%" delta="-1.2% vs benchmark" deltaPositive={false} />
    )
    const delta = container.querySelector('.text-signal-neg')
    expect(delta).toBeTruthy()
  })

  it('renders loading skeleton when loading=true', () => {
    const { container } = render(<KPICard label="Sharpe" value={null} loading={true} />)
    const skeleton = container.querySelector('.animate-pulse')
    expect(skeleton).toBeTruthy()
    // Should not render actual label text while loading
    expect(screen.queryByText('Sharpe')).toBeNull()
  })

  it('renders no delta element when delta is not provided', () => {
    const { container } = render(<KPICard label="Return" value="12.5%" />)
    expect(container.querySelector('.text-signal-pos')).toBeNull()
    expect(container.querySelector('.text-signal-neg')).toBeNull()
  })
})
