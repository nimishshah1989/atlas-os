'use client'

// EtfLensTable — the interactive ETF list table (client). Sortable on every column,
// plus a category <select> filter. Default sort = leadership-breadth desc (the headline,
// D26/D27). Presentational only — every value pre-coerced to number|null server-side.
import { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import type { EtfLensRow } from '@/lib/queries/v6/etf_lens'

// ── colour helpers (shared idioms with the stocks pages) ──────────────────
// Lens scores here are 0..100 (holdings-weighted), so the band cuts are scaled ×10
// from the decile helper: ≥80 strong, ≥50 neutral, else weak.
const scoreText = (v: number | null) =>
  v == null ? 'text-ink-tertiary' : v >= 80 ? 'text-signal-pos' : v >= 50 ? 'text-ink-secondary' : 'text-signal-neg'

const breadthText = (b: number | null) =>
  b == null ? 'text-ink-tertiary' : b >= 0.1 ? 'text-signal-pos' : b >= 0.05 ? 'text-teal' : 'text-ink-secondary'

const fmtScore = (v: number | null) => (v == null ? '—' : v.toFixed(0))
const fmtBreadth = (b: number | null) => (b == null ? '—' : `${(b * 100).toFixed(0)}%`)
const fmtExpense = (e: number | null) => (e == null ? '—' : `${e.toFixed(2)}%`) // already in percent units

type LensKey = 'v_tech' | 'v_fund' | 'v_cat' | 'v_flow' | 'v_val'

type SortKey =
  | 'name' | 'category' | 'n_holdings' | 'n_leaders' | 'breadth'
  | LensKey | 'expense' | 'nse_ticker'

type Col = { key: SortKey; label: string; align: 'left' | 'right' }
const COLS: Col[] = [
  { key: 'name', label: 'Name', align: 'left' },
  { key: 'category', label: 'Category', align: 'left' },
  { key: 'n_holdings', label: 'Holdings', align: 'right' },
  { key: 'n_leaders', label: 'Leaders', align: 'right' },
  { key: 'breadth', label: 'Leadership-breadth', align: 'right' },
  { key: 'v_tech', label: 'Tch', align: 'right' },
  { key: 'v_fund', label: 'Fnd', align: 'right' },
  { key: 'v_cat', label: 'Cat', align: 'right' },
  { key: 'v_flow', label: 'Flw', align: 'right' },
  { key: 'v_val', label: 'Val', align: 'right' },
  { key: 'expense', label: 'Expense', align: 'right' },
  { key: 'nse_ticker', label: 'NSE', align: 'left' },
]

// numeric value for a sort key; nulls sink to -Infinity so they sort last on desc.
function numFor(r: EtfLensRow, key: SortKey): number {
  switch (key) {
    case 'n_holdings': return r.n_holdings
    case 'n_leaders': return r.n_leaders
    case 'breadth': return r.breadth ?? -Infinity
    case 'v_tech': return r.v_tech ?? -Infinity
    case 'v_fund': return r.v_fund ?? -Infinity
    case 'v_cat': return r.v_cat ?? -Infinity
    case 'v_flow': return r.v_flow ?? -Infinity
    case 'v_val': return r.v_val ?? -Infinity
    case 'expense': return r.expense ?? Infinity // cheaper sorts "better" on asc
    default: return 0
  }
}

const CONTROL = 'font-sans text-[12px] bg-paper border border-paper-rule rounded-sm px-2 py-1 text-ink-secondary'

export function EtfLensTable({ etfs }: { etfs: EtfLensRow[] }) {
  const router = useRouter()

  const [category, setCategory] = useState<string>('all')
  const [sortKey, setSortKey] = useState<SortKey>('breadth')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  const categories = useMemo(
    () => Array.from(new Set(etfs.map(e => e.category).filter((x): x is string => !!x))).sort(),
    [etfs],
  )

  const filtered = useMemo(
    () => (category === 'all' ? etfs : etfs.filter(e => e.category === category)),
    [etfs, category],
  )

  const sorted = useMemo(() => {
    const sign = sortDir === 'desc' ? -1 : 1
    const out = [...filtered]
    out.sort((a, b) => {
      if (sortKey === 'name') return sign * a.name.localeCompare(b.name)
      if (sortKey === 'category') return sign * (a.category ?? '').localeCompare(b.category ?? '')
      if (sortKey === 'nse_ticker') return sign * (a.nse_ticker ?? '').localeCompare(b.nse_ticker ?? '')
      return sign * (numFor(a, sortKey) - numFor(b, sortKey))
    })
    return out
  }, [filtered, sortKey, sortDir])

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(d => (d === 'desc' ? 'asc' : 'desc'))
    else { setSortKey(key); setSortDir(key === 'expense' ? 'asc' : 'desc') }
  }

  const total = etfs.length
  const shown = sorted.length

  return (
    <div>
      {/* control row */}
      <div className="flex flex-wrap items-end gap-4 mb-4">
        <label className="flex flex-col gap-1">
          <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">Category</span>
          <select className={CONTROL} value={category} onChange={e => setCategory(e.target.value)}>
            <option value="all">All</option>
            {categories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <span className="font-mono text-[12px] text-ink-tertiary self-end ml-auto">
          {shown} of {total} ETFs
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-paper-rule">
              {COLS.map(col => {
                const isSorted = sortKey === col.key
                const arrow = isSorted ? (sortDir === 'desc' ? ' ▼' : ' ▲') : ''
                return (
                  <th
                    key={col.key}
                    onClick={() => toggleSort(col.key)}
                    className={`font-sans text-[10px] uppercase tracking-wider pb-2 px-2 cursor-pointer select-none whitespace-nowrap ${
                      col.align === 'right' ? 'text-right' : 'text-left'
                    } ${isSorted ? 'text-ink-primary font-semibold' : 'text-ink-tertiary'} hover:text-ink-secondary`}
                  >
                    {col.label}{arrow}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {sorted.map(e => (
              <tr
                key={e.fcode}
                onClick={() => router.push('/etfs/' + e.fcode)}
                className="border-b border-paper-rule/50 cursor-pointer hover:bg-paper-soft"
              >
                <td className="py-1.5 px-2 font-sans text-[12px] font-medium text-ink-primary max-w-[260px] truncate">{e.name}</td>
                <td className="py-1.5 px-2 font-sans text-[11px] text-ink-secondary truncate max-w-[160px]">{e.category ?? '—'}</td>
                <td className="py-1.5 px-2 text-right font-mono text-[12px] tabular-nums text-ink-secondary">{e.n_holdings}</td>
                <td className="py-1.5 px-2 text-right font-mono text-[12px] tabular-nums text-ink-secondary">{e.n_leaders}</td>
                <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums font-semibold ${breadthText(e.breadth)}`}>{fmtBreadth(e.breadth)}</td>
                <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${scoreText(e.v_tech)}`}>{fmtScore(e.v_tech)}</td>
                <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${scoreText(e.v_fund)}`}>{fmtScore(e.v_fund)}</td>
                <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${scoreText(e.v_cat)}`}>{fmtScore(e.v_cat)}</td>
                <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${scoreText(e.v_flow)}`}>{fmtScore(e.v_flow)}</td>
                <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${scoreText(e.v_val)}`}>{fmtScore(e.v_val)}</td>
                <td className="py-1.5 px-2 text-right font-mono text-[12px] tabular-nums text-ink-secondary">{fmtExpense(e.expense)}</td>
                <td className="py-1.5 px-2 font-mono text-[10px] text-ink-tertiary whitespace-nowrap">
                  {e.nse_ticker ? <span className="px-1.5 py-0.5 bg-paper-deep border border-paper-rule rounded-[2px]">{e.nse_ticker}</span> : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
