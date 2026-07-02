// Self-explaining note (§1.4) — every table/chart can carry one. Pure-CSS
// hover/focus popover (no client JS) so it works inside server components.
import type { ReactNode } from 'react'

export function InfoTip({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <span className="group/info relative inline-flex">
      <button
        type="button"
        aria-label={title ? `About ${title}` : 'More info'}
        className="grid h-[17px] w-[17px] place-items-center rounded-full border border-brand/50 bg-brand/5 font-num text-[10px] font-semibold italic leading-none text-brand transition-colors hover:border-brand hover:bg-brand/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
      >
        i
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-[150%] z-50 w-[280px] -translate-x-1/2 rounded-tile border border-edge-rule bg-surface-raised p-3 text-[11.5px] leading-[1.55] text-txt-2 opacity-0 shadow-panel transition-opacity duration-150 group-hover/info:opacity-100 group-focus-within/info:opacity-100"
      >
        {title && <span className="mb-1 block font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">{title}</span>}
        {children}
      </span>
    </span>
  )
}
