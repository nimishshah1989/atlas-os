'use client'
// src/components/themes/ThemeGrid.tsx — what a fund is actually ABOUT, and which of those things
// is working. Atlas India's sector-heatmap idiom (SectorHeatmapV4) over the theme taxonomy.
//
// The FM's ask, verbatim: "If there is something like an ETF which is focused on AI, then creating
// that artificial intelligence... it's not just energy, it's energy sources... funds around gold
// and silver miners... water and food security. Within the category there should be a rank: the
// right fund within that particular category."
//
// So each row is a theme, the heat is its members' MEDIAN strength against the S&P, and the row
// carries the leading fund by name so the answer to "how do I own this" is on the list page. The
// row navigates to the theme, where every fund carrying it is ranked against the others.
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { RsCell } from '@/components/countries/RsCell'
import { formatPct, formatUsd } from '@/lib/format'
import { THEME_WINDOWS, type ThemeList, type ThemeRow, type ThemeWindow } from '@/lib/themes'
import { decileColour } from '@/lib/scores'

const LABEL: Record<ThemeWindow, string> = { '3m': '3M', '6m': '6M', '12m': '1Y' }

type SortKey = 'name' | 'sector' | 'funds' | 'aum' | 'score' | 'breadth' | ThemeWindow

function sortValue(r: ThemeRow, key: SortKey): number | string | null {
  switch (key) {
    case 'name': return r.name
    case 'sector': return r.sector_name ?? ''
    case 'funds': return r.n_scored
    case 'aum': return r.aum_usd == null ? null : Number(r.aum_usd)
    case 'score': return r.median_composite == null ? null : Number(r.median_composite)
    case 'breadth': return r.above_ema200_frac == null ? null : Number(r.above_ema200_frac)
    default: return r.rs[key] == null ? null : Number(r.rs[key])
  }
}

function Row({ row }: { row: ThemeRow }) {
  const router = useRouter()
  const href = `/themes/${row.id}`
  const median = row.median_composite == null ? null : Number(row.median_composite)
  const top = row.top_composite == null ? null : Number(row.top_composite)
  return (
    <tr
      className="cursor-pointer border-t border-hair transition-colors hover:bg-raised"
      onClick={() => router.push(href)}
    >
      <td className="px-3 py-2 text-table">
        <Link href={href} className="font-medium text-ink" onClick={(e) => e.stopPropagation()}>
          {row.name}
        </Link>
        <span className="ml-2 text-meta text-ink-3">{row.sector_name ?? '—'}</span>
      </td>
      <td className="px-3 py-2 text-right text-table num text-ink-2">
        {row.n_scored}
        <span className="text-ink-3"> / {row.n_funds}</span>
      </td>
      <td className="px-3 py-2 text-right text-table num text-ink-2">
        {row.aum_usd ? formatUsd(row.aum_usd, 0) : '—'}
      </td>
      <td className="border-l border-rule px-3 py-2 text-right text-table num">
        {median == null ? <span className="text-ink-3">—</span> : <span className="font-semibold text-ink">{median.toFixed(0)}</span>}
      </td>
      <td className="px-3 py-2 text-right text-table num text-ink-2">
        {row.above_ema200_frac == null ? <span className="text-ink-3">—</span> : formatPct(row.above_ema200_frac, 0)}
      </td>
      <td className="border-l border-rule px-3 py-2 text-table">
        {row.top_symbol == null ? (
          <span className="text-meta text-ink-3">nothing scored yet</span>
        ) : (
          <>
            <span className="font-medium text-ink">{row.top_symbol}</span>
            {top != null && (
              <span className="ml-2 num text-table font-semibold" style={{ color: decileColour(row.top_decile) ?? undefined }}>
                {top.toFixed(0)}
              </span>
            )}
            <span className="ml-2 text-meta text-ink-3">{row.top_name}</span>
          </>
        )}
      </td>
      {THEME_WINDOWS.map((w, i) => (
        <RsCell key={w} value={row.rs[w]} first={i === 0} />
      ))}
    </tr>
  )
}

export function ThemeGrid({ list }: { list: ThemeList }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'funds', dir: -1 })
  if (list.rows.length === 0) {
    return (
      <p className="text-body text-ink-2">
        No fund carries a theme yet — run scripts/global_market/classify_etfs.py.
      </p>
    )
  }
  const onSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: (s.dir === 1 ? -1 : 1) as 1 | -1 } : { key, dir: key === 'name' || key === 'sector' ? 1 : -1 }))
  const arrow = (key: SortKey) => (sort.key === key ? (sort.dir === -1 ? ' ↓' : ' ↑') : '')
  const sorted = [...list.rows].sort((a, b) => {
    const av = sortValue(a, sort.key)
    const bv = sortValue(b, sort.key)
    if (av == null) return 1
    if (bv == null) return -1
    if (typeof av === 'string' || typeof bv === 'string') return String(av).localeCompare(String(bv)) * sort.dir
    return (av - bv) * sort.dir
  })

  const th = 'cursor-pointer select-none bg-raised px-3 py-1.5 text-meta font-semibold uppercase tracking-[0.1em] text-ink-3 hover:text-ink'
  const band = 'bg-raised px-3 py-1.5 text-left text-meta font-semibold uppercase tracking-[0.14em] text-ink-2'

  return (
    <div className="dt panel">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-hair">
            <th className="bg-raised" colSpan={3} />
            <th className={`${band} border-l border-rule`} colSpan={2}>Members</th>
            <th className={`${band} border-l border-rule`}>Strongest fund</th>
            <th className={`${band} border-l border-rule`} colSpan={THEME_WINDOWS.length}>Median vs S&amp;P 500</th>
          </tr>
          <tr className="border-b border-rule">
            <th className={`${th} text-left`} onClick={() => onSort('name')}>Theme{arrow('name')}</th>
            <th className={`${th} text-right`} onClick={() => onSort('funds')}>Funds{arrow('funds')}</th>
            <th className={`${th} text-right`} onClick={() => onSort('aum')}>AUM{arrow('aum')}</th>
            <th className={`${th} border-l border-rule text-right`} onClick={() => onSort('score')}>Median score{arrow('score')}</th>
            <th className={`${th} text-right`} onClick={() => onSort('breadth')} title="Share of measured members trading above their own 200-day EMA">
              Above 200d{arrow('breadth')}
            </th>
            <th className="border-l border-rule bg-raised px-3 py-1.5 text-left text-meta font-semibold uppercase tracking-[0.1em] text-ink-3">
              The one to own
            </th>
            {THEME_WINDOWS.map((w, i) => (
              <th key={w} className={`${th} text-right ${i === 0 ? 'border-l border-rule' : ''}`} onClick={() => onSort(w)}>
                {LABEL[w]}{arrow(w)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <Row key={r.id} row={r} />
          ))}
        </tbody>
      </table>
    </div>
  )
}
