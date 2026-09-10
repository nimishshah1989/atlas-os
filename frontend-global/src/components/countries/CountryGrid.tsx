'use client'
// src/components/countries/CountryGrid.tsx — the country matrix, in Atlas India's heatmap idiom
// (frontend/src/components/sectors/SectorHeatmapV4.tsx): two grouped column bands, heat carrying
// the shape of a row, the number always printed, click-sortable, and EVERY ROW A DOOR.
//
// It used to be a static list nobody could click. The FM, on seeing it: "none of this is
// clickable... the tables can be so much cleaner, so much better, more like cards. There's proper
// red, amber, and green representation, and we should be able to click into the country page."
// So: the whole row navigates to /countries/[iso2], the country name is a real <Link> underneath
// it for keyboard and middle-click, and the score is drawn on the same D1→D10 ramp every other
// Atlas surface uses.
//
// The rank column comes first because it is the column the page exists to show. A market with no
// scored fund has NO rank rather than a last place, which would read as a verdict on something
// nobody measured (the FM's decision D2 of 2026-09-09).
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { DecileMeter } from '@/components/ui/DecileMeter'
import { formatUsd } from '@/lib/format'
import type { CountryList, CountryRow, RsWindow } from '@/lib/countries'
import { RS_WINDOWS } from '@/lib/countries'
import { decileColour } from '@/lib/scores'
import { whyNotOffered } from '@/lib/universe'
import { RsCell } from './RsCell'

const REGION_NAMES: Record<string, string> = {
  north_america: 'North America',
  europe: 'Europe',
  asia_pacific: 'Asia Pacific',
  latam: 'Latin America',
  mea: 'Middle East & Africa',
}

const WINDOW_LABEL: Record<RsWindow, string> = {
  '1w': '1W', '1m': '1M', '3m': '3M', '6m': '6M', '12m': '1Y', '24m': '2Y',
}

type SortKey = 'rank' | 'name' | 'adv' | 'funds' | 'breadth' | RsWindow

/** What each column sorts on. Null always sinks, whichever way the arrow points. */
function sortValue(r: CountryRow, key: SortKey): number | string | null {
  if (key === 'name') return r.name
  if (key === 'rank') return r.composite == null ? null : Number(r.composite)
  if (key === 'adv') return r.adv_usd_60d_median == null ? null : Number(r.adv_usd_60d_median)
  if (key === 'funds') return r.n_etfs
  if (key === 'breadth') return r.breadth_pct == null ? null : Number(r.breadth_pct)
  return r.rs[key] == null ? null : Number(r.rs[key])
}

function Row({ row }: { row: CountryRow }) {
  const router = useRouter()
  const href = `/countries/${row.iso2.toLowerCase()}`
  const composite = row.composite == null ? null : Number(row.composite)
  const breadth = row.breadth_pct == null ? null : Number(row.breadth_pct)
  return (
    <tr
      className="cursor-pointer border-t border-hair transition-colors hover:bg-raised"
      onClick={() => router.push(href)}
    >
      <td className="px-3 py-2 text-right text-table num text-ink-2">
        {row.rank == null ? <span className="text-ink-3">—</span> : row.rank}
      </td>
      <td className="px-3 py-2 text-table">
        {/* the real link under the row click: keyboard, middle-click, and "copy link address" */}
        <Link href={href} className="font-medium text-ink" onClick={(e) => e.stopPropagation()}>
          {row.name}
        </Link>
        <span className="ml-2 text-meta text-ink-3">{row.iso2}</span>
      </td>
      <td className="px-3 py-2 text-table">
        {row.symbol ? (
          <>
            <span className="font-medium text-ink">{row.symbol}</span>
            <span className="ml-2 text-meta text-ink-3">{row.fund_name}</span>
            {whyNotOffered(row.exclusion_reason) && (
              <span className="ml-2 text-meta text-neg">{whyNotOffered(row.exclusion_reason)}</span>
            )}
          </>
        ) : (
          // Not a gap in the data: every fund covering this market is geared, inverse or
          // currency-hedged, so none of them is the thing "buy this country" means.
          <span className="text-meta text-ink-3">geared / hedged only</span>
        )}
      </td>
      <td className="px-3 py-2 text-right text-table num text-ink-2">
        {row.adv_usd_60d_median ? formatUsd(row.adv_usd_60d_median, 0) : '—'}
      </td>
      <td className="px-3 py-2 text-right text-table num text-ink-2">{row.n_etfs}</td>
      {/* THE SCORE BAND. Colour is the second channel: the figure is printed in every cell. */}
      <td className="border-l border-rule px-3 py-2 text-right text-table num">
        {composite == null ? (
          <span className="text-ink-3">—</span>
        ) : (
          <span className="font-semibold" style={{ color: decileColour(row.decile) ?? undefined }}>
            {composite.toFixed(0)}
          </span>
        )}
      </td>
      <td className="px-2 py-2">
        <DecileMeter decile={row.decile} title={row.rank == null ? undefined : `Ranked ${row.rank} of ${row.n_ranked} scored markets`} />
      </td>
      <td className="px-3 py-2 text-right text-table num text-ink-2">
        {breadth == null ? <span className="text-ink-3">—</span> : `${breadth.toFixed(0)}%`}
      </td>
      {RS_WINDOWS.map((w, i) => (
        <RsCell key={w} value={row.rs[w]} first={i === 0} />
      ))}
    </tr>
  )
}

