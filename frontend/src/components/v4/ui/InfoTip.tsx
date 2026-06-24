// Self-explaining note (§1.4) — every table/chart can carry one. Pure-CSS
// hover/focus popover (no client JS) so it works inside server components.
import type { ReactNode } from 'react'

export function InfoTip({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <span className="group/info relative inline-flex">
      <button
        type="button"
        aria-label={title ? `About ${title}` : 'More info'}
        className="grid h-[15px] w-[15px] place-items-center rounded-full border border-edge-rule font-num text-[9px] leading-none text-txt-3 transition-colors hover:border-edge-strong hover:text-txt-1 focus:text-txt-1 focus:outline-none"
      >
        i
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-[150%] z-50 w-[240px] -translate-x-1/2 rounded-tile border border-edge-rule bg-surface-raised p-3 text-[11px] leading-[1.5] text-txt-2 opacity-0 shadow-panel transition-opacity duration-150 group-hover/info:opacity-100 group-focus-within/info:opacity-100"
      >
        {title && <span className="mb-1 block font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">{title}</span>}
        {children}
      </span>
    </span>
  )
}
