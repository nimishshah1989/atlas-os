// frontend/src/components/v6/__tests__/ColumnChooser.test.tsx
//
// 6 test cases covering all A.3 acceptance criteria:
//   1. Per-page key isolation — two pageKeys don't share LS state
//   2. Reset restores defaults
//   3. Persists to localStorage on toggle
//   4. Modal opens on settings-icon / trigger click
//   5. Modal closes on Esc keydown
//   6. Modal closes on outside-click; aria-modal + role="dialog" a11y

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import {
  render,
  screen,
  fireEvent,
  act,
  waitFor,
} from '@testing-library/react'
import { renderHook } from '@testing-library/react'
import { ColumnChooser, type ColumnDef } from '../ColumnChooser'
import { useColumnPreferences } from '@/lib/v6/useColumnPreferences'

// ── Fixtures ─────────────────────────────────────────────────────────────────

const COLUMNS: ColumnDef<string>[] = [
  { key: '1m_return', label: '1m return', group: 'returns' },
  { key: '6m_return', label: '6m return', group: 'returns' },
  { key: 'sigma_60d', label: '60d vol', group: 'risk' },
  { key: 'rsi', label: 'RSI', group: 'technicals' },
  { key: 'ic', label: 'IC', group: 'atlas' },
  { key: 'vs_nifty500', label: 'vs Nifty 500', group: 'benchmarks' },
]

const DEFAULTS = ['1m_return', '6m_return']

// ── LS mock ──────────────────────────────────────────────────────────────────

let lsStore: Record<string, string> = {}

beforeEach(() => {
  lsStore = {}
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(
    (key: string) => lsStore[key] ?? null,
  )
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(
    (key: string, value: string) => { lsStore[key] = value },
  )
  vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(
    (key: string) => { delete lsStore[key] },
  )
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderChooser(
  visible: string[],
  open = false,
  onVisibleChange = vi.fn(),
  onReset = vi.fn(),
  onOpenChange = vi.fn(),
) {
  return render(
    <ColumnChooser
      columns={COLUMNS}
      visible={visible}
      defaults={DEFAULTS}
      onVisibleChange={onVisibleChange}
      onReset={onReset}
      open={open}
      onOpenChange={onOpenChange}
    />,
  )
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ColumnChooser + useColumnPreferences', () => {
  // 1. Per-page key isolation
  it('per-page LS keys are namespaced and do not leak across pages', () => {
    const { result: hookA } = renderHook(() =>
      useColumnPreferences<string>('stocks', ['col_a']),
    )
    const { result: hookB } = renderHook(() =>
      useColumnPreferences<string>('etfs', ['col_b']),
    )

    act(() => {
      hookA.current.setVisible(['col_a', 'col_c'])
    })

    // Page B should still have its own defaults — not influenced by A's write.
    expect(hookB.current.visible).toEqual(['col_b'])

    // LS keys are different
    expect(lsStore['v6.columns.stocks']).toBe(JSON.stringify(['col_a', 'col_c']))
    expect(lsStore['v6.columns.etfs']).toBeUndefined()
  })

  // 2. Reset restores defaults and clears LS
  it('reset restores the defaults prop and removes the LS entry', () => {
    const { result } = renderHook(() =>
      useColumnPreferences('stocks', DEFAULTS),
    )

    act(() => {
      result.current.setVisible(['1m_return', '6m_return', 'rsi'])
    })
    expect(lsStore['v6.columns.stocks']).toBeTruthy()

    act(() => {
      result.current.reset()
    })

    expect(result.current.visible).toEqual(DEFAULTS)
    expect(lsStore['v6.columns.stocks']).toBeUndefined()
  })

  // 3. Persists to localStorage on setVisible
  it('setVisible persists the new column list to localStorage', () => {
    const { result } = renderHook(() =>
      useColumnPreferences<string>('funds', ['col_x']),
    )

    act(() => {
      result.current.setVisible(['col_x', 'col_y'])
    })

    expect(lsStore['v6.columns.funds']).toBe(
      JSON.stringify(['col_x', 'col_y']),
    )
    expect(result.current.visible).toEqual(['col_x', 'col_y'])
  })

  // 4. Modal opens on trigger click
  it('modal opens when the settings trigger button is clicked', async () => {
    const onOpenChange = vi.fn()
    renderChooser(DEFAULTS, false, vi.fn(), vi.fn(), onOpenChange)

    const trigger = screen.getByRole('button', { name: /open column chooser/i })
    fireEvent.click(trigger)

    expect(onOpenChange).toHaveBeenCalledWith(true)
  })

  // 5. Modal closes on Esc keydown
  it('modal closes when Esc is pressed inside the dialog', async () => {
    const onOpenChange = vi.fn()
    renderChooser(DEFAULTS, true, vi.fn(), vi.fn(), onOpenChange)

    await waitFor(() =>
      expect(screen.getByRole('dialog')).toBeInTheDocument(),
    )

    const dialog = screen.getByRole('dialog')
    fireEvent.keyDown(dialog, { key: 'Escape', code: 'Escape' })

    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  // 6. a11y: role=dialog + aria-modal; outside-click fires onOpenChange(false)
  it('dialog has correct a11y attributes and closes on outside-click', async () => {
    const onOpenChange = vi.fn()
    const { container } = renderChooser(
      DEFAULTS,
      true,
      vi.fn(),
      vi.fn(),
      onOpenChange,
    )

    await waitFor(() =>
      expect(screen.getByRole('dialog')).toBeInTheDocument(),
    )

    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAttribute('aria-label', 'Column chooser')

    // Outside-click: fire mousedown on the document body (outside modal content)
    fireEvent.mouseDown(container.ownerDocument.body)

    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
