'use client'

// EtfLensTable — the interactive ETF list table (client). Sortable on every column,
// plus a category <select> filter. Default sort = leadership-breadth desc (the headline,
// D26/D27). Presentational only — every value pre-coerced to number|null server-side.
import { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import type { EtfLensRow } from '@/lib/queries/v6/etf_lens'
import { decileColor } from '@/components/v4/ui/decile'
import { TermInfo } from '@/components/v6/shared/TermInfo'

// Morningstar prefixes every Indian ETF category with a redundant "India Fund " (so the
// filter read "India Fund Equity", "India Fund Large-Cap", …). Strip it for display — FM
// 2026-06-26. The underlying value keeps the full string so filtering is unaffected.
const cleanCat = (c: string | null): string =>
  (c ?? '—').replace(/^India\s+Fund\s*[-–—]?\s*/i, '').trim() || (c ?? '—')

// ── colour helpers (shared idioms with the stocks pages) ──────────────────
// Lens scores here are 0..100 (holdings-weighted); colour the figure with the shared
// perceptual ramp by mapping the score to its decile band (score/10), so a held lens
// reads on the same scale as the stock deciles. null → tertiary text token.
const scoreStyle = (v: number | null) =>
  ({ color: v == null ? 'var(--color-txt-3)' : decileColor(Math.round(v / 10)) })

const breadthText = (b: number | null) =>
  b == null ? 'text-txt-3' : b >= 0.1 ? 'text-sig-pos' : b >= 0.05 ? 'text-brand' : 'text-txt-2'

const fmtScore = (v: number | null) => (v == null ? '—' : v.toFixed(0))
const fmtBreadth = (b: number | null) => (b == null ? '—' : `${(b * 100).toFixed(0)}%`)
const fmtExpense = (e: number | null) => (e == null ? '—' : `${e.toFixed(2)}%`) // already in percent units

type LensKey = 'v_tech' | 'v_fund' | 'v_cat' | 'v_flow' | 'v_val'

type SortKey =
  | 'name' | 'category' | 'n_holdings' | 'n_leaders' | 'breadth'
  | LensKey | 'expense' | 'nse_ticker'

type Col = { key: SortKey; label: string; align: 'left' | 'right'; term?: string }
const COLS: Col[] = [
  { key: 'name', label: 'Name', align: 'left' },
  { key: 'category', label: 'Category', align: 'left' },
  { key: 'n_holdings', label: 'Holdings', align: 'right', term: 'holdings_count' },
  { key: 'n_leaders', label: 'Leaders', align: 'right', term: 'leaders_count' },
  { key: 'breadth', label: 'Leadership-breadth', align: 'right', term: 'leadership_breadth' },
  { key: 'v_tech', label: 'Tch', align: 'right', term: 'weighted_lens' },
  { key: 'v_fund', label: 'Fnd', align: 'right', term: 'weighted_lens' },
  { key: 'v_cat', label: 'Cat', align: 'right', term: 'weighted_lens' },
  { key: 'v_flow', label: 'Flw', align: 'right', term: 'weighted_lens' },
  { key: 'v_val', label: 'Val', align: 'right', term: 'weighted_lens' },
  { key: 'expense', label: 'Expense', align: 'right', term: 'expense' },
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

const CONTROL = 'font-sans text-[12px] bg-surface-raised border border-edge-rule rounded-tile px-2 py-1 text-txt-2'

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
      <div className="mb-4 flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1">
          <span className="font-sans text-[10px] uppercase tracking-wider text-txt-3">Category</span>
          <select className={CONTROL} value={category} onChange={e => setCategory(e.target.value)}>
            <option value="all">All</option>
            {categories.map(c => <option key={c} value={c}>{cleanCat(c)}</option>)}
          </select>
        </label>
        <span className="ml-auto self-end font-num text-[12px] tabular-nums text-txt-3">
          {shown} of {total} ETFs
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="tbl-centered w-full border-collapse">
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
            {sorted.map(e => (
              <tr
                key={e.fcode}
                onClick={() => router.push('/etfs/' + e.fcode)}
                className="cursor-pointer border-b border-edge-hair hover:bg-surface-raised"
              >
                {/* Real <Link> on the name so the row is navigable before hydration +
                    keyboard/middle-click accessible (the row onClick is a convenience). */}
                <td className="max-w-[260px] truncate px-2 py-1.5 font-sans text-[12px] font-medium">
                  <Link href={`/etfs/${e.fcode}`} className="text-txt-1 no-underline hover:text-brand hover:underline">{e.name}</Link>
                </td>
                <td className="max-w-[160px] truncate px-2 py-1.5 font-sans text-[11px] text-txt-2">{cleanCat(e.category)}</td>
                <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums text-txt-2">{e.n_holdings}</td>
                <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums text-txt-2">{e.n_leaders}</td>
                <td className={`px-2 py-1.5 text-right font-num text-[12px] font-semibold tabular-nums ${breadthText(e.breadth)}`}>{fmtBreadth(e.breadth)}</td>
                <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums" style={scoreStyle(e.v_tech)}>{fmtScore(e.v_tech)}</td>
                <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums" style={scoreStyle(e.v_fund)}>{fmtScore(e.v_fund)}</td>
                <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums" style={scoreStyle(e.v_cat)}>{fmtScore(e.v_cat)}</td>
                <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums" style={scoreStyle(e.v_flow)}>{fmtScore(e.v_flow)}</td>
                <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums" style={scoreStyle(e.v_val)}>{fmtScore(e.v_val)}</td>
                <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums text-txt-2">{fmtExpense(e.expense)}</td>
                <td className="whitespace-nowrap px-2 py-1.5 font-num text-[10px] text-txt-3">
                  {e.nse_ticker ? <span className="rounded-tile border border-edge-rule bg-surface-inset px-1.5 py-0.5">{e.nse_ticker}</span> : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
