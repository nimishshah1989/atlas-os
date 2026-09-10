'use client'
// src/components/portfolios/BasketBuilder.tsx — the "New basket" form: a name, a kind, capital,
// and rows of {symbol, weight %}. Controlled inputs, so a refused submit hands back exactly what
// was typed with the reasons beside it; the server action validates again, against the
// thresholds, before anything is written. The running total is shown in the same integer
// arithmetic the action uses (src/lib/basketDraft.ts), so what the form says adds up is what
// the action will accept.
import { useActionState, useState } from 'react'
import { createBasket } from '@/app/portfolios/new/actions'
import { KINDS, microToPct, pctToMicro, type DraftInput, type FormState } from '@/lib/basketDraft'

type Row = { id: number; symbol: string; weightPct: string }

export type BuilderLimits = {
  /** Whole dollars, for the placeholder and the floor sentence. */
  defaultCapital: string
  /** Percentages for the copy ("25", "1"). */
  capPct: string
  floorPct: string
  /** ceil(100 / cap): the fewest names that can carry the whole capital. */
  minRows: number
}

const MICRO = 1_000_000
let seq = 1
const blank = (): Row => ({ id: seq++, symbol: '', weightPct: '' })

export function BasketBuilder({
  limits,
  session,
  seed,
  seedName,
}: {
  limits: BuilderLimits
  session: string | null
  /** Rows the page arrived with — a theme's funds, a market's funds — equal-weighted. A STARTING
   *  POINT, not a recommendation: equal weight says "I have not decided yet", which is the honest
   *  state of a basket seeded from a list one click ago. */
  seed?: { symbol: string; weightPct: string }[]
  /** A name the page arrived with, so a basket built from Water opens called "Water". */
  seedName?: string
}) {
  const initial: FormState = {
    errors: [],
    notes: [],
    values: {
      name: seedName ?? '',
      kind: KINDS[0],
      capital: limits.defaultCapital,
      // A refused submit hands back what was typed, and THAT must win over the link's seed —
      // otherwise correcting one weight would silently reset every other row to equal.
      rows: seed ?? [],
    },
  }
  const [state, formAction, pending] = useActionState(createBasket, initial)
  const [values, setValues] = useState<Omit<DraftInput, 'rows'>>({
    name: state.values.name,
    kind: state.values.kind,
    capital: state.values.capital,
  })
  const [rows, setRows] = useState<Row[]>(() =>
    state.values.rows.length
      ? state.values.rows.map((r) => ({ ...blank(), ...r }))
      : Array.from({ length: limits.minRows }, blank),
  )
  const setRow = (id: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)))

  const allocated = rows.reduce((s, r) => s + (pctToMicro(r.weightPct) ?? 0), 0)
  const complete = allocated === MICRO
  const remaining = MICRO - allocated

  return (
    <form action={formAction} className="panel max-w-[720px] px-6 py-5">
      {state.errors.length > 0 && (
        <div className="notice" role="alert">
          <span className="dot bg-neg" aria-hidden="true" />
          <ul className="text-body text-ink">
            {state.errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <label className="block sm:col-span-2">
          <span className="mb-1 block text-meta text-ink-2">Name</span>
          <input
            className="field text-body"
            name="name"
            value={values.name}
            onChange={(e) => setValues((v) => ({ ...v, name: e.target.value }))}
            placeholder="e.g. Core four"
            autoFocus
            required
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-meta text-ink-2">Kind</span>
          <select
            className="field text-body"
            name="kind"
            value={values.kind}
            onChange={(e) => setValues((v) => ({ ...v, kind: e.target.value }))}
          >
            <option value="etf">ETF basket</option>
            <option value="stock">Stock basket</option>
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-meta text-ink-2">Starting capital (USD)</span>
          <input
            className="field num text-body"
            name="capital"
            inputMode="numeric"
            value={values.capital}
            onChange={(e) => setValues((v) => ({ ...v, capital: e.target.value.replace(/[^0-9]/g, '') }))}
            placeholder={limits.defaultCapital}
          />
        </label>
        <p className="text-meta text-ink-3 sm:col-span-2 sm:self-end">
          At least ${Number(limits.defaultCapital).toLocaleString('en-US')}. Each name between {limits.floorPct}% and{' '}
          {limits.capPct}% of capital; the weights must sum to exactly 100%.
        </p>
      </div>

      <table className="tbl mt-6">
        <thead>
          <tr>
            <th>Symbol</th>
            <th className="r">Weight %</th>
            <th aria-label="Remove" />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>
                <input
                  className="field text-body uppercase"
                  name="symbol"
                  value={r.symbol}
                  onChange={(e) => setRow(r.id, { symbol: e.target.value.toUpperCase() })}
                  placeholder={values.kind === 'etf' ? 'e.g. SPY' : 'e.g. AAPL'}
                  autoComplete="off"
                  spellCheck={false}
                />
              </td>
              <td className="r">
                <input
                  className="field num text-body text-right"
                  name="weight"
                  inputMode="decimal"
                  value={r.weightPct}
                  onChange={(e) => setRow(r.id, { weightPct: e.target.value.replace(/[^0-9.]/g, '') })}
                  placeholder="25"
                />
              </td>
              <td className="r">
                <button
                  type="button"
                  className="btn btn-quiet text-meta"
                  onClick={() => setRows((rs) => (rs.length > 1 ? rs.filter((x) => x.id !== r.id) : rs))}
                  aria-label={`Remove ${r.symbol || 'row'}`}
                >
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <button type="button" className="btn text-body" onClick={() => setRows((rs) => [...rs, blank()])}>
          Add a name
        </button>
        <p className={`num text-body ${complete ? 'text-pos' : allocated > MICRO ? 'text-neg' : 'text-ink-2'}`} data-allocated={allocated}>
          Allocated {microToPct(allocated)}%
          {complete ? ' — whole' : remaining > 0 ? ` — ${microToPct(remaining)}% still to place` : ` — ${microToPct(-remaining)}% over`}
        </p>
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-hair pt-4">
        <p className="text-meta text-ink-3">
          {session
            ? `Booked at the ${session} close by the next mark, within five minutes of saving.`
            : 'No SPY session on this board yet: the basket is saved, and booked once bars exist.'}
        </p>
        <button type="submit" className="btn btn-primary text-body" disabled={pending}>
          {pending ? 'Saving…' : 'Save basket'}
        </button>
      </div>
    </form>
  )
}
