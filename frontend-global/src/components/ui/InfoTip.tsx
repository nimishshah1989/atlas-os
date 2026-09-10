// src/components/ui/InfoTip.tsx — ported verbatim in spirit from Atlas India's
// frontend/src/components/ui/InfoTip.tsx (§1.4, "every table and chart can carry one").
//
// WHY THIS EXISTS ON THIS BOARD. A methodology decision the FM must know to read a number is a
// FACT and never gets deleted; a paragraph restating what the number obviously is, is prose and
// does. This is where the first kind goes when it would otherwise be a paragraph: one 17-px glyph
// on the title row, the sentence on hover or focus.
//
// Pure CSS — hover and focus-within, no state, no effect — so it renders inside a server
// component with no client bundle, exactly as it does on India.
//
// IT MUST RESET WHAT IT INHERITS, and the reason is that its usual home is a table header.
// `.panel table th` in globals.css sets `white-space: nowrap` (so a column label never wraps) and
// `text-transform: uppercase` (the desk's small caps) — and a tooltip nested inside that <th>
// inherits both. The FM caught it on /sectors: a three-sentence explanation rendered AS ONE LINE
// OF CAPITALS running off the right edge of the screen, past the window, with `w-[290px]` doing
// nothing because nowrap makes content overflow a fixed width rather than wrap inside it.
//
// The bug was there from the port and only became visible when the text got long enough to leave
// the table. So the panel resets every inherited text property it cares about — case, wrapping,
// tracking, weight, alignment — rather than trusting whatever element it happens to sit in.
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
        className="pointer-events-none absolute right-0 top-[150%] z-50 w-[290px] max-w-[calc(100vw-32px)] whitespace-normal rounded-tile border border-edge-rule bg-surface-raised p-3 text-left align-baseline text-[11.5px] font-normal normal-case leading-[1.55] tracking-normal text-txt-2 opacity-0 shadow-panel transition-opacity duration-150 group-hover/info:opacity-100 group-focus-within/info:opacity-100"
      >
        {title && (
          <span className="mb-1 block font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">{title}</span>
        )}
        {children}
      </span>
    </span>
  )
}
