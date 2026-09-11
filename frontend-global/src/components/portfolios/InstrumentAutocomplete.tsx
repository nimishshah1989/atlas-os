'use client'
// src/components/portfolios/InstrumentAutocomplete.tsx — a symbol box that suggests as you type.
//
// The FM: "if I'm just writing 2, 3, or 4 letters, the system should have a suggestion box." The
// suggestions are the board's own directory (instrument_master, through a server action — the
// board reads Postgres directly, no internal API), so what is offered is what the action will
// accept. A name outside the universe is offered but says so: a basket is meant to hold what the
// FM's rules offer, and the note lets him decide with the fact in front of him.
//
// Debounced, keyboard-navigable (↑ ↓ Enter Escape), one open list at a time. The input stays a
// plain controlled text box — the form posts `symbol` exactly as before — so the server action's
// validation is unchanged.
import { useEffect, useRef, useState } from 'react'
import type { Suggestion } from '@/lib/basketDraft'

const MIN_CHARS = 1
const DEBOUNCE_MS = 150

export function InstrumentAutocomplete({
  value,
  onChange,
  kind,
  suggest,
  name = 'symbol',
  placeholder,
}: {
  value: string
  onChange: (symbol: string) => void
  kind: 'etf' | 'stock'
  /** The server action; injected so the component is testable without one. */
  suggest: (q: string, kind: 'etf' | 'stock') => Promise<Suggestion[]>
  name?: string
  placeholder?: string
}) {
  const [hits, setHits] = useState<Suggestion[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [picked, setPicked] = useState<string | null>(null)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const q = value.trim()
    // A value that was just picked is not a query; nor is a value the list already answered.
    if (q.length < MIN_CHARS || q === picked) {
      setHits([])
      setOpen(false)
      return
    }
    let stale = false
    const t = setTimeout(async () => {
      try {
        const out = await suggest(q, kind)
        if (stale) return
        setHits(out)
        setOpen(out.length > 0)
        setActive(0)
      } catch {
        if (!stale) setHits([])
      }
    }, DEBOUNCE_MS)
    return () => {
      stale = true
      clearTimeout(t)
    }
  }, [value, kind, picked, suggest])

  useEffect(() => {
    const away = (e: PointerEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', away)
    return () => document.removeEventListener('pointerdown', away)
  }, [])

  const pick = (h: Suggestion) => {
    setPicked(h.symbol)
    onChange(h.symbol)
    setOpen(false)
  }

  return (
    <div ref={box} className="relative">
      <input
        className="field text-body uppercase"
        name={name}
        value={value}
        onChange={(e) => {
          setPicked(null)
          onChange(e.target.value.toUpperCase())
        }}
        onFocus={() => hits.length > 0 && setOpen(true)}
        onKeyDown={(e) => {
          if (!open || hits.length === 0) return
          if (e.key === 'ArrowDown') {
            e.preventDefault()
            setActive((a) => Math.min(a + 1, hits.length - 1))
          } else if (e.key === 'ArrowUp') {
            e.preventDefault()
            setActive((a) => Math.max(a - 1, 0))
          } else if (e.key === 'Enter') {
            e.preventDefault()
            if (hits[active]) pick(hits[active])
          } else if (e.key === 'Escape') setOpen(false)
        }}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        aria-controls={`${name}-suggestions`}
      />
      {open && hits.length > 0 && (
        <ul id={`${name}-suggestions`} role="listbox" className="suggest panel">
          {hits.map((h, i) => (
            <li key={h.symbol} role="option" aria-selected={i === active}>
              <button
                type="button"
                className={`suggest-row${i === active ? ' active' : ''}`}
                onMouseEnter={() => setActive(i)}
                onClick={() => pick(h)}
              >
                <span className="dt-symbol">{h.symbol}</span>
                <span className="suggest-name">{h.name ?? '—'}</span>
                {h.in_universe === false && <span className="suggest-note">outside the universe</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
