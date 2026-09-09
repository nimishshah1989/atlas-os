// src/app/countries/page.tsx — the country product's front door: one tradeable fund per market,
// scored, ranked, and clickable through to the market's own page.
import Link from 'next/link'
import { CountryGrid } from '@/components/countries/CountryGrid'
import { EodStamp } from '@/components/ui/EodStamp'
import { PageHeader } from '@/components/ui/PageHeader'
import { QueryFailed } from '@/components/ui/Section'
import { requireUser } from '@/lib/auth'
import { getCountries } from '@/lib/queries/countries'
import { attempt } from '@/lib/result'

export const metadata = { title: 'Countries' }

export default async function CountriesPage() {
  await requireUser()
  const list = await attempt(getCountries())
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
      {list.ok ? <CountryGrid list={list.value} /> : <QueryFailed error={list.error} />}
      <p className="mt-4 max-w-(--measure) text-meta text-ink-3">
        Relative strength is (1+r)/(1+r<sub>SPY</sub>) − 1: +8.0% means the market beat the index by
        eight percent over that window, not that it rose eight. Geared, inverse and below-floor
        funds are counted in Funds but never scored. <Link href="/methodology">How this is built</Link>.
      </p>
    </div>
  )
}
