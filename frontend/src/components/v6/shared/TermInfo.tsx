'use client'
// TermInfo — a small eye icon next to a term (VWAP, vol-contraction, …). Hover or click
// reveals a plain-English explainer from the central glossary. Reused everywhere a term
// appears so the meaning is always one glance away. Accessible: button + popover, click
// toggles (mobile) and hover/focus reveals (desktop).
import { useState } from 'react'
import { GLOSSARY, type GlossaryEntry } from '@/lib/v6/glossary'

export function TermInfo({ term, title, body }: { term?: string; title?: string; body?: string }) {
  const [open, setOpen] = useState(false)
  const entry: GlossaryEntry | undefined = term ? GLOSSARY[term] : undefined
  const t = title ?? entry?.title
  const b = body ?? entry?.body
  if (!b) return null // unknown term → render nothing rather than a dead icon

  return (
    <span className="group relative inline-flex align-middle">
      <button
        type="button"
        aria-label={`What is ${t}?`}
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen((v) => !v) }}
        className="ml-1 inline-flex h-[14px] w-[14px] items-center justify-center rounded-full text-txt-3 hover:text-brand focus:text-brand focus:outline-none"
      >
        {/* eye glyph */}
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
          <circle cx="12" cy="12" r="2.6" />
        </svg>
      </button>
      <span
        role="tooltip"
        className={`pointer-events-none absolute bottom-full left-1/2 z-50 mb-1.5 w-[260px] -translate-x-1/2 rounded-tile border border-edge-rule bg-surface-raised px-3 py-2 text-left shadow-panel transition-opacity duration-100
          ${open ? 'opacity-100' : 'opacity-0'} group-hover:opacity-100 group-focus-within:opacity-100`}
      >
        <span className="block font-num text-[10px] font-semibold uppercase tracking-[0.12em] text-txt-1">{t}</span>
        <span className="mt-1 block font-sans text-[11.5px] leading-[1.45] text-txt-2">{b}</span>
      </span>
    </span>
  )
}
