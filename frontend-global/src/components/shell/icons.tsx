// src/components/shell/icons.tsx — the one stroke set. Inline SVG on a 16-grid, 1.5 px stroke,
// currentColor; sized 16 or 20. No emoji anywhere on the board.
import type { ReactNode } from 'react'

export type IconName =
  | 'today'
  | 'etfs'
  | 'stocks'
  | 'countries'
  | 'search'
  | 'sun'
  | 'moon'
  | 'health'
  | 'up'
  | 'down'

const GLYPHS: Record<IconName, ReactNode> = {
  today: (
    <>
      <rect x="2" y="3" width="12" height="11" rx="1" />
      <path d="M2 7h12M5.5 1.5V4M10.5 1.5V4" />
    </>
  ),
  etfs: (
    <>
      <path d="M8 2l6 3-6 3-6-3 6-3z" />
      <path d="M2 8l6 3 6-3M2 11l6 3 6-3" />
    </>
  ),
  stocks: (
    <>
      <path d="M2 12l4-5 3 3 5-6" />
      <path d="M10.5 4H14v3.5" />
    </>
  ),
  // A globe: circle, equator, meridian. Same 16-box, same single stroke as its neighbours —
  // an icon set reads as one set or it reads as a mistake.
  countries: (
    <>
      <circle cx="8" cy="8" r="6" />
      <path d="M2 8h12" />
      <path d="M8 2c2 2 2 10 0 12M8 2c-2 2-2 10 0 12" />
    </>
  ),
  search: (
    <>
      <circle cx="7" cy="7" r="4.5" />
      <path d="M10.5 10.5L14 14" />
    </>
  ),
  sun: (
    <>
      <circle cx="8" cy="8" r="3" />
      <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4" />
    </>
  ),
  moon: <path d="M13 9.5A5.5 5.5 0 1 1 6.5 3a4.5 4.5 0 0 0 6.5 6.5z" />,
  health: <path d="M1.5 8.5h3l1.5-4 2.5 7 2-5 1 2h3" />,
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
