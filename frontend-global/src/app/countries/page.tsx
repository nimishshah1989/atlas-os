// src/app/countries/page.tsx — the country product's front door.
// One tradeable fund per market, and how that market has done against the S&P.
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
        lead="One fund per market — the most-traded plain ETF that gives you exposure to it — and what that market has done against the S&P 500."
        aside={
          list.ok && list.value.date ? (
            // The grid is anchored on ONE session, so eod and as-of are the same date: there is
            // no "computed today from yesterday's close" gap to disclose here.
            <EodStamp eod={list.value.date} asOf={list.value.date} />
          ) : undefined
        }
      />
      {list.ok ? <CountryGrid list={list.value} /> : <QueryFailed error={list.error} />}
      <p className="mt-4 max-w-[80ch] text-meta text-ink-3">
        Every figure is relative to the S&P 500 in the form (1+r)/(1+r<sub>SPY</sub>) − 1, so
        +8.0% means the market beat the index by eight percent over that window, not that it rose
        eight percent. Membership comes from the fund&rsquo;s own name; the fund shown is the
        most-traded one that is not geared, inverse or currency-hedged, on its 60-session median
        dollar volume. Countries are not ranked or scored here — that arrives with the lens work.
      </p>
    </div>
  )
}
