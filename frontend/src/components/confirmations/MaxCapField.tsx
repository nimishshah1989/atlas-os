'use client'
// The book's max position cap. Anything at, above, or within 1% of it pre-fills the
// sell side next week — so this one number decides what the FM is asked to review.
import { useRouter } from 'next/navigation'
import { useState } from 'react'

import { CAP_TOLERANCE_PCT, type PortfolioCode } from '@/lib/confirmations'

export function MaxCapField({ code, capPct }: { code: PortfolioCode; capPct: number }) {
  const router = useRouter()
  const [value, setValue] = useState(capPct ? String(capPct) : '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const commit = async () => {
    const next = value.trim() === '' ? 0 : Number(value)
    if (!Number.isFinite(next)) {
      setErr('numbers only')
      return
    }
    if (next === capPct) return
    setBusy(true)
    setErr(null)
    try {
      const r = await fetch('/api/confirmations/cap', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, capPct: next }),
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) setErr(d.message ?? 'could not save')
      else {
        setValue(d.capPct ? String(d.capPct) : '')
        router.refresh()
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex items-baseline gap-2">
      <label htmlFor={`cap-${code}`} className="font-num text-[9px] uppercase tracking-wider text-txt-3">
        Max cap
      </label>
      <input
        id={`cap-${code}`}
        inputMode="decimal"
        value={value}
        placeholder="—"
        disabled={busy}
        onChange={(e) => setValue(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === 'Enter' && commit()}
        className="w-14 rounded-tile border border-edge-rule bg-surface-base px-1.5 py-0.5 text-right font-num text-[12px] tabular-nums text-txt-1 outline-none focus:border-brand"
      />
      <span className="font-num text-[11px] text-txt-3">%</span>
      {err ? (
        <span className="font-sans text-[10px] text-sig-neg">{err}</span>
      ) : capPct > 0 ? (
        <span className="font-sans text-[10px] text-txt-3">
          ≥{(capPct - CAP_TOLERANCE_PCT).toFixed(1)}% pre-fills sells
        </span>
      ) : (
        <span className="font-sans text-[10px] text-txt-3">set to pre-fill sells</span>
      )}
    </div>
  )
}
