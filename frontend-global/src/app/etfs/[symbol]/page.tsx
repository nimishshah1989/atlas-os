// src/app/etfs/[symbol]/page.tsx — one ETF. Logic lives in components/entity.
import { InstrumentPage, symbolOf, type SymbolParams } from '@/components/entity/InstrumentPage'

export async function generateMetadata(props: SymbolParams) {
  return { title: await symbolOf(props) }
}

export default async function EtfPage(props: SymbolParams) {
  return <InstrumentPage assetClass="etf" symbol={await symbolOf(props)} />
}
