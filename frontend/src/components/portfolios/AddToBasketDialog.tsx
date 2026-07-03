'use client'
// AddToBasketDialog — pick "new basket" (named) or an existing one, then book the
// selected instruments as manual buys via /api/portfolios/create. All booking is
// done by the Python engine at the last EOD close; this dialog only collects intent.
import { useEffect, useState } from 'react'
import { X } from 'lucide-react'

export type BasketPick = { key: string; label: string } // key = "stock:SYMBOL" | "etf:SYMBOL" | "fund:MSTAR_ID"

type Basket = { id: string; name: string }

export function AddToBasketDialog({ picks, onClose }: { picks: BasketPick[]; onClose: () => void }) {
  const [baskets, setBaskets] = useState<Basket[]>([])
  const [target, setTarget] = useState<'new' | string>('new')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string; href?: string } | null>(null)

  useEffect(() => {
    fetch('/api/portfolios/baskets')
      .then((r) => r.json())
      .then((d) => setBaskets(d.baskets ?? []))
      .catch(() => setBaskets([]))
  }, [])

  const submit = async () => {
    setBusy(true)
    setMsg(null)
    try {
      const body =
        target === 'new'
          ? { name: name.trim(), picks: picks.map((p) => p.key) }
          : { basketId: target, picks: picks.map((p) => p.key) }
      const res = await fetch('/api/portfolios/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const d = await res.json()
      if (!res.ok) setMsg({ ok: false, text: d.message ?? 'failed' })
      else if (target === 'new')
        setMsg({
          ok: true,
          text: 'Basket created and booked at the last EOD close — backtest is computing.',
          href: `/portfolios/${d.data.portfolioId}`,
        })
      else {
        const results: { ok: boolean; pick: string; detail: string }[] = d.data.results ?? []
        const failed = results.filter((r) => !r.ok)
        setMsg({
          ok: failed.length === 0,
          text: failed.length
            ? `${results.length - failed.length} booked, ${failed.length} failed: ${failed.map((f) => f.detail).join('; ')}`
            : `${results.length} instrument(s) booked at the last EOD close.`,
          href: `/portfolios/${target}`,
        })
      }
    } catch (e) {
      setMsg({ ok: false, text: String(e) })
    } finally {
      setBusy(false)
    }
  }

  const canSubmit = !busy && picks.length > 0 && (target !== 'new' || name.trim().length > 1)

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative w-[420px] max-w-[92vw] rounded-panel border border-edge-rule bg-surface-panel p-5 shadow-panel">
        <div className="mb-3 flex items-start justify-between">
          <div>
            <div className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Portfolios</div>
            <h3 className="font-display text-[17px] font-medium text-txt-1">Add to basket</h3>
          </div>
          <button onClick={onClose} aria-label="Close" className="p-1 text-txt-3 hover:text-txt-1"><X size={16} /></button>
        </div>

        <div className="mb-3 flex flex-wrap gap-1.5">
          {picks.map((p) => (
            <span key={p.key} className="rounded-tile border border-edge-hair bg-surface-raised px-2 py-0.5 font-num text-[11px] tabular-nums text-txt-1">
              {p.label}
            </span>
          ))}
        </div>

        <div className="space-y-2">
          <label className="flex items-center gap-2 font-sans text-[13px] text-txt-1">
            <input type="radio" checked={target === 'new'} onChange={() => setTarget('new')} />
            New basket
          </label>
          {target === 'new' && (
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Basket name (e.g. Defence Conviction)"
              className="w-full rounded-tile border border-edge-rule bg-surface-base px-3 py-1.5 font-sans text-[13px] text-txt-1 outline-none focus:border-brand"
            />
          )}
          {baskets.map((b) => (
            <label key={b.id} className="flex items-center gap-2 font-sans text-[13px] text-txt-1">
              <input type="radio" checked={target === b.id} onChange={() => setTarget(b.id)} />
              {b.name}
            </label>
          ))}
        </div>

        {msg && (
          <p className={`mt-3 font-sans text-[12.5px] ${msg.ok ? 'text-sig-pos' : 'text-sig-neg'}`}>
            {msg.text}{' '}
            {msg.href && (
              <a href={msg.href} className="text-brand underline">View portfolio →</a>
            )}
          </p>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-tile px-3 py-1.5 font-sans text-[12.5px] text-txt-2 hover:text-txt-1">
            {msg?.ok ? 'Done' : 'Cancel'}
          </button>
          {!msg?.ok && (
            <button
              onClick={submit}
              disabled={!canSubmit}
              className="rounded-tile bg-brand px-3.5 py-1.5 font-sans text-[12.5px] font-semibold text-white disabled:opacity-40"
            >
              {busy ? 'Booking…' : target === 'new' ? 'Create & book' : 'Add & book'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
