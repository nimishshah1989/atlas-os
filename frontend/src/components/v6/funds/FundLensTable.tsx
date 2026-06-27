'use client'

// FundLensTable — the interactive fund list table (client). Sortable on every column,
// plus a category <select> filter. Default sort = leadership-breadth desc (the headline,
// D26/D27); expense sorts cheapest-first. Mirrors EtfLensTable. Presentational only —
// every value pre-coerced to number|null server-side.
import { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import type { FundLensRow } from '@/lib/queries/v6/fund_lens'
import { TermInfo } from '@/components/v6/shared/TermInfo'

// ── colour helpers (shared idioms with the stocks / ETF pages) ────────────
// Weighted lens scores are 0..100, so band cuts are ×10 from the decile helper.
const scoreText = (v: number | null) =>
  v == null ? 'text-txt-3' : v >= 80 ? 'text-sig-pos' : v >= 50 ? 'text-txt-2' : 'text-sig-neg'

const breadthText = (b: number | null) =>
  b == null ? 'text-txt-3' : b >= 0.2 ? 'text-sig-pos' : b >= 0.1 ? 'text-brand' : 'text-txt-2'

// Fund composite score (0–100, from the scorecard): green strong / brand decent / red weak.
const compositeText = (v: number | null) =>
  v == null ? 'text-txt-3' : v >= 60 ? 'text-sig-pos' : v >= 45 ? 'text-brand' : 'text-sig-neg'

const fmtScore = (v: number | null) => (v == null ? '—' : v.toFixed(0))
const fmtBreadth = (b: number | null) => (b == null ? '—' : `${(b * 100).toFixed(0)}%`)
const fmtExpense = (e: number | null) => (e == null ? '—' : `${e.toFixed(2)}%`) // already in percent units

type LensKey = 'v_tech' | 'v_fund' | 'v_cat' | 'v_flow' | 'v_val'

type SortKey =
  | 'name' | 'category' | 'amc' | 'n_holdings' | 'n_leaders' | 'breadth'
  | LensKey | 'expense' | 'composite' | 'cat_rank'

type Col = { key: SortKey; label: string; align: 'left' | 'right'; term?: string }
const COLS: Col[] = [
  { key: 'name', label: 'Name', align: 'left' },
  { key: 'category', label: 'Category', align: 'left' },
  { key: 'cat_rank', label: 'Cat rank', align: 'right', term: 'cat_rank' },
  { key: 'composite', label: 'Score', align: 'right', term: 'fund_score' },
  { key: 'amc', label: 'AMC', align: 'left' },
  { key: 'n_holdings', label: 'Holdings', align: 'right', term: 'holdings_count' },
  { key: 'n_leaders', label: 'Leaders', align: 'right', term: 'leaders_count' },
  { key: 'breadth', label: 'Leadership-breadth', align: 'right', term: 'leadership_breadth' },
  { key: 'v_tech', label: 'Tch', align: 'right', term: 'weighted_lens' },
  { key: 'v_fund', label: 'Fnd', align: 'right', term: 'weighted_lens' },
  { key: 'v_cat', label: 'Cat', align: 'right', term: 'weighted_lens' },
  { key: 'v_flow', label: 'Flw', align: 'right', term: 'weighted_lens' },
  { key: 'v_val', label: 'Val', align: 'right', term: 'weighted_lens' },
  { key: 'expense', label: 'Expense', align: 'right', term: 'expense' },
]

// numeric value for a sort key; nulls sink to -Infinity so they sort last on desc.
function numFor(r: FundLensRow, key: SortKey): number {
  switch (key) {
    case 'n_holdings': return r.n_holdings
    case 'n_leaders': return r.n_leaders
    case 'composite': return r.composite ?? -Infinity
    case 'cat_rank': return r.cat_rank ?? Infinity // rank 1 is best → nulls sink last on asc
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

const CONTROL = 'font-sans text-[12px] bg-surface-raised border border-edge-rule rounded-tile px-2 py-1 text-txt-2'

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
    else { setSortKey(key); setSortDir(key === 'expense' || key === 'cat_rank' ? 'asc' : 'desc') }
  }

  const total = funds.length
  const shown = sorted.length

  return (
    <div>
      {/* control row */}
      <div className="mb-4 flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1">
          <span className="font-sans text-[10px] uppercase tracking-wider text-txt-3">Category</span>
          <select className={CONTROL} value={category} onChange={e => setCategory(e.target.value)}>
            <option value="all">All</option>
            {categories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <span className="ml-auto self-end font-num text-[12px] tabular-nums text-txt-3">
          {shown} of {total} funds
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-edge-rule">
              {COLS.map(col => {
                const isSorted = sortKey === col.key
                const arrow = isSorted ? (sortDir === 'desc' ? ' ▼' : ' ▲') : ''
                return (
                  <th
                    key={col.key}
                    onClick={() => toggleSort(col.key)}
                    className={`font-sans text-[10px] uppercase tracking-wider pb-2 px-2 cursor-pointer select-none whitespace-nowrap ${
                      col.align === 'right' ? 'text-right' : 'text-left'
                    } ${isSorted ? 'text-txt-1 font-semibold' : 'text-txt-3'} hover:text-txt-2`}
                  >
                    {col.label}{col.term && <TermInfo term={col.term} />}{arrow}
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
                className="cursor-pointer border-b border-edge-hair hover:bg-surface-raised"
              >
                <td className="max-w-[260px] truncate px-2 py-1.5 font-sans text-[12px] font-medium text-txt-1">{f.name}</td>
                <td className="max-w-[160px] truncate px-2 py-1.5 font-sans text-[11px] text-txt-2">{f.category ?? '—'}</td>
                <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums text-txt-2">
                  {f.cat_rank != null ? <><span className="font-semibold text-txt-1">{f.cat_rank}</span><span className="text-txt-3">/{f.cat_size}</span></> : '—'}
                </td>
                <td className={`px-2 py-1.5 text-right font-num text-[12px] tabular-nums font-semibold ${compositeText(f.composite)}`}>{fmtScore(f.composite)}</td>
                <td className="max-w-[140px] truncate px-2 py-1.5 font-sans text-[11px] text-txt-2">{f.amc ?? '—'}</td>
                <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums text-txt-2">{f.n_holdings}</td>
                <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums text-txt-2">{f.n_leaders}</td>
                <td className={`px-2 py-1.5 text-right font-num text-[12px] tabular-nums font-semibold ${breadthText(f.breadth)}`}>{fmtBreadth(f.breadth)}</td>
                <td className={`px-2 py-1.5 text-right font-num text-[12px] tabular-nums ${scoreText(f.v_tech)}`}>{fmtScore(f.v_tech)}</td>
                <td className={`px-2 py-1.5 text-right font-num text-[12px] tabular-nums ${scoreText(f.v_fund)}`}>{fmtScore(f.v_fund)}</td>
                <td className={`px-2 py-1.5 text-right font-num text-[12px] tabular-nums ${scoreText(f.v_cat)}`}>{fmtScore(f.v_cat)}</td>
                <td className={`px-2 py-1.5 text-right font-num text-[12px] tabular-nums ${scoreText(f.v_flow)}`}>{fmtScore(f.v_flow)}</td>
                <td className={`px-2 py-1.5 text-right font-num text-[12px] tabular-nums ${scoreText(f.v_val)}`}>{fmtScore(f.v_val)}</td>
                <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums text-txt-2">{fmtExpense(f.expense)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
