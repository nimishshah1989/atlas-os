// src/app/sp500/page.tsx — the S&P 500 board (and every other listed stock behind the index
// facet). Logic lives in components/explorer.
import { ExplorerPage } from '@/components/explorer/ExplorerPage'

export const metadata = { title: 'Stocks' }

export default function StocksPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  return <ExplorerPage assetClass="stock" searchParams={searchParams} />
}
