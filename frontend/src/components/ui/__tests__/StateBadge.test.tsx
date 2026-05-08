import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { StateBadge } from '../StateBadge'

describe('StateBadge', () => {
  it('renders the state label', () => {
    render(<StateBadge state="Risk-On" />)
    expect(screen.getByText('Risk-On')).toBeInTheDocument()
  })

  it('applies forest color for positive states', () => {
    const { container } = render(<StateBadge state="Risk-On" />)
    expect(container.firstChild).toHaveClass('text-signal-pos')
  })

  it('applies terracotta color for negative states', () => {
    const { container } = render(<StateBadge state="Risk-Off" />)
    expect(container.firstChild).toHaveClass('text-signal-neg')
  })

  it('applies ochre for warning states', () => {
    const { container } = render(<StateBadge state="Cautious" />)
    expect(container.firstChild).toHaveClass('text-signal-warn')
  })
})
