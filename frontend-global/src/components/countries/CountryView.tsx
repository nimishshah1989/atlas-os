// src/components/countries/CountryView.tsx — one market's page: what it scored, the fund that
// stands for it, ten years of that fund's price, and every alternative ranked beneath it.
//
// A MARKET HAS NO PRICE OF ITS OWN. There is no index in atlas_global for Japan; there is a fund
// that tracks Japan. So the chart, the relative strength and the score on this page are all the
// REPRESENTATIVE fund's, and the page says so once rather than implying an index behind them.
// The representative is the most-traded fund covering the market that is not geared, inverse or
// currency-hedged — build_country_views.py's choice, read back here, never re-decided.
import Link from 'next/link'
import { PriceSection } from '@/components/entity/PriceSection'
import { DecileMeter } from '@/components/ui/DecileMeter'
import { EodStamp } from '@/components/ui/EodStamp'
import { PageHeader } from '@/components/ui/PageHeader'
import { Section } from '@/components/ui/Section'
import { StatCard } from '@/components/ui/StatCard'
import { formatUsd } from '@/lib/format'
import { RS_WINDOWS, type CountryDetail, type RsWindow } from '@/lib/countries'
import { decileColour } from '@/lib/scores'
import type { InstrumentSeries } from '@/lib/queries/series'
import { CountryFundTable } from './CountryFundTable'
import { RsCell } from './RsCell'

const REGION_NAMES: Record<string, string> = {
  north_america: 'North America',
  europe: 'Europe',
  asia_pacific: 'Asia Pacific',
  latam: 'Latin America',
  mea: 'Middle East & Africa',
}

const WINDOW_LABEL: Record<RsWindow, string> = {
  '1w': '1 week', '1m': '1 month', '3m': '3 months', '6m': '6 months', '12m': '1 year', '24m': '2 years',
}

const num = (v: string | null) => (v == null ? null : Number(v))

export function CountryView({ detail, series }: { detail: CountryDetail; series: InstrumentSeries }) {
  const { row, funds, date } = detail
  const composite = num(row.composite)
  const breadth = num(row.breadth_pct)
  const scored = funds.filter((f) => f.rank != null).length

  return (
    <div className="page">
      <PageHeader
        title={row.name}
        lead={
          row.symbol ? (
            <>
              Everything below is <Link href={`/etfs/${encodeURIComponent(row.symbol)}`}>{row.symbol}</Link>
              &rsquo;s — the most-traded plain fund covering this market.
            </>
          ) : (
            'Every fund covering this market is geared, inverse or currency-hedged, so none of them stands for it.'
          )
        }
        aside={<EodStamp eod={date} asOf={date} />}
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <StatCard
          label="Score"
          value={composite == null ? '—' : composite.toFixed(0)}
          colour={decileColour(row.decile)}
          sub={row.rank == null ? 'not scored' : `rank ${row.rank} of ${row.n_ranked} markets`}
        >
          <DecileMeter decile={row.decile} size="md" />
        </StatCard>
        <StatCard
          label="Breadth"
          value={breadth == null ? '—' : breadth.toFixed(0)}
          unit={breadth == null ? undefined : '%'}
          sub={`${scored} of ${row.n_etfs} funds scored`}
        />
        <StatCard label="Funds listed" value={row.n_etfs} sub={REGION_NAMES[row.region ?? ''] ?? row.region ?? '—'} />
        <StatCard
          label="Liquidity"
          value={row.adv_usd_60d_median ? formatUsd(row.adv_usd_60d_median, 0) : '—'}
          sub="60-session median $ volume"
        />
        <StatCard
          label="The fund"
          value={row.symbol ?? '—'}
          href={row.symbol ? `/etfs/${encodeURIComponent(row.symbol)}` : undefined}
          sub={row.fund_name ?? 'no plain fund covers this market'}
        />
      </div>

      <Section title="Against the S&P 500" note="(1+r)/(1+r SPY) − 1 — what the market did after taking the index out">
        <div className="dt panel">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-rule">
                {RS_WINDOWS.map((w) => (
                  <th key={w} className="bg-raised px-3 py-1.5 text-right text-meta font-semibold uppercase tracking-[0.1em] text-ink-3">
                    {WINDOW_LABEL[w]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                {RS_WINDOWS.map((w) => (
                  <RsCell key={w} value={row.rs[w]} />
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </Section>

      {row.symbol && series.points.length > 0 && <PriceSection series={series} symbol={row.symbol} />}

      <Section
        title="Every fund covering this market"
        note={
          scored > 0
            ? `ranked over the ${scored} that carry a score`
            : 'none carries a score — all are geared, hedged or below the liquidity floor'
        }
      >
        <CountryFundTable funds={funds} />
      </Section>
    </div>
  )
}
