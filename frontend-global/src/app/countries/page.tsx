// src/app/countries/page.tsx — the country product's front door: one tradeable fund per market,
// scored, ranked, and clickable through to the market's own page.
import Link from 'next/link'
import { CountryGrid } from '@/components/countries/CountryGrid'
import { BuildBasketLink, SEED_LIMIT } from '@/components/portfolios/BuildBasketLink'
import { EodStamp } from '@/components/ui/EodStamp'
import { PageHeader } from '@/components/ui/PageHeader'
import { QueryFailed } from '@/components/ui/Section'
import { requireUser } from '@/lib/auth'
import type { CountryRow } from '@/lib/countries'
import { getCountries } from '@/lib/queries/countries'
import { attempt } from '@/lib/result'

export const metadata = { title: 'Countries' }

/** One fund per market, strongest market first — each market's own representative, which is the
 *  most-traded plain fund covering it. A market with no scored representative is left out rather
 *  than seeded with nothing. */
function seedSymbols(rows: CountryRow[]): string[] {
  return rows
    .filter((r): r is CountryRow & { symbol: string; rank: number } => r.rank != null && !!r.symbol)
    .sort((a, b) => a.rank - b.rank)
    .map((r) => r.symbol)
}

export default async function CountriesPage() {
  await requireUser()
  const list = await attempt(getCountries())
  const seeds = list.ok ? seedSymbols(list.value.rows) : []
  return (
    <div className="page">
      <PageHeader
        title="Countries"
        lead="The most-traded plain fund covering each market, ranked by its score. Click a market."
        aside={
          list.ok && list.value.date ? (
            // The grid is anchored on ONE session, so eod and as-of are the same date: there is
            // no "computed today from yesterday's close" gap to disclose here.
            <EodStamp eod={list.value.date} asOf={list.value.date} />
          ) : undefined
        }
      />
      {/* THE COUNTRY BASKET IS BUILT HERE, not on a market's own page. The FM: "the whole point of
          a country ETF is the fact that we want to create a basket of DIVERSIFIED EXPOSURE TO
          COUNTRIES" — which is one fund per market across many markets, and never twelve Japan
          funds, which is what the same link on the detail page used to seed. */}
      {seeds.length > 0 && (
        <div className="mb-2 flex justify-end">
          <BuildBasketLink
            symbols={seeds}
            name="Top markets"
            label={`Build a basket from the top ${Math.min(seeds.length, SEED_LIMIT)} markets`}
          />
        </div>
      )}
      {list.ok ? <CountryGrid list={list.value} /> : <QueryFailed error={list.error} />}
      <p className="mt-4 max-w-(--measure) text-meta text-ink-3">
        Relative strength is (1+r)/(1+r<sub>SPY</sub>) − 1: +8.0% means the market beat the index by
        eight percent over that window, not that it rose eight. Geared, inverse and below-floor funds
        are measured like every other, and counted in Funds, but never ranked or bought.{' '}
        <Link href="/methodology">How this is built</Link>.
      </p>
    </div>
  )
}
