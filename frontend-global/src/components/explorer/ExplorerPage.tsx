// src/components/explorer/ExplorerPage.tsx — the server half of /etfs and /stocks: sign-in, one
// cached query for every active instrument of the class, the dated header, then the explorer.
import { NoDatabase } from '@/components/health/NoDatabase'
import { EodStamp } from '@/components/ui/EodStamp'
import { InfoTip } from '@/components/ui/InfoTip'
import { PageHeader } from '@/components/ui/PageHeader'
import { QueryFailed } from '@/components/ui/Section'
import { requireUser } from '@/lib/auth'
import { dbAvailable } from '@/lib/db'
import type { AssetClass } from '@/lib/facts'
import { getInstrumentList } from '@/lib/queries/scores'
import { attempt } from '@/lib/result'
import { InstrumentExplorer } from './InstrumentExplorer'

// The lead is ONE line: what the board is ranked by. The universe rule beneath it is a
// methodology decision — which rows the board opens on, and that the rest are one click away, not
// hidden — so it is kept, behind the InfoTip, rather than printed as a second paragraph.
const COPY: Record<AssetClass, { title: string; lead: string; universe: string }> = {
  etf: {
    title: 'ETFs',
    lead: 'Ranked inside the job each fund does, strongest first.',
    universe: 'Opens on the funds that clear the liquidity floor and are neither leveraged nor inverse. Widen it to everything listed, with each fund’s reason for being out, from the rail.',
  },
  stock: {
    title: 'Stocks',
    lead: 'The S&P 500 at the latest session, ranked within its cap cohort, strongest first.',
    universe: 'Membership is the universe, not a filter. Widen it to every listed stock, with each name’s reason for being out, from the rail.',
  },
}

export async function ExplorerPage({ assetClass }: { assetClass: AssetClass }) {
  await requireUser()
  const { title, lead, universe } = COPY[assetClass]
  if (!dbAvailable) return <NoDatabase title={title} />
  const list = await attempt(getInstrumentList(assetClass))
  return (
    <div className="page page-wide">
      <PageHeader
        title={title}
        lead={
          <>
            {lead} <InfoTip title="The universe">{universe}</InfoTip>
          </>
        }
        aside={list.ok ? <EodStamp eod={list.value.eod} asOf={list.value.as_of} /> : undefined}
      />
      {list.ok ? <InstrumentExplorer assetClass={assetClass} list={list.value} /> : <QueryFailed error={list.error} />}
    </div>
  )
}
