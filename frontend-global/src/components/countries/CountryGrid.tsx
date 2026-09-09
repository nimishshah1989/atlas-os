// src/components/countries/CountryGrid.tsx — one row per market, grouped by region.
//
// The row IS the answer to "how do I get exposure to this country": the fund you would buy, how
// liquid it is, how many alternatives exist, and how the market has done against the S&P over six
// windows — and, since P2-E, where it RANKS among every market that carries a score.
//
// The rank column is the FM's decision D2 of 2026-09-09: Atlas already ranks by composite into
// deciles within a cohort, and countries get the same treatment rather than a second mechanism.
// A market with no scored fund shows no rank at all — not a last place, which would read as a
// verdict on something nobody measured.
import { DecileChip } from '@/components/ui/DecileChip'
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
      {/* Rank first: it is the column the page exists to show. Ties share a rank, and an
          unscored market is blank rather than being sorted to the bottom. */}
      <td className="px-3 py-2 text-right text-table num text-ink-2">
        {row.rank == null ? <span className="text-ink-3">—</span> : row.rank}
      </td>
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
      <td className="px-3 py-2 text-right text-table num text-ink">
        {row.composite == null ? (
          <span className="text-ink-3">—</span>
        ) : (
          <span className="inline-flex items-center gap-2">
            {Number(row.composite).toFixed(0)}
            <DecileChip decile={row.decile} />
          </span>
        )}
      </td>
      <td className="px-3 py-2 text-right text-table num text-ink-2">
        {row.breadth_pct == null ? (
          <span className="text-ink-3">—</span>
        ) : (
          `${Number(row.breadth_pct).toFixed(0)}%`
        )}
      </td>
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
            <th className="px-3 py-2 text-right font-medium">#</th>
            <th className="px-3 py-2 text-left font-medium">Market</th>
            <th className="px-3 py-2 text-left font-medium">Fund you would buy</th>
            <th className="px-3 py-2 text-right font-medium">Traded / day</th>
            <th className="px-3 py-2 text-right font-medium">Funds</th>
            <th className="px-3 py-2 text-right font-medium">Score</th>
            <th className="px-3 py-2 text-right font-medium">Breadth</th>
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
                colSpan={7 + RS_WINDOWS.length}
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
