'use client'
// Type-ahead over /api/instruments/search — pick a stock/ETF/fund by symbol or name.
// Debounced; keyboard-navigable. Returns the picked hit (key + display price) up.
import { useEffect, useRef, useState } from 'react'

export type Hit = {
  key: string // "stock:SYMBOL" | "etf:SYMBOL" | "fund:MSTAR_ID"
  label: string
  sublabel: string
  assetClass: string
  price: number | null
}

export function InstrumentAutocomplete({
  assetClass,
  onPick,
}: {
  assetClass: 'stock' | 'etf' | 'fund'
  onPick: (h: Hit) => void
}) {
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<Hit[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (q.trim().length < 2) {
      setHits([])
      return
    }
    const t = setTimeout(async () => {
      try {
        const r = await fetch(`/api/instruments/search?q=${encodeURIComponent(q)}&class=${assetClass}`)
        const d = await r.json()
        setHits(d.hits ?? [])
        setOpen(true)
        setActive(0)
      } catch {
        setHits([])
      }
    }, 180)
    return () => clearTimeout(t)
  }, [q, assetClass])

  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  const pick = (h: Hit) => {
    onPick(h)
    setQ(h.label)
    setOpen(false)
  }

  const ph =
    assetClass === 'fund' ? 'Type a fund, e.g. Quant Small Cap' : assetClass === 'etf' ? 'Type an ETF, e.g. NIFTYBEES' : 'Type a stock, e.g. REL'

  return (
    <div ref={box} className="relative">
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => hits.length > 0 && setOpen(true)}
        onKeyDown={(e) => {
          if (!open || !hits.length) return
          if (e.key === 'ArrowDown') {
            e.preventDefault()
            setActive((a) => Math.min(a + 1, hits.length - 1))
          } else if (e.key === 'ArrowUp') {
            e.preventDefault()
            setActive((a) => Math.max(a - 1, 0))
          } else if (e.key === 'Enter' && hits[active]) {
            e.preventDefault()
            pick(hits[active])
          } else if (e.key === 'Escape') setOpen(false)
        }}
        placeholder={ph}
        className="w-full rounded-tile border border-edge-rule bg-surface-base px-2.5 py-1.5 font-sans text-[13px] text-txt-1 outline-none focus:border-brand"
      />
      {open && hits.length > 0 && (
        <div className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-tile border border-edge-rule bg-surface-panel shadow-panel">
          {hits.map((h, i) => (
            <button
              key={h.key}
              type="button"
              onClick={() => pick(h)}
              onMouseEnter={() => setActive(i)}
              className={`flex w-full items-center gap-2 px-2.5 py-1.5 text-left font-sans text-[12.5px] ${i === active ? 'bg-surface-raised' : ''}`}
            >
              <span className="font-num font-semibold text-txt-1">{h.label}</span>
              <span className="min-w-0 flex-1 truncate text-txt-3">{h.sublabel}</span>
              {h.price != null && (
                <span className="shrink-0 font-num tabular-nums text-txt-2">
                  ₹{h.price.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
