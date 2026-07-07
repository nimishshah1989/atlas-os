'use client'
// PortfolioBuilder — the "New portfolio" flow on /portfolios. Name it, set capital,
// then add instruments (stock/ETF/fund) by search, each with a % weight. Weights may
// sum to <=100% (the remainder stays in cash). On create, POST /api/portfolios/create
// { name, capital, holdings } — the Python engine books each at the last EOD close.
import { useState } from 'react'
import { Plus, X, Trash2 } from 'lucide-react'
import { InstrumentAutocomplete, type Hit } from './InstrumentAutocomplete'

type Row = {
  id: number
  assetClass: 'stock' | 'etf' | 'fund'
  pick: Hit | null
  weightPct: string
}

const CLASSES: { v: Row['assetClass']; label: string }[] = [
  { v: 'stock', label: 'Stock' },
  { v: 'etf', label: 'ETF' },
  { v: 'fund', label: 'Mutual fund' },
]

let seq = 1
const blankRow = (): Row => ({ id: seq++, assetClass: 'stock', pick: null, weightPct: '' })

export function PortfolioBuilder() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 rounded-tile bg-brand px-3.5 py-2 font-sans text-[12.5px] font-semibold text-white transition-opacity hover:opacity-90"
      >
        <Plus size={15} /> New portfolio
      </button>
      {open && <Modal onClose={() => setOpen(false)} />}
    </>
  )
}

function Modal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('')
  const [capital, setCapital] = useState('1000000')
  const [rows, setRows] = useState<Row[]>([blankRow()])
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string; href?: string } | null>(null)

  const setRow = (id: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)))

  const allocated = rows.reduce((s, r) => s + (Number(r.weightPct) || 0), 0)
  const capNum = Number(capital)
  const picked = rows.filter((r) => r.pick && Number(r.weightPct) > 0)
  const canSubmit =
    !busy &&
    name.trim().length >= 2 &&
    Number.isFinite(capNum) &&
    capNum >= 100000 &&
    picked.length > 0 &&
    allocated <= 100.0001 &&
    rows.every((r) => !r.pick || Number(r.weightPct) > 0)

  const submit = async () => {
    setBusy(true)
    setMsg(null)
    try {
      const res = await fetch('/api/portfolios/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          capital: Math.round(capNum),
          holdings: picked.map((r) => ({ key: r.pick!.key, weightPct: Number(r.weightPct) })),
        }),
      })
      const d = await res.json()
      if (!res.ok) setMsg({ ok: false, text: d.message ?? 'failed' })
      else
        setMsg({
          ok: true,
          text: 'Portfolio created and booked at the last EOD close — backtest is computing.',
          href: `/portfolios/${d.data.portfolioId}`,
        })
    } catch (e) {
      setMsg({ ok: false, text: String(e) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[70] flex items-start justify-center overflow-y-auto py-10">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative w-[620px] max-w-[94vw] rounded-panel border border-edge-rule bg-surface-panel p-5 shadow-panel">
        <div className="mb-4 flex items-start justify-between">
          <div>
            <div className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Portfolios</div>
            <h3 className="font-display text-[18px] font-medium text-txt-1">Build a new portfolio</h3>
          </div>
          <button onClick={onClose} aria-label="Close" className="p-1 text-txt-3 hover:text-txt-1">
            <X size={16} />
          </button>
        </div>

        {msg?.ok ? (
          <p className="font-sans text-[13px] text-sig-pos">
            {msg.text}{' '}
            {msg.href && (
              <a href={msg.href} className="text-brand underline">
                View portfolio →
              </a>
            )}
          </p>
        ) : (
          <>
            <div className="mb-4 grid grid-cols-2 gap-3">
              <label className="block">
                <span className="mb-1 block font-sans text-[11px] text-txt-3">Name</span>
                <input
                  autoFocus
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Defence Conviction"
                  className="w-full rounded-tile border border-edge-rule bg-surface-base px-2.5 py-1.5 font-sans text-[13px] text-txt-1 outline-none focus:border-brand"
                />
              </label>
              <label className="block">
                <span className="mb-1 block font-sans text-[11px] text-txt-3">Starting capital (₹)</span>
                <input
                  value={capital}
                  onChange={(e) => setCapital(e.target.value.replace(/[^0-9]/g, ''))}
                  inputMode="numeric"
                  className="w-full rounded-tile border border-edge-rule bg-surface-base px-2.5 py-1.5 font-num tabular-nums text-[13px] text-txt-1 outline-none focus:border-brand"
                />
              </label>
            </div>

            <div className="space-y-2">
              {rows.map((r) => (
                <div key={r.id} className="flex items-center gap-2">
                  <select
                    value={r.assetClass}
                    onChange={(e) => setRow(r.id, { assetClass: e.target.value as Row['assetClass'], pick: null })}
                    className="shrink-0 rounded-tile border border-edge-rule bg-surface-base px-2 py-1.5 font-sans text-[12.5px] text-txt-1 outline-none focus:border-brand"
                  >
                    {CLASSES.map((c) => (
                      <option key={c.v} value={c.v}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                  <div className="min-w-0 flex-1">
                    <InstrumentAutocomplete
                      key={`${r.id}-${r.assetClass}`}
                      assetClass={r.assetClass}
                      onPick={(h) => setRow(r.id, { pick: h })}
                    />
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <input
                      value={r.weightPct}
                      onChange={(e) => setRow(r.id, { weightPct: e.target.value.replace(/[^0-9.]/g, '') })}
                      inputMode="decimal"
                      placeholder="%"
                      className="w-16 rounded-tile border border-edge-rule bg-surface-base px-2 py-1.5 text-right font-num tabular-nums text-[13px] text-txt-1 outline-none focus:border-brand"
                    />
                    <span className="font-sans text-[12px] text-txt-3">%</span>
                  </div>
                  <button
                    onClick={() => setRows((rs) => (rs.length > 1 ? rs.filter((x) => x.id !== r.id) : rs))}
                    aria-label="Remove"
                    className="shrink-0 p-1 text-txt-3 hover:text-sig-neg"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>

            <button
              onClick={() => setRows((rs) => [...rs, blankRow()])}
              className="mt-2 flex items-center gap-1 font-sans text-[12.5px] text-brand hover:underline"
            >
              <Plus size={13} /> Add instrument
            </button>

            <div className="mt-4 flex items-center justify-between border-t border-edge-hair pt-3 font-num text-[12.5px] tabular-nums">
              <span className={allocated > 100.0001 ? 'text-sig-neg' : 'text-txt-2'}>
                Allocated {allocated.toFixed(1)}%
              </span>
              <span className="text-txt-3">Cash {Math.max(0, 100 - allocated).toFixed(1)}%</span>
            </div>

            {msg && !msg.ok && <p className="mt-2 font-sans text-[12.5px] text-sig-neg">{msg.text}</p>}

            <div className="mt-4 flex justify-end gap-2">
              <button onClick={onClose} className="rounded-tile px-3 py-1.5 font-sans text-[12.5px] text-txt-2 hover:text-txt-1">
                Cancel
              </button>
              <button
                onClick={submit}
                disabled={!canSubmit}
                className="rounded-tile bg-brand px-3.5 py-1.5 font-sans text-[12.5px] font-semibold text-white disabled:opacity-40"
              >
                {busy ? 'Creating…' : 'Create & book'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
