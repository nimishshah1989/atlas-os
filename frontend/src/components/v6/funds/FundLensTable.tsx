'use client'

// FundLensTable — the interactive fund list table (client). Sortable on every column,
// plus a category <select> filter. Default sort = leadership-breadth desc (the headline,
// D26/D27); expense sorts cheapest-first. Mirrors EtfLensTable. Presentational only —
// every value pre-coerced to number|null server-side.
import { Fragment, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import type { FundLensRow } from '@/lib/queries/v6/fund_lens'
import { fundCompositeContributions } from '@/lib/v6/fundScore'
import { TermInfo } from '@/components/v6/shared/TermInfo'

// ── colour helpers (shared idioms with the stocks / ETF pages) ────────────
// Weighted lens scores are 0..100, so band cuts are ×10 from the decile helper.
const scoreText = (v: number | null) =>
  v == null ? 'text-txt-3' : v >= 80 ? 'text-sig-pos' : v >= 50 ? 'text-txt-2' : 'text-sig-neg'

const breadthText = (b: number | null) =>
  b == null ? 'text-txt-3' : b >= 0.2 ? 'text-sig-pos' : b >= 0.1 ? 'text-brand' : 'text-txt-2'

// Fund composite score (0–100): derived from the holdings-weighted lens blend (fundScore.ts).
const compositeText = (v: number | null) =>
  v == null ? 'text-txt-3' : v >= 60 ? 'text-sig-pos' : v >= 45 ? 'text-brand' : 'text-sig-neg'

const fmtScore = (v: number | null) => (v == null ? '—' : v.toFixed(0))
const fmtBreadth = (b: number | null) => (b == null ? '—' : `${(b * 100).toFixed(0)}%`)
const fmtExpense = (e: number | null) => (e == null ? '—' : `${e.toFixed(2)}%`) // already in percent units
const fmtAum = (a: number | null) => (a == null ? '—' : a.toLocaleString('en-IN', { maximumFractionDigits: 0 }))

// Morningstar prefixes every Indian fund category with a redundant "India Fund " (so the filter
// read "India Fund Multi-Cap", …). Strip it for display only — filtering still uses the raw value.
const cleanCat = (c: string | null): string =>
  (c ?? '—').replace(/^India\s+Fund\s*[-–—]?\s*/i, '').trim() || (c ?? '—')

// AUM size buckets (₹ crore) for the screener filter.
const AUM_BUCKETS: { key: string; label: string; test: (a: number | null) => boolean }[] = [
  { key: 'all', label: 'All sizes', test: () => true },
  { key: 'lg', label: '> ₹10,000 Cr', test: a => a != null && a > 10000 },
  { key: 'md', label: '₹1,000–10,000 Cr', test: a => a != null && a >= 1000 && a <= 10000 },
  { key: 'sm', label: '< ₹1,000 Cr', test: a => a != null && a < 1000 },
]

type LensKey = 'v_tech' | 'v_fund' | 'v_cat' | 'v_flow' | 'v_val'

type SortKey =
  | 'name' | 'category' | 'amc' | 'n_holdings' | 'n_leaders' | 'breadth'
  | LensKey | 'expense' | 'composite' | 'cat_rank' | 'aum_cr'

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
  { key: 'aum_cr', label: 'AUM (Cr)', align: 'right', term: 'fund_aum' },
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
    case 'aum_cr': return r.aum_cr ?? -Infinity
    case 'expense': return r.expense ?? Infinity // cheaper sorts "better" on asc
    default: return 0
  }
}

const CONTROL = 'font-sans text-[12px] bg-surface-raised border border-edge-rule rounded-tile px-2 py-1 text-txt-2'

