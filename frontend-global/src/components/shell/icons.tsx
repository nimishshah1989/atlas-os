// src/components/shell/icons.tsx — the one stroke set. Inline SVG on a 16-grid, 1.5 px stroke,
// currentColor; sized 16 or 20. No emoji anywhere on the board.
import type { ReactNode } from 'react'

export type IconName =
  | 'today'
  | 'etfs'
  | 'countries'
  | 'sectors'
  | 'stocks'
  | 'baskets'
  | 'methodology'
  | 'admin'
  | 'search'
  | 'sun'
  | 'moon'

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
  countries: (
    <>
      <circle cx="8" cy="8" r="6" />
      <path d="M2 8h12M8 2c-2.4 2.8-2.4 9.2 0 12M8 2c2.4 2.8 2.4 9.2 0 12" />
    </>
  ),
  sectors: (
    <>
      <circle cx="8" cy="8" r="6" />
      <path d="M8 2v6h6" />
    </>
  ),
  stocks: (
    <>
      <path d="M2 12l4-5 3 3 5-6" />
      <path d="M10.5 4H14v3.5" />
    </>
  ),
  baskets: (
    <>
      <path d="M2 6h12l-1.5 7.5h-9L2 6z" />
      <path d="M5.5 6L7 2.5M10.5 6L9 2.5M2 9.5h12" />
    </>
  ),
  methodology: (
    <>
      <path d="M3.5 2.5h8a1 1 0 0 1 1 1V13H4.5a1 1 0 0 1-1-1V2.5z" />
      <path d="M3.5 11h9M6 5.5h4" />
    </>
  ),
  admin: (
    <>
      <path d="M2.5 4.5h11M2.5 8h11M2.5 11.5h11" />
      <circle cx="6" cy="4.5" r="1.4" fill="currentColor" stroke="none" />
      <circle cx="10.5" cy="8" r="1.4" fill="currentColor" stroke="none" />
      <circle cx="5" cy="11.5" r="1.4" fill="currentColor" stroke="none" />
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
