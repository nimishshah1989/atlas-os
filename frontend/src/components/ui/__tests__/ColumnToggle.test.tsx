import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderHook, act } from '@testing-library/react'

import { ColumnToggle, useColumnVisibility, type ColumnDef } from '@/components/ui/ColumnToggle'

const COLS: ColumnDef[] = [
  { key: 'ret_1w',    label: '1W Return',  defaultVisible: false },
  { key: 'ret_3m',    label: '3M Return',  defaultVisible: true },
  { key: 'rs_pctile', label: 'RS Pctile',  defaultVisible: true },
]

describe('ColumnToggle', () => {
  beforeEach(() => localStorage.clear())

  it('renders a Columns button', () => {
    const onChange = vi.fn()
    render(
      <ColumnToggle
        columns={COLS}
        visible={new Set(['ret_3m', 'rs_pctile'])}
        onChange={onChange}
      />
    )
    expect(screen.getByText('Columns')).toBeInTheDocument()
  })

  it('opens dropdown on click, showing column labels', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <ColumnToggle
        columns={COLS}
        visible={new Set(['ret_3m', 'rs_pctile'])}
        onChange={onChange}
      />
    )
    await user.click(screen.getByText('Columns'))
    expect(screen.getByText('1W Return')).toBeInTheDocument()
    expect(screen.getByText('3M Return')).toBeInTheDocument()
    expect(screen.getByText('RS Pctile')).toBeInTheDocument()
  })

  it('visible columns have checked checkboxes', async () => {
    const user = userEvent.setup()
    render(
      <ColumnToggle
        columns={COLS}
        visible={new Set(['ret_3m', 'rs_pctile'])}
        onChange={vi.fn()}
      />
    )
    await user.click(screen.getByText('Columns'))
    const checkboxes = screen.getAllByRole('checkbox')
    // COLS order: ret_1w (hidden), ret_3m (visible), rs_pctile (visible)
    expect(checkboxes[0]).not.toBeChecked()
    expect(checkboxes[1]).toBeChecked()
    expect(checkboxes[2]).toBeChecked()
  })

  it('toggling a checkbox calls onChange with updated Set', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <ColumnToggle
        columns={COLS}
        visible={new Set(['ret_3m', 'rs_pctile'])}
        onChange={onChange}
      />
    )
    await user.click(screen.getByText('Columns'))
    const checkboxes = screen.getAllByRole('checkbox')
    await user.click(checkboxes[0]) // toggle ret_1w on
    expect(onChange).toHaveBeenCalledOnce()
    const updated: Set<string> = onChange.mock.calls[0][0]
    expect(updated.has('ret_1w')).toBe(true)
    expect(updated.has('ret_3m')).toBe(true)
  })
})

describe('useColumnVisibility', () => {
  beforeEach(() => localStorage.clear())

  it('returns defaultVisible=true columns initially visible', () => {
    const { result } = renderHook(() =>
      useColumnVisibility('test-key', COLS)
    )
    const [visible] = result.current
    expect(visible.has('ret_3m')).toBe(true)
    expect(visible.has('rs_pctile')).toBe(true)
    expect(visible.has('ret_1w')).toBe(false)
  })

  it('all columns visible when defaultVisible not specified', () => {
    const cols: ColumnDef[] = [
      { key: 'a', label: 'A' },
      { key: 'b', label: 'B' },
    ]
    const { result } = renderHook(() =>
      useColumnVisibility('test-key-2', cols)
    )
    const [visible] = result.current
    expect(visible.has('a')).toBe(true)
    expect(visible.has('b')).toBe(true)
  })

  it('setVisible updates the set and persists to localStorage', () => {
    const { result } = renderHook(() =>
      useColumnVisibility('test-key-3', COLS)
    )
    act(() => {
      result.current[1](new Set(['ret_1w']))
    })
    const [visible] = result.current
    expect(visible.has('ret_1w')).toBe(true)
    const stored = JSON.parse(localStorage.getItem('test-key-3') ?? '[]')
    expect(stored).toContain('ret_1w')
  })
})