export function FundLensTable({ funds }: { funds: FundLensRow[] }) {
  const router = useRouter()

  const [category, setCategory] = useState<string>('all')
  const [aumBucket, setAumBucket] = useState<string>('all')
  const [sortKey, setSortKey] = useState<SortKey>('breadth')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [openId, setOpenId] = useState<string | null>(null) // row whose score derivation is expanded

  // Raw category values drive filtering; cleanCat() only relabels for display.
  const categories = useMemo(
    () => Array.from(new Set(funds.map(f => f.category).filter((x): x is string => !!x))).sort(),
    [funds],
  )

  const filtered = useMemo(() => {
    const bucket = AUM_BUCKETS.find(b => b.key === aumBucket) ?? AUM_BUCKETS[0]
    return funds.filter(f => (category === 'all' || f.category === category) && bucket.test(f.aum_cr))
  }, [funds, category, aumBucket])

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
            {categories.map(c => <option key={c} value={c}>{cleanCat(c)}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-sans text-[10px] uppercase tracking-wider text-txt-3">AUM</span>
          <select className={CONTROL} value={aumBucket} onChange={e => setAumBucket(e.target.value)}>
            {AUM_BUCKETS.map(b => <option key={b.key} value={b.key}>{b.label}</option>)}
          </select>
        </label>
        <span className="ml-auto self-end font-num text-[12px] tabular-nums text-txt-3">
          {shown} of {total} funds · {category === 'all'
            ? `ranked within ${categories.length} SEBI categories`
            : `ranked within ${cleanCat(category)}`}
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
            {sorted.map(f => {
              const isOpen = openId === f.mstar_id
              const contribs = f.composite != null ? fundCompositeContributions(f) : []
              return (
              <Fragment key={f.mstar_id}>
              <tr
                onClick={() => router.push('/funds/' + f.mstar_id)}
                className="cursor-pointer border-b border-edge-hair hover:bg-surface-raised"
              >
                <td className="max-w-[260px] truncate px-2 py-1.5 font-sans text-[12px] font-medium text-txt-1">{f.name}</td>
                <td className="max-w-[160px] truncate px-2 py-1.5 font-sans text-[11px] text-txt-2">{cleanCat(f.category)}</td>
                <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums text-txt-2">
                  {f.cat_rank != null ? <><span className="font-semibold text-txt-1">{f.cat_rank}</span><span className="text-txt-3">/{f.cat_size}</span></> : '—'}
                </td>
                <td className={`px-2 py-1.5 text-right font-num text-[12px] tabular-nums font-semibold ${compositeText(f.composite)}`}>
                  <button
                    type="button"
                    onClick={e => { e.stopPropagation(); setOpenId(isOpen ? null : f.mstar_id) }}
                    className="inline-flex items-center gap-1 hover:text-txt-1"
                    title="How the score is built"
                  >
                    {f.composite != null && <span className="font-num text-[9px] text-txt-3">{isOpen ? '▾' : '▸'}</span>}
                    {fmtScore(f.composite)}
                  </button>
                </td>
                <td className="max-w-[140px] truncate px-2 py-1.5 font-sans text-[11px] text-txt-2">{f.amc ?? '—'}</td>
                <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums text-txt-2">{f.n_holdings}</td>
                <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums text-txt-2">{f.n_leaders}</td>
                <td className={`px-2 py-1.5 text-right font-num text-[12px] tabular-nums font-semibold ${breadthText(f.breadth)}`}>{fmtBreadth(f.breadth)}</td>
                <td className={`px-2 py-1.5 text-right font-num text-[12px] tabular-nums ${scoreText(f.v_tech)}`}>{fmtScore(f.v_tech)}</td>
                <td className={`px-2 py-1.5 text-right font-num text-[12px] tabular-nums ${scoreText(f.v_fund)}`}>{fmtScore(f.v_fund)}</td>
                <td className={`px-2 py-1.5 text-right font-num text-[12px] tabular-nums ${scoreText(f.v_cat)}`}>{fmtScore(f.v_cat)}</td>
                <td className={`px-2 py-1.5 text-right font-num text-[12px] tabular-nums ${scoreText(f.v_flow)}`}>{fmtScore(f.v_flow)}</td>
                <td className={`px-2 py-1.5 text-right font-num text-[12px] tabular-nums ${scoreText(f.v_val)}`}>{fmtScore(f.v_val)}</td>
                <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums text-txt-2">{fmtAum(f.aum_cr)}</td>
                <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums text-txt-2">{fmtExpense(f.expense)}</td>
              </tr>
              {isOpen && contribs.length > 0 && (
                <tr className="border-b border-edge-hair bg-surface-raised/50">
                  <td colSpan={COLS.length} className="px-4 py-3">
                    <div className="font-sans text-[11px] text-txt-2">
                      <div className="mb-1.5 text-[10px] uppercase tracking-wider text-txt-3">
                        How the score is built<TermInfo term="fund_score" />
                      </div>
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 font-num tabular-nums">
                        {contribs.map((c, i) => (
                          <span key={c.key} className="whitespace-nowrap">
                            {i > 0 && <span className="text-txt-3">+ </span>}
                            <span className="text-txt-3">{c.short} </span>
                            <span className={scoreText(c.score)}>{fmtScore(c.score)}</span>
                            <span className="text-txt-3"> ×{c.weight.toFixed(2)}</span>
                          </span>
                        ))}
                        <span className="text-txt-3">=</span>
                        <span className={`font-semibold ${compositeText(f.composite)}`}>{fmtScore(f.composite)}</span>
                      </div>
                      <div className="mt-1.5 text-[10px] text-txt-3">
                        Each lens is the holdings-weighted average of the fund’s constituents; the composite weights them
                        0.30 / 0.25 / 0.25 / 0.20 (Tch / Fnd / Flw / Cat). Valuation is context, not scored. Weights
                        renormalise over the lenses present.
                      </div>
                    </div>
                  </td>
                </tr>
              )}
              </Fragment>
            )})}
          </tbody>
        </table>
      </div>
    </div>
  )
}
