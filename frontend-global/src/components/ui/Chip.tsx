// src/components/ui/Chip.tsx — a pill: a peer group, a cohort, a classification flag. One hairline
// on the raised surface, one radius, the type scale's smallest step. Every colour is a token, so
// the pill follows the palette instead of carrying one of its own.
//
// The `chip` class name is carried alongside the utilities on purpose: the desk design language
// names that class, and anything it adds (tracking, case, weight) lands on these same elements
// without this file changing.
import type { ReactNode } from 'react'

export function Chip({
  children,
  title,
  className = '',
}: {
  children: ReactNode
  title?: string
  className?: string
}) {
  return (
    <span
      className={`chip inline-flex max-w-full items-center gap-1 truncate rounded-panel border border-hair bg-raised px-1.5 py-px text-meta text-ink-2 ${className}`}
      title={title}
    >
      {children}
    </span>
  )
}

/** The same pill as a filter control: pressed when its value is the current selection. */
export function ChipButton({
  children,
  pressed,
  onClick,
  title,
}: {
  children: ReactNode
  pressed: boolean
  onClick: () => void
  title?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={pressed}
      title={title}
      className={`chip inline-flex items-center gap-1.5 rounded-panel border px-2 py-1 text-meta ${
        pressed ? 'border-ink bg-ink text-ground' : 'border-hair bg-raised text-ink-2 hover:text-ink'
      }`}
    >
      {children}
    </button>
  )
}
