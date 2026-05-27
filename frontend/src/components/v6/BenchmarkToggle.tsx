// frontend/src/components/v6/BenchmarkToggle.tsx
//
// Segmented control for selecting benchmark: Nifty 50 / Nifty 500 / Gold.
// Design: design-application.md §3.2 — every RS-flavored view top-right.
// Tokens: globals.css --color-paper, --color-ink-*, --color-accent, --color-teal
// Persistence: URL-param-primary + localStorage-seed via useBenchmarkPreference.
// ARIA: role="radiogroup" wrapper, role="radio" pills, ←/→/Home/End keyboard nav.
//
// goldAvailable MUST be resolved server-side (isGoldAvailable()) and passed
// as a prop — do NOT call the query from inside this client component.

'use client'

import { useRef, type KeyboardEvent } from 'react'
import { useBenchmarkPreference, type BenchmarkValue } from '@/lib/v6/persistence'

// ── Pill definitions ──────────────────────────────────────────────────────────

type PillDef = { value: BenchmarkValue; label: string }

const ALL_PILLS: readonly PillDef[] = [
  { value: 'nifty50', label: 'Nifty 50' },
  { value: 'nifty500', label: 'Nifty 500' },
  { value: 'gold', label: 'Gold' },
]

const DEFAULT_BENCHMARK: BenchmarkValue = 'nifty500'

// ── Props ─────────────────────────────────────────────────────────────────────

interface BenchmarkToggleProps {
  /**
   * Page-scoped key used to namespace localStorage.
   * Example: "stock-detail", "sector-detail", "today"
   */
  pageKey: string
  /**
   * Pass the result of isGoldAvailable() from the server parent.
   * When false, the Gold pill is hidden and any gold URL/LS value falls
   * back to the default nifty500.
   */
  goldAvailable: boolean
  /** Optional external override — useful when parent lifts state. */
  value?: BenchmarkValue
  /** Optional external setter — useful when parent lifts state. */
  onChange?: (value: BenchmarkValue) => void
  className?: string
}

// ── Component ─────────────────────────────────────────────────────────────────

export function BenchmarkToggle({
  pageKey,
  goldAvailable,
  value,
  onChange,
  className = '',
}: BenchmarkToggleProps) {
  const { benchmark: internalBenchmark, setBenchmark: setInternalBenchmark } =
    useBenchmarkPreference(pageKey)
  const pillRefs = useRef<(HTMLButtonElement | null)[]>([])

  // Filter pills based on gold availability
  const pills = goldAvailable ? ALL_PILLS : ALL_PILLS.filter((p) => p.value !== 'gold')

  // Resolve active value: if gold is not available and active value is 'gold',
  // fall back to default.
  const rawActive: BenchmarkValue = value ?? internalBenchmark
  const activeBenchmark: BenchmarkValue =
    !goldAvailable && rawActive === 'gold' ? DEFAULT_BENCHMARK : rawActive

  function handleSelect(b: BenchmarkValue): void {
    if (onChange) {
      onChange(b)
    } else {
      setInternalBenchmark(b)
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>): void {
    const idx = pills.findIndex((p) => p.value === activeBenchmark)

    if (e.key === 'ArrowRight') {
      e.preventDefault()
      const next = (idx + 1) % pills.length
      handleSelect(pills[next].value)
      pillRefs.current[next]?.focus()
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      const prev = (idx - 1 + pills.length) % pills.length
      handleSelect(pills[prev].value)
      pillRefs.current[prev]?.focus()
    } else if (e.key === 'Home') {
      e.preventDefault()
      handleSelect(pills[0].value)
      pillRefs.current[0]?.focus()
    } else if (e.key === 'End') {
      e.preventDefault()
      const last = pills.length - 1
      handleSelect(pills[last].value)
      pillRefs.current[last]?.focus()
    }
  }

  return (
    <div
      role="radiogroup"
      aria-label="Benchmark"
      onKeyDown={handleKeyDown}
      className={`inline-flex border border-paper-rule rounded-[2px] overflow-hidden ${className}`}
    >
      {pills.map((pill, i) => {
        const isActive = pill.value === activeBenchmark
        return (
          <button
            key={pill.value}
            ref={(el) => { pillRefs.current[i] = el }}
            type="button"
            role="radio"
            aria-checked={isActive}
            tabIndex={isActive ? 0 : -1}
            onClick={() => handleSelect(pill.value)}
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
            {pill.label}
          </button>
        )
      })}
    </div>
  )
}

// Re-export BenchmarkValue so consumers don't need to import from persistence.
export type { BenchmarkValue }
