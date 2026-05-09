// Tests for src/components/strategy/StateMultiSelect.tsx

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StateMultiSelect } from '@/components/strategy/StateMultiSelect'

const OPTIONS = ['Leader', 'Strong', 'Average', 'Weak'] as const

describe('StateMultiSelect', () => {
  it('renders all option chips', () => {
    render(
      <StateMultiSelect
        title="RS States"
        options={OPTIONS}
        selected={new Set()}
        onChange={() => {}}
      />,
    )
    for (const opt of OPTIONS) {
      expect(screen.getByText(opt)).toBeDefined()
    }
  })

  it('shows title label', () => {
    render(
      <StateMultiSelect
        title="Allowed states"
        options={OPTIONS}
        selected={new Set()}
        onChange={() => {}}
      />,
    )
    expect(screen.getByText(/Allowed states/i)).toBeDefined()
  })

  it('shows help text when provided', () => {
    render(
      <StateMultiSelect
        title="RS"
        options={OPTIONS}
        selected={new Set()}
        onChange={() => {}}
        help="Help text here"
      />,
    )
    expect(screen.getByText('Help text here')).toBeDefined()
  })

  it('selected chip has aria-pressed=true', () => {
    render(
      <StateMultiSelect
        title="RS"
        options={OPTIONS}
        selected={new Set(['Leader'])}
        onChange={() => {}}
      />,
    )
    const leaderBtn = screen.getByText('Leader').closest('button')
    expect(leaderBtn?.getAttribute('aria-pressed')).toBe('true')
  })

  it('unselected chip has aria-pressed=false', () => {
    render(
      <StateMultiSelect
        title="RS"
        options={OPTIONS}
        selected={new Set(['Leader'])}
        onChange={() => {}}
      />,
    )
    const weakBtn = screen.getByText('Weak').closest('button')
    expect(weakBtn?.getAttribute('aria-pressed')).toBe('false')
  })

  it('clicking unselected chip adds it to set', async () => {
    const onChange = vi.fn()
    render(
      <StateMultiSelect
        title="RS"
        options={OPTIONS}
        selected={new Set()}
        onChange={onChange}
      />,
    )
    await userEvent.click(screen.getByText('Leader'))
    expect(onChange).toHaveBeenCalledOnce()
    const nextSet: Set<string> = onChange.mock.calls[0][0]
    expect(nextSet.has('Leader')).toBe(true)
  })

  it('clicking selected chip removes it from set', async () => {
    const onChange = vi.fn()
    render(
      <StateMultiSelect
        title="RS"
        options={OPTIONS}
        selected={new Set(['Leader', 'Strong'])}
        onChange={onChange}
      />,
    )
    await userEvent.click(screen.getByText('Leader'))
    expect(onChange).toHaveBeenCalledOnce()
    const nextSet: Set<string> = onChange.mock.calls[0][0]
    expect(nextSet.has('Leader')).toBe(false)
    expect(nextSet.has('Strong')).toBe(true)
  })

  it('shows count of selected items', () => {
    render(
      <StateMultiSelect
        title="RS"
        options={OPTIONS}
        selected={new Set(['Leader', 'Strong'])}
        onChange={() => {}}
      />,
    )
    expect(screen.getByText('(2 selected)')).toBeDefined()
  })
})
