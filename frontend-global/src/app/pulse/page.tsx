// src/app/pulse/page.tsx — the whole board on one screen: what the backdrop is, which sectors and
// themes and markets are working, how broad the move is, and which instruments are at the edges.
//
// The FM: "the pulse needs to be more like summary representations of everything that's there, and
// it needs to be complete… clickable pulse, or none of these pages should be independent."
//
// NOTHING HERE IS QUERIED TWICE. The strips map the SAME cached results /sectors, /themes and
// /countries render — one `eod` tag, one set of numbers. A summary that computed its own figures
// would be a fourth opinion of the market, and the first thing anyone would notice is the morning
// it disagreed with the page it claims to summarise.
//
// EVERY BLOCK FAILS ON ITS OWN. Each source is wrapped separately, so a query that breaks costs
// its own strip and not the page — which is the defect that put /pulse behind a 500 in public.
import { LeaderRail } from '@/components/pulse/LeaderRail'
import { PulseView } from '@/components/pulse/PulseView'
import { RankStrip } from '@/components/pulse/RankStrip'
import { EodStamp } from '@/components/ui/EodStamp'
import { InfoTip } from '@/components/ui/InfoTip'
import { PageHeader } from '@/components/ui/PageHeader'
import { QueryFailed } from '@/components/ui/Section'
import { requireUser } from '@/lib/auth'
import { getCountries } from '@/lib/queries/countries'
import { getPulse } from '@/lib/queries/pulse'
import { getSectorTree } from '@/lib/queries/sectors'
import { getInstrumentList } from '@/lib/queries/scores'
import { getThemes } from '@/lib/queries/themes'
import { expandRows } from '@/lib/facts'
import { countryItems, sectorItems, themeItems } from '@/lib/rank'
import { attempt } from '@/lib/result'

export const metadata = { title: 'Pulse' }

export default async function PulsePage() {
  await requireUser()
  const [pulse, tree, themes, countries, etfs, stocks] = await Promise.all([
    attempt(getPulse()),
    attempt(getSectorTree()),
    attempt(getThemes()),
    attempt(getCountries()),
    attempt(getInstrumentList('etf')),
    attempt(getInstrumentList('stock')),
  ])

  return (
    <div className="page">
      <PageHeader
        title="Pulse"
        lead={
          <>
            Where the strength is, how broad it is, and what to open next — every row here is a
            door into the board it came from.{' '}
            <InfoTip title="Counted, not indexed">
              The S&P 500 is weighted by size, so seven companies can carry it while four hundred
              fall. Every share on this page is over what was MEASURED, never over what was listed.
            </InfoTip>
          </>
        }
        aside={pulse.ok && pulse.value.eod ? <EodStamp eod={pulse.value.eod} asOf={pulse.value.as_of} /> : undefined}
      />

      <div className="grid gap-3 lg:grid-cols-3">
        {tree.ok ? (
          <RankStrip
            title="Sectors"
            note="Median score of the sector's themed funds. Opens that sector's themes in place."
            href="/sectors"
            items={sectorItems(tree.value.rows)}
          />
        ) : (
          <QueryFailed error={tree.error} />
        )}
        {themes.ok ? (
          <RankStrip
            title="Themes"
            note="Median score of the funds carrying the theme, and how many of them there are."
            href="/themes"
            items={themeItems(themes.value.rows)}
          />
        ) : (
          <QueryFailed error={themes.error} />
        )}
        {countries.ok ? (
          <RankStrip
            title="Markets"
            note="The representative fund's own score — unhedged, ungeared, largest by assets."
            href="/countries"
            items={countryItems(countries.value.rows)}
          />
        ) : (
          <QueryFailed error={countries.error} />
        )}
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        {/* The list ships PACKED (keys + cells) so Next's 2 MB data-cache ceiling is not hit;
            expandRows is the only way back to rows, and it is the same call /etfs makes. */}
        {etfs.ok && <LeaderRail title="Funds" href="/etfs" assetClass="etf" rows={expandRows(etfs.value)} />}
        {stocks.ok && <LeaderRail title="S&P 500" href="/stocks" assetClass="stock" rows={expandRows(stocks.value)} />}
      </div>

      <div className="mt-3">
        {pulse.ok ? <PulseView pulse={pulse.value} /> : <QueryFailed error={pulse.error} />}
      </div>
    </div>
  )
}
