'use client'

// FundLensTable — the interactive fund list table (client). Sortable on every column,
// plus a category <select> filter. Default sort = leadership-breadth desc (the headline,
// D26/D27); expense sorts cheapest-first. Mirrors EtfLensTable. Presentational only —
// every value pre-coerced to number|null server-side.
import { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import type { FundLensRow } from '@/lib/queries/v6/fund_lens'

// ── colour helpers (shared idioms with the stocks / ETF pages) ────────────
// Weighted lens scores are 0..100, so band cuts are ×10 from the decile helper.
const scoreText = (v: number | null) =>
  v == null ? 'text-ink-tertiary' : v >= 80 ? 'text-signal-pos' : v >= 50 ? 'text-ink-secondary' : 'text-signal-neg'

const breadthText = (b: number | null) =>
  b == null ? 'text-ink-tertiary' : b >= 0.2 ? 'text-signal-pos' : b >= 0.1 ? 'text-teal' : 'text-ink-secondary'

const fmtScore = (v: number | null) => (v == null ? '—' : v.toFixed(0))
const fmtBreadth = (b: number | null) => (b == null ? '—' : `${(b * 100).toFixed(0)}%`)
const fmtExpense = (e: number | null) => (e == null ? '—' : `${e.toFixed(2)}%`) // already in percent units

type LensKey = 'v_tech' | 'v_fund' | 'v_cat' | 'v_flow' | 'v_val'

type SortKey =
  | 'name' | 'category' | 'amc' | 'n_holdings' | 'n_leaders' | 'breadth'
  | LensKey | 'expense'

type Col = { key: SortKey; label: string; align: 'left' | 'right' }
const COLS: Col[] = [
  { key: 'name', label: 'Name', align: 'left' },
  { key: 'category', label: 'Category', align: 'left' },
  { key: 'amc', label: 'AMC', align: 'left' },
  { key: 'n_holdings', label: 'Holdings', align: 'right' },
  { key: 'n_leaders', label: 'Leaders', align: 'right' },
  { key: 'breadth', label: 'Leadership-breadth', align: 'right' },
  { key: 'v_tech', label: 'Tch', align: 'right' },
  { key: 'v_fund', label: 'Fnd', align: 'right' },
  { key: 'v_cat', label: 'Cat', align: 'right' },
  { key: 'v_flow', label: 'Flw', align: 'right' },
  { key: 'v_val', label: 'Val', align: 'right' },
  { key: 'expense', label: 'Expense', align: 'right' },
]

// numeric value for a sort key; nulls sink to -Infinity so they sort last on desc.
function numFor(r: FundLensRow, key: SortKey): number {
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

export function FundLensTable({ funds }: { funds: FundLensRow[] }) {
  const router = useRouter()

  const [category, setCategory] = useState<string>('all')
  const [sortKey, setSortKey] = useState<SortKey>('breadth')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  const categories = useMemo(
    () => Array.from(new Set(funds.map(f => f.category).filter((x): x is string => !!x))).sort(),
    [funds],
  )

  const filtered = useMemo(
    () => (category === 'all' ? funds : funds.filter(f => f.category === category)),
    [funds, category],
  )

  const sorted = useMemo(() => {
    const sign = sortDir === 'desc' ? -1 : 1
    const out = [...filtered]
    out.sort((a, b) => {
      if (sortKey === 'name') return sign * a.name.localeCompare(b.name)
      if (sortKey === 'category') return sign * (a.category ?? '').localeCompare(b.category ?? '')
      if (sortKey === 'amc') return sign * (a.amc ?? '').localeCompare(b.amc ?? '')
      return sign * (numFor(a, sortKey) - numFor(b, sortKey))
    })
    return out
  }, [filtered, sortKey, sortDir])

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(d => (d === 'desc' ? 'asc' : 'desc'))
    else { setSortKey(key); setSortDir(key === 'expense' ? 'asc' : 'desc') }
  }

  const total = funds.length
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
          {shown} of {total} funds
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
            {sorted.map(f => (
              <tr
                key={f.mstar_id}
                onClick={() => router.push('/funds/' + f.mstar_id)}
                className="border-b border-paper-rule/50 cursor-pointer hover:bg-paper-soft"
              >
                <td className="py-1.5 px-2 font-sans text-[12px] font-medium text-ink-primary max-w-[260px] truncate">{f.name}</td>
                <td className="py-1.5 px-2 font-sans text-[11px] text-ink-secondary truncate max-w-[160px]">{f.category ?? '—'}</td>
                <td className="py-1.5 px-2 font-sans text-[11px] text-ink-secondary truncate max-w-[140px]">{f.amc ?? '—'}</td>
                <td className="py-1.5 px-2 text-right font-mono text-[12px] tabular-nums text-ink-secondary">{f.n_holdings}</td>
                <td className="py-1.5 px-2 text-right font-mono text-[12px] tabular-nums text-ink-secondary">{f.n_leaders}</td>
                <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums font-semibold ${breadthText(f.breadth)}`}>{fmtBreadth(f.breadth)}</td>
                <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${scoreText(f.v_tech)}`}>{fmtScore(f.v_tech)}</td>
                <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${scoreText(f.v_fund)}`}>{fmtScore(f.v_fund)}</td>
                <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${scoreText(f.v_cat)}`}>{fmtScore(f.v_cat)}</td>
                <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${scoreText(f.v_flow)}`}>{fmtScore(f.v_flow)}</td>
                <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${scoreText(f.v_val)}`}>{fmtScore(f.v_val)}</td>
                <td className="py-1.5 px-2 text-right font-mono text-[12px] tabular-nums text-ink-secondary">{fmtExpense(f.expense)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
