// src/app/stocks/[symbol]/page.tsx — one stock. Logic lives in components/entity.
import { InstrumentPage, symbolOf, type SymbolParams } from '@/components/entity/InstrumentPage'

export async function generateMetadata(props: SymbolParams) {
  return { title: await symbolOf(props) }
}

export default async function StockPage(props: SymbolParams) {
  return <InstrumentPage assetClass="stock" symbol={await symbolOf(props)} />
}
