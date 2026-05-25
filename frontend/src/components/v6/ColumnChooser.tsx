// frontend/src/components/v6/ColumnChooser.tsx
//
// Per-table column visibility manager for v6 data tables.
// Trigger: Settings gear icon. Modal: grouped checkboxes in 5 categories.
// Closes on: outside-click, Esc key.
// No Radix Dialog available — uses createPortal + manual focus trap.
// Tokens: DESIGN.md paper/ink only.

'use client'

import {
  useRef,
  useEffect,
  useCallback,
  type KeyboardEvent,
} from 'react'
import { createPortal } from 'react-dom'

// ── Types ────────────────────────────────────────────────────────────────────

export type ColumnGroup =
  | 'returns'
  | 'risk'
  | 'technicals'
  | 'atlas'
  | 'benchmarks'

export type ColumnDef<T extends string = string> = {
  key: T
  label: string
  group: ColumnGroup
}

type Props<T extends string = string> = {
  columns: ColumnDef<T>[]
  visible: T[]
  defaults: T[]
  onVisibleChange: (cols: T[]) => void
  onReset: () => void
  open: boolean
  onOpenChange: (open: boolean) => void
}

// ── Group metadata ────────────────────────────────────────────────────────────

const GROUP_LABELS: Record<ColumnGroup, string> = {
  returns: 'Returns',
  risk: 'Risk',
  technicals: 'Technicals',
  atlas: 'Atlas signals',
  benchmarks: 'Benchmarks',
}

const GROUP_ORDER: ColumnGroup[] = [
  'returns',
  'risk',
  'technicals',
  'atlas',
  'benchmarks',
]

// ── Settings icon (gear) ─────────────────────────────────────────────────────

function GearIcon() {
  return (
    <svg
      aria-hidden="true"
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="7" cy="7" r="2" />
      <path d="M7 1v1.5M7 11.5V13M1 7h1.5M11.5 7H13M2.929 2.929l1.06 1.06M9.01 9.01l1.06 1.06M2.929 11.071l1.06-1.06M9.01 4.99l1.06-1.06" />
    </svg>
  )
}

// ── Modal ─────────────────────────────────────────────────────────────────────

function Modal<T extends string>({
  columns,
  visible,
  defaults,
  onVisibleChange,
  onReset,
  onClose,
}: Omit<Props<T>, 'open' | 'onOpenChange'> & { onClose: () => void }) {
  const modalRef = useRef<HTMLDivElement>(null)
  const firstFocusableRef = useRef<HTMLButtonElement>(null)

  // Focus modal on open; return focus to trigger on close is handled by caller.
  useEffect(() => {
    firstFocusableRef.current?.focus()
  }, [])

  // Esc closes the modal.
  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    },
    [onClose],
  )

  // Outside-click closes the modal (mousedown not click, to avoid event
  // propagation quirks when clicking portal content).
  useEffect(() => {
    function handleMouseDown(e: MouseEvent) {
      if (modalRef.current && !modalRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handleMouseDown)
    return () => document.removeEventListener('mousedown', handleMouseDown)
  }, [onClose])

  const visibleSet = new Set(visible)

  function toggleColumn(key: T) {
    const next = visibleSet.has(key)
      ? visible.filter(k => k !== key)
      : [...visible, key]
    onVisibleChange(next as T[])
  }

  // Group columns by their group key, preserving GROUP_ORDER.
  const grouped = GROUP_ORDER.reduce<Record<ColumnGroup, ColumnDef<T>[]>>(
    (acc, g) => {
      acc[g] = columns.filter(c => c.group === g)
      return acc
    },
    {} as Record<ColumnGroup, ColumnDef<T>[]>,
  )

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Column chooser"
      className="fixed inset-0 z-50 flex items-start justify-end pt-12 pr-4"
      onKeyDown={handleKeyDown}
    >
      {/* Backdrop — transparent so outside-click fires on the mousedown handler */}
      <div className="absolute inset-0" aria-hidden="true" />

      <div
        ref={modalRef}
        className="relative z-10 w-72 rounded border border-[#C2B8A8] bg-[#F8F4EC] shadow-lg"
        style={{ maxHeight: 'calc(100vh - 5rem)', overflowY: 'auto' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#C2B8A8] px-4 py-3">
          <span className="text-xs font-semibold uppercase tracking-[0.14em] text-[#1A1714]">
            Columns
          </span>
          <div className="flex items-center gap-2">
            <button
              ref={firstFocusableRef}
              onClick={onReset}
              className="text-xs text-[#6B6157] underline underline-offset-2 hover:text-[#1A1714] transition-colors"
            >
              Reset to default
            </button>
            <button
              onClick={onClose}
              aria-label="Close column chooser"
              className="ml-1 rounded p-0.5 text-[#9A8F82] hover:text-[#1A1714] transition-colors"
            >
              <svg
                aria-hidden="true"
                width="12"
                height="12"
                viewBox="0 0 12 12"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              >
                <path d="M1 1l10 10M11 1L1 11" />
              </svg>
            </button>
          </div>
        </div>

        {/* Groups */}
        <div className="px-3 py-2 space-y-3">
          {GROUP_ORDER.map(group => {
            const cols = grouped[group]
            if (cols.length === 0) return null
            return (
              <section key={group} aria-labelledby={`colgroup-${group}`}>
                <p
                  id={`colgroup-${group}`}
                  className="mb-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-[#9A8F82]"
                >
                  {GROUP_LABELS[group]}
                </p>
                <ul role="list" className="space-y-0.5">
                  {cols.map(col => {
                    const checked = visibleSet.has(col.key)
                    return (
                      <li key={col.key}>
                        <label className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-xs text-[#3D362E] hover:bg-[#F1ECDF] transition-colors">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleColumn(col.key)}
                            className="h-3 w-3 accent-[#2F6B43] rounded-sm"
                            aria-label={`Toggle ${col.label}`}
                          />
                          {col.label}
                        </label>
                      </li>
                    )
                  })}
                </ul>
              </section>
            )
          })}
        </div>
      </div>
    </div>,
    document.body,
  )
}

// ── ColumnChooser (trigger + modal) ──────────────────────────────────────────

export function ColumnChooser<T extends string = string>({
  columns,
  visible,
  defaults,
  onVisibleChange,
  onReset,
  open,
  onOpenChange,
}: Props<T>) {
  const triggerRef = useRef<HTMLButtonElement>(null)

  function handleClose() {
    onOpenChange(false)
    // Return focus to trigger after modal closes.
    setTimeout(() => triggerRef.current?.focus(), 0)
  }

  return (
    <>
      <button
        ref={triggerRef}
        onClick={() => onOpenChange(!open)}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label="Open column chooser"
        className="flex items-center gap-1 rounded border border-[#C2B8A8] px-2 py-1 text-xs text-[#6B6157] transition-colors hover:bg-[#F1ECDF] hover:text-[#1A1714]"
      >
        <GearIcon />
        Columns
      </button>

      {open && (
        <Modal
          columns={columns}
          visible={visible}
          defaults={defaults}
          onVisibleChange={onVisibleChange}
          onReset={onReset}
          onClose={handleClose}
        />
      )}
    </>
  )
}
