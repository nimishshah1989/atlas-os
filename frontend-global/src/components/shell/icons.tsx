// src/components/shell/icons.tsx — the one stroke set. Inline SVG on a 16-grid, 1.5 px stroke,
// currentColor; sized 16 or 20. No emoji anywhere on the board. The bar's links are text, so the
// set is what the controls need: search, and the sort direction.
import type { ReactNode } from 'react'

export type IconName = 'search' | 'up' | 'down'

const GLYPHS: Record<IconName, ReactNode> = {
  search: (
    <>
      <circle cx="7" cy="7" r="4.5" />
      <path d="M10.5 10.5L14 14" />
    </>
  ),
  up: <path d="M4 10l4-4 4 4" />,
  down: <path d="M4 6l4 4 4-4" />,
}

export function Icon({ name, size = 16, className }: { name: IconName; size?: 16 | 20; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {GLYPHS[name]}
    </svg>
  )
}
