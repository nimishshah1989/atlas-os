// src/components/entity/InstrumentPage.tsx — the server half of /etfs/[symbol] and
// /stocks/[symbol]: sign-in, one cached query for the instrument, then the detail view. A symbol
// that is not an active instrument of the class is a 404 (it may live under the other list).
import { notFound } from 'next/navigation'
import { NoDatabase } from '@/components/health/NoDatabase'
import { PageHeader } from '@/components/ui/PageHeader'
import { QueryFailed } from '@/components/ui/Section'
import { requireUser } from '@/lib/auth'
import { dbAvailable } from '@/lib/db'
import type { AssetClass } from '@/lib/facts'
import { getInstrumentDetail } from '@/lib/queries/instruments'
import { attempt } from '@/lib/result'
import { InstrumentDetailView } from './InstrumentDetailView'

export type SymbolParams = { params: Promise<{ symbol: string }> }

/** The segment as instrument_master spells it (BRK.B, ABR$D). Next 15.5 hands it percent-encoded
 *  (/stocks/ABR%24D arrives as "ABR%24D" — verified), so it is decoded once; a malformed escape
 *  ("100%") is looked up as typed and is a 404, not a 500. */
export async function symbolOf({ params }: SymbolParams): Promise<string> {
  const { symbol } = await params
  try {
    return decodeURIComponent(symbol)
  } catch {
    return symbol
  }
}

const LIST: Record<AssetClass, string> = { etf: 'ETFs', stock: 'Stocks' }

export async function InstrumentPage({ assetClass, symbol }: { assetClass: AssetClass; symbol: string }) {
  await requireUser()
  if (!dbAvailable) return <NoDatabase title={LIST[assetClass]} />
  const d = await attempt(getInstrumentDetail(assetClass, symbol))
  if (!d.ok) {
    return (
      <div className="page">
        <PageHeader title={symbol} />
        <QueryFailed error={d.error} />
      </div>
    )
  }
  if (!d.value) notFound()
  return <InstrumentDetailView d={d.value} />
}
