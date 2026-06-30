'use client'
// TermInfo — a small eye icon next to a term (VWAP, swing, RS, …). Hover or click reveals a
// plain-English explainer from the central glossary. The popover is rendered in a PORTAL with
// fixed positioning so it is NOT clipped by an ancestor's overflow (e.g. a table's
// `overflow-x-auto`, which previously hid these tooltips inside the funds/sectors tables).
import { useState, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { GLOSSARY, type GlossaryEntry } from '@/lib/v6/glossary'

export function TermInfo({ term, title, body }: { term?: string; title?: string; body?: string }) {
  const entry: GlossaryEntry | undefined = term ? GLOSSARY[term] : undefined
  const t = title ?? entry?.title
  const b = body ?? entry?.body
  const btnRef = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<{ left: number; top: number; below: boolean } | null>(null)

  const place = useCallback(() => {
    const el = btnRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const below = r.top < 130 // near the viewport top (e.g. a sticky header) → drop the tooltip below
    setPos({ left: r.left + r.width / 2, top: below ? r.bottom + 6 : r.top - 6, below })
  }, [])

  if (!b) return null // unknown term → render nothing rather than a dead icon

  return (
    <span className="relative inline-flex align-middle">
      <button
        ref={btnRef}
        type="button"
        aria-label={`What is ${t}?`}
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); place(); setOpen((v) => !v) }}
        onMouseEnter={() => { place(); setOpen(true) }}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => { place(); setOpen(true) }}
        onBlur={() => setOpen(false)}
        className="ml-1 inline-flex h-[14px] w-[14px] items-center justify-center rounded-full text-txt-3 hover:text-brand focus:text-brand focus:outline-none"
      >
        {/* eye glyph */}
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
          <circle cx="12" cy="12" r="2.6" />
        </svg>
      </button>
      {open && pos && typeof document !== 'undefined' && createPortal(
        <span
          role="tooltip"
          style={{
            position: 'fixed', left: pos.left, top: pos.top,
            transform: pos.below ? 'translate(-50%, 0)' : 'translate(-50%, -100%)',
          }}
          className="pointer-events-none z-[100] block w-[260px] rounded-tile border border-edge-rule bg-surface-raised px-3 py-2 text-left shadow-panel"
        >
          <span className="block font-num text-[10px] font-semibold uppercase tracking-[0.12em] text-txt-1">{t}</span>
          <span className="mt-1 block font-sans text-[11.5px] leading-[1.45] text-txt-2">{b}</span>
        </span>,
        document.body,
      )}
    </span>
  )
}
