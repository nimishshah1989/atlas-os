// src/lib/basketTray.ts — the draft basket: what the "+" on a row adds to, before there is a basket.
//
// WHAT THIS IS. The FM: "every instrument has a plus sign… it can be added to any existing
// portfolio, or there is an option to create a new portfolio similar to Atlas." The second half is
// this file. The plus collects symbols into a DRAFT in the browser; the tray offers to open the
// builder with them, and the builder's server action validates every one against instrument_master
// and the thresholds before anything is written. Nothing here writes a row.
//
// WHY NOT THE FIRST HALF, YET. Adding a name to an EXISTING basket is a new version of its
// constituents with re-normalised weights and rebalance trades — and mark_baskets.py refuses to mark
// any book with a non-inception trade ("marking a rebalanced book is not built yet (basket
// versioning)"). A "+" that wrote version 2 would produce a basket the nightly cannot value. That
// is engine work with tests on real bars, not a button, and the button waits for it.
//
// ONE DRAFT PER KIND. A basket is an ETF basket or a stock basket (basket_master.kind), so the
// draft is too: adding AAPL and SPY makes two drafts, and the tray says so rather than letting the
// builder refuse a mixed list later.
//
// STORAGE IS localStorage, which can be absent (a private window, a locked-down profile) — every
// read and write is guarded, and with no storage the tray simply holds nothing.
import { useEffect, useState } from 'react'

export type DraftKind = 'etf' | 'stock'
export type Draft = Record<DraftKind, string[]>

const KEY = 'atlas-global:basket-draft'
const EVENT = 'atlas-global:basket-draft'
const EMPTY: Draft = { etf: [], stock: [] }
/** The most a draft holds — the builder's seed limit, and past a dozen the FM is indexing. */
export const DRAFT_LIMIT = 50
const SYMBOL_RE = /^[A-Z0-9.\-$]{1,12}$/

const clean = (list: unknown): string[] =>
  Array.isArray(list) ? [...new Set(list.filter((s): s is string => typeof s === 'string' && SYMBOL_RE.test(s)))].slice(0, DRAFT_LIMIT) : []

export function readDraft(): Draft {
  try {
    const raw = globalThis.localStorage?.getItem(KEY)
    if (!raw) return EMPTY
    const parsed = JSON.parse(raw) as Partial<Draft>
    return { etf: clean(parsed.etf), stock: clean(parsed.stock) }
  } catch {
    return EMPTY
  }
}

export function writeDraft(draft: Draft): void {
  try {
    globalThis.localStorage?.setItem(KEY, JSON.stringify(draft))
  } catch {
    // no storage: the draft lives only as long as this render
  }
  globalThis.dispatchEvent?.(new Event(EVENT))
}

export function isInDraft(kind: DraftKind, symbol: string, draft = readDraft()): boolean {
  return draft[kind].includes(symbol)
}

/** Add or remove one symbol; returns the new draft. Adding past the limit is refused, not truncated. */
export function toggleDraft(kind: DraftKind, symbol: string): Draft {
  const draft = readDraft()
  const list = draft[kind]
  const next = list.includes(symbol) ? list.filter((s) => s !== symbol) : list.length >= DRAFT_LIMIT ? list : [...list, symbol]
  const out = { ...draft, [kind]: next }
  writeDraft(out)
  return out
}

export function clearDraft(kind?: DraftKind): Draft {
  const out = kind ? { ...readDraft(), [kind]: [] } : EMPTY
  writeDraft(out)
  return out
}

/** The builder's address for a draft — the same `?symbols=` a theme or a market page seeds it with,
 *  so the one validation path serves both. */
export function draftHref(kind: DraftKind, draft = readDraft()): string {
  const p = new URLSearchParams({ symbols: draft[kind].join(','), kind })
  return `/portfolios/new?${p.toString()}`
}

/** The draft as React state: every "+" and the tray read one value and re-render together. Starts
 *  EMPTY on both server and first client paint, then reads storage — so the server-rendered HTML
 *  and the hydrated tree agree, and nothing flashes. */
export function useDraft(): Draft {
  const [draft, setDraft] = useState<Draft>(EMPTY)
  useEffect(() => {
    const sync = () => setDraft(readDraft())
    sync()
    window.addEventListener(EVENT, sync)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener(EVENT, sync)
      window.removeEventListener('storage', sync)
    }
  }, [])
  return draft
}
