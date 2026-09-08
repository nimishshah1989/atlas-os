// src/components/countries/CountryGrid.tsx — one row per market, grouped by region.
//
// The row IS the answer to "how do I get exposure to this country": the fund you would buy, how
// liquid it is, how many alternatives exist, and how the market has done against the S&P over six
// windows. Nothing here is a score — Phase 3 has not happened — so the grid does not pretend to
// rank countries. It shows what is measured and lets the reader rank.
import { formatUsd } from '@/lib/format'
import type { CountryList, CountryRow } from '@/lib/queries/countries'
import { RS_WINDOWS } from '@/lib/queries/countries'
import { RsCell } from './RsCell'

const REGION_NAMES: Record<string, string> = {
  north_america: 'North America',
  europe: 'Europe',
  asia_pacific: 'Asia Pacific',
  latam: 'Latin America',
  mea: 'Middle East & Africa',
}

/** Rows in the order the query returned them, split into their region blocks. */
function byRegion(rows: CountryRow[]): [string, CountryRow[]][] {
  const groups = new Map<string, CountryRow[]>()
  for (const row of rows) {
    const key = row.region ?? 'other'
    const bucket = groups.get(key)
    if (bucket) bucket.push(row)
    else groups.set(key, [row])
  }
  return [...groups.entries()]
}

function Row({ row }: { row: CountryRow }) {
  return (
    <tr className="border-t border-hair">
      <td className="px-3 py-2 text-table text-ink">
        <span className="font-medium">{row.name}</span>
        <span className="ml-2 text-meta text-ink-3">{row.iso2}</span>
      </td>
      <td className="px-3 py-2 text-table">
        {row.symbol ? (
          <>
            <span className="font-medium text-ink">{row.symbol}</span>
            <span className="ml-2 text-meta text-ink-3">{row.fund_name}</span>
          </>
        ) : (
          // Not an error and not a gap in the data: every fund covering this market is geared,
          // inverse or currency-hedged, so none of them is the thing "buy this country" means.
          <span className="text-ink-3">
            no plain fund — every one is geared, inverse or currency-hedged
          </span>
        )}
      </td>
      <td className="px-3 py-2 text-right text-table tabular-nums text-ink-2">
        {row.adv_usd_60d_median ? formatUsd(row.adv_usd_60d_median, 0) : '—'}
      </td>
      <td className="px-3 py-2 text-right text-table tabular-nums text-ink-2">{row.n_etfs}</td>
      {RS_WINDOWS.map((w) => (
        <RsCell key={w} value={row.rs[w]} />
      ))}
    </tr>
  )
}

export function CountryGrid({ list }: { list: CountryList }) {
  if (list.rows.length === 0) {
    return (
      <p className="panel px-4 py-3 text-body text-ink-2">
        No country rows yet. Run{' '}
        <code className="text-ink">scripts/global_market/build_country_views.py</code> — it reads
        the technicals journal and writes one row per market.
      </p>
    )
  }
  return (
    <div className="panel overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="text-meta text-ink-3">
            <th className="px-3 py-2 text-left font-medium">Market</th>
            <th className="px-3 py-2 text-left font-medium">Fund you would buy</th>
            <th className="px-3 py-2 text-right font-medium">Traded / day</th>
            <th className="px-3 py-2 text-right font-medium">Funds</th>
            {RS_WINDOWS.map((w) => (
              <th key={w} className="px-3 py-2 text-right font-medium">
                {w}
              </th>
            ))}
          </tr>
        </thead>
        {byRegion(list.rows).map(([region, rows]) => (
          <tbody key={region}>
            <tr>
              <th
                colSpan={4 + RS_WINDOWS.length}
                className="bg-raised px-3 py-1.5 text-left text-meta font-medium text-ink-2"
              >
                {REGION_NAMES[region] ?? region}
              </th>
            </tr>
            {rows.map((row) => (
              <Row key={row.iso2} row={row} />
            ))}
          </tbody>
        ))}
      </table>
    </div>
  )
}
