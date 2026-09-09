// src/app/countries/[iso2]/page.tsx — one market. Logic lives in components/countries.
import { notFound } from 'next/navigation'
import { CountryView } from '@/components/countries/CountryView'
import { NoDatabase } from '@/components/health/NoDatabase'
import { PageHeader } from '@/components/ui/PageHeader'
import { QueryFailed } from '@/components/ui/Section'
import { requireUser } from '@/lib/auth'
import { dbAvailable } from '@/lib/db'
import { getCountry } from '@/lib/queries/countries'
import { getInstrumentSeries, type InstrumentSeries } from '@/lib/queries/series'
import { attempt } from '@/lib/result'

type Params = { params: Promise<{ iso2: string }> }

const iso2Of = async ({ params }: Params) => (await params).iso2.toUpperCase()

export async function generateMetadata(props: Params) {
  const detail = dbAvailable ? await getCountry(await iso2Of(props)) : null
  return { title: detail?.row.name ?? (await iso2Of(props)) }
}

export default async function CountryPage(props: Params) {
  await requireUser()
  const iso2 = await iso2Of(props)
  if (!dbAvailable) return <NoDatabase title="Countries" />

  const detail = await attempt(getCountry(iso2))
  if (!detail.ok) {
    return (
      <div className="page">
        <PageHeader title={iso2} />
        <QueryFailed error={detail.error} />
      </div>
    )
  }
  if (!detail.value) notFound()

  // The chart is the REPRESENTATIVE fund's own history — the market has no price of its own, and
  // saying so is more honest than drawing a line and letting the reader assume there is an index
  // behind it. A market whose funds are all geared has no representative and no chart.
  const noSeries: InstrumentSeries = { points: [], benchmark: [], technical: null }
  const symbol = detail.value.row.symbol
  const series = symbol ? await attempt(getInstrumentSeries(symbol)) : null

  return (
    <CountryView
      detail={detail.value}
      series={series?.ok ? series.value : noSeries}
    />
  )
}
