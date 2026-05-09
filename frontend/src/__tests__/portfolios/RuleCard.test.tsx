// Tests for src/components/strategy/RuleCard.tsx

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RuleCard } from '@/components/strategy/RuleCard'

describe('RuleCard', () => {
  it('renders title and description', () => {
    render(
      <RuleCard title="RS State" description="Relative strength" enabled={false} onToggleEnabled={() => {}}>
        <span>body content</span>
      </RuleCard>,
    )
    expect(screen.getByText('RS State')).toBeDefined()
    expect(screen.getByText('Relative strength')).toBeDefined()
  })

  it('shows children body', () => {
    render(
      <RuleCard title="RS State" enabled={false} onToggleEnabled={() => {}}>
        <span data-testid="body">inner</span>
      </RuleCard>,
    )
    expect(screen.getByTestId('body')).toBeDefined()
  })

  it('body is dimmed when enabled=false', () => {
    const { container } = render(
      <RuleCard title="RS" enabled={false} onToggleEnabled={() => {}}>
        <span>inner</span>
      </RuleCard>,
    )
    // The body wrapper should have opacity-50 + pointer-events-none
    const body = container.querySelector('.opacity-50.pointer-events-none')
    expect(body).not.toBeNull()
  })

  it('body is not dimmed when enabled=true', () => {
    const { container } = render(
      <RuleCard title="RS" enabled={true} onToggleEnabled={() => {}}>
        <span>inner</span>
      </RuleCard>,
    )
    const dimmed = container.querySelector('.opacity-50.pointer-events-none')
    expect(dimmed).toBeNull()
  })

  it('toggle button calls onToggleEnabled', async () => {
    const onToggle = vi.fn()
    render(
      <RuleCard title="RS" enabled={false} onToggleEnabled={onToggle}>
        <span>inner</span>
      </RuleCard>,
    )
    const toggle = screen.getByRole('switch', { name: /Toggle RS/i })
    await userEvent.click(toggle)
    expect(onToggle).toHaveBeenCalledOnce()
  })

  it('toggle button has correct aria-checked when disabled', () => {
    render(
      <RuleCard title="RS" enabled={false} onToggleEnabled={() => {}}>
        <span>inner</span>
      </RuleCard>,
    )
    const toggle = screen.getByRole('switch')
    expect(toggle.getAttribute('aria-checked')).toBe('false')
  })

  it('toggle button has correct aria-checked when enabled', () => {
    render(
      <RuleCard title="RS" enabled={true} onToggleEnabled={() => {}}>
        <span>inner</span>
      </RuleCard>,
    )
    const toggle = screen.getByRole('switch')
    expect(toggle.getAttribute('aria-checked')).toBe('true')
  })
})
