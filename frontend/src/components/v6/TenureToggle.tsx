// frontend/src/components/v6/TenureToggle.tsx
//
// Segmented control for selecting return-window tenure: 1m / 3m / 6m / 12m.
// Design: design-application.md §3.1 — every chart / bubble / table top-right.
// Tokens: globals.css --color-paper, --color-ink-*, --color-accent, --color-teal
// Persistence: URL-param-primary + localStorage-seed via useTenurePreference.
// ARIA: role="radiogroup" wrapper, role="radio" pills, ←/→ keyboard nav.

'use client'

import { useRef, type KeyboardEvent } from 'react'
import { useTenurePreference, type TenureValue } from '@/lib/v6/persistence'

// ── Constants ─────────────────────────────────────────────────────────────────

const TENURES: readonly TenureValue[] = ['1m', '3m', '6m', '12m']

// ── Props ─────────────────────────────────────────────────────────────────────

interface TenureToggleProps {
  /**
   * Page-scoped key used to namespace localStorage.
   * Example: "sector-detail", "stocks-table", "fund-detail"
   */
  pageKey: string
  /** Optional external override — useful when parent lifts state. */
  value?: TenureValue
  /** Optional external setter — useful when parent lifts state. */
  onChange?: (value: TenureValue) => void
  className?: string
}

// ── Component ─────────────────────────────────────────────────────────────────

export function TenureToggle({ pageKey, value, onChange, className = '' }: TenureToggleProps) {
  const { tenure: internalTenure, setTenure: setInternalTenure } = useTenurePreference(pageKey)
  const pillRefs = useRef<(HTMLButtonElement | null)[]>([])

  // Controlled from outside when `value` prop provided; otherwise internal.
  const activeTenure: TenureValue = value ?? internalTenure

  function handleSelect(t: TenureValue): void {
    if (onChange) {
      onChange(t)
    } else {
      setInternalTenure(t)
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>): void {
    const idx = TENURES.indexOf(activeTenure)

    if (e.key === 'ArrowRight') {
      e.preventDefault()
      const next = (idx + 1) % TENURES.length
      handleSelect(TENURES[next])
      pillRefs.current[next]?.focus()
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      const prev = (idx - 1 + TENURES.length) % TENURES.length
      handleSelect(TENURES[prev])
      pillRefs.current[prev]?.focus()
    } else if (e.key === 'Home') {
      e.preventDefault()
      handleSelect(TENURES[0])
      pillRefs.current[0]?.focus()
    } else if (e.key === 'End') {
      e.preventDefault()
      const last = TENURES.length - 1
      handleSelect(TENURES[last])
      pillRefs.current[last]?.focus()
    }
  }

  return (
    <div
      role="radiogroup"
      aria-label="Return window"
      onKeyDown={handleKeyDown}
      className={`inline-flex border border-paper-rule rounded-[2px] overflow-hidden ${className}`}
    >
      {TENURES.map((t, i) => {
        const isActive = t === activeTenure
        return (
          <button
            key={t}
            ref={(el) => { pillRefs.current[i] = el }}
            type="button"
            role="radio"
            aria-checked={isActive}
            // Only the active pill participates in tab order;
            // arrow keys navigate within the group.
            tabIndex={isActive ? 0 : -1}
            onClick={() => handleSelect(t)}
            className={[
              'px-3 py-1 text-[11px] font-mono font-medium tabular-nums leading-none',
              'border-r border-paper-rule last:border-r-0',
              'focus:outline-none focus-visible:ring-1 focus-visible:ring-teal focus-visible:ring-inset',
              'transition-colors',
              isActive
                ? 'bg-accent text-paper cursor-default'
                : 'bg-paper text-ink-secondary hover:bg-paper-rule/30 cursor-pointer',
            ].join(' ')}
          >
            {t}
          </button>
        )
      })}
    </div>
  )
}

// Re-export TenureValue so consumers don't need to import from persistence.
export type { TenureValue }
