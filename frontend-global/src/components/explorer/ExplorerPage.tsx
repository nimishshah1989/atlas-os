// src/components/explorer/ExplorerPage.tsx — the server half of /etfs and /stocks: sign-in, one
// cached query for every active instrument of the class, the dated header, then the explorer.
import { NoDatabase } from '@/components/health/NoDatabase'
import { EodStamp } from '@/components/ui/EodStamp'
import { PageHeader } from '@/components/ui/PageHeader'
import { QueryFailed } from '@/components/ui/Section'
import { requireUser } from '@/lib/auth'
import { dbAvailable } from '@/lib/db'
import type { AssetClass } from '@/lib/facts'
import { getInstrumentList } from '@/lib/queries/instruments'
import { attempt } from '@/lib/result'
import { InstrumentExplorer } from './InstrumentExplorer'

const COPY: Record<AssetClass, { title: string; lead: string }> = {
  etf: {
    title: 'ETFs',
    lead: 'Every US-listed ETF in the Nasdaq Trader directory, with its identity as the SEC and the price vendors spell it. Prices, returns and relative strength join once the price spine runs.',
  },
  stock: {
    title: 'Stocks',
    lead: 'The S&P 500 at the latest session, with its sector and weight in SPY; widen the index facet for every other listed stock. Prices, returns and relative strength join once the price spine runs.',
  },
}

export async function ExplorerPage({ assetClass }: { assetClass: AssetClass }) {
  await requireUser()
  const { title, lead } = COPY[assetClass]
  if (!dbAvailable) return <NoDatabase title={title} />
  const list = await attempt(getInstrumentList(assetClass))
  return (
    <div className="page page-wide">
      <PageHeader title={title} lead={lead} aside={list.ok ? <EodStamp eod={list.value.eod} asOf={list.value.as_of} /> : undefined} />
      {list.ok ? <InstrumentExplorer assetClass={assetClass} list={list.value} /> : <QueryFailed error={list.error} />}
    </div>
  )
}