export function CountryGrid({ list }: { list: CountryList }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'rank', dir: -1 })
  if (list.rows.length === 0) {
    return <p className="text-body text-ink-2">No market has a fund on this session yet.</p>
  }

  const onSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: (s.dir === 1 ? -1 : 1) as 1 | -1 } : { key, dir: key === 'name' ? 1 : -1 }))
  const arrow = (key: SortKey) => (sort.key === key ? (sort.dir === -1 ? ' ↓' : ' ↑') : '')

  // Regions stay together while the default rank sort is in force — it is how the FM reads the
  // world. Sort by any column and the grouping drops away, because a global ordering split into
  // five blocks is not an ordering.
  const grouped = sort.key === 'rank' && sort.dir === -1
  const cmp = (a: CountryRow, b: CountryRow) => {
    const av = sortValue(a, sort.key)
    const bv = sortValue(b, sort.key)
    if (av == null) return 1
    if (bv == null) return -1
    if (typeof av === 'string' || typeof bv === 'string') return String(av).localeCompare(String(bv)) * sort.dir
    return (av - bv) * sort.dir
  }
  const sorted = [...list.rows].sort(cmp)
  const blocks: [string | null, CountryRow[]][] = grouped
    ? [...sorted.reduce((m, r) => {
        const k = r.region ?? 'other'
        m.set(k, [...(m.get(k) ?? []), r])
        return m
      }, new Map<string, CountryRow[]>())].map(([k, rs]) => [k, rs])
    : [[null, sorted]]

  const th = 'cursor-pointer select-none bg-raised px-3 py-1.5 text-meta font-semibold uppercase tracking-[0.1em] text-ink-3 hover:text-ink'
  const band = 'bg-raised px-3 py-1.5 text-left text-meta font-semibold uppercase tracking-[0.14em] text-ink-2'

  return (
    <div className="dt panel">
      <table className="w-full border-collapse">
        <thead>
          {/* the two bands: what the market IS worth, and what it DID against the American default */}
          <tr className="border-b border-hair">
            <th className="bg-raised" colSpan={5} />
            <th className={`${band} border-l border-rule`} colSpan={3}>Score</th>
            <th className={`${band} border-l border-rule`} colSpan={RS_WINDOWS.length}>vs S&amp;P 500</th>
          </tr>
          <tr className="border-b border-rule">
            <th className={`${th} text-right`} onClick={() => onSort('rank')}>#{arrow('rank')}</th>
            <th className={`${th} text-left`} onClick={() => onSort('name')}>Market{arrow('name')}</th>
            <th className="bg-raised px-3 py-1.5 text-left text-meta font-semibold uppercase tracking-[0.1em] text-ink-3">The fund you would buy</th>
            <th className={`${th} text-right`} onClick={() => onSort('adv')}>ADV ${arrow('adv')}</th>
            <th className={`${th} text-right`} onClick={() => onSort('funds')}>Funds{arrow('funds')}</th>
            <th className={`${th} border-l border-rule text-right`} onClick={() => onSort('rank')}>Score{arrow('rank')}</th>
            <th className="bg-raised px-2 py-1.5 text-left text-meta font-semibold uppercase tracking-[0.1em] text-ink-3">Decile</th>
            <th className={`${th} text-right`} onClick={() => onSort('breadth')}>Breadth{arrow('breadth')}</th>
            {RS_WINDOWS.map((w, i) => (
              <th key={w} className={`${th} text-right ${i === 0 ? 'border-l border-rule' : ''}`} onClick={() => onSort(w)}>
                {WINDOW_LABEL[w]}{arrow(w)}
              </th>
            ))}
          </tr>
        </thead>
        {blocks.map(([region, rows]) => (
          <tbody key={region ?? 'all'}>
            {region && (
              <tr>
                <td colSpan={8 + RS_WINDOWS.length} className="border-t border-rule bg-inset/60 px-3 py-1 text-meta font-semibold uppercase tracking-[0.12em] text-ink-2">
                  {REGION_NAMES[region] ?? region}
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <Row key={r.iso2} row={r} />
            ))}
          </tbody>
        ))}
      </table>
    </div>
  )
}
