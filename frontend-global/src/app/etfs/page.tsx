// src/app/etfs/page.tsx — the ETF universe, explorable. Logic lives in components/explorer.
import { ExplorerPage } from '@/components/explorer/ExplorerPage'

export const metadata = { title: 'ETFs' }

export default function EtfsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  return <ExplorerPage assetClass="etf" searchParams={searchParams} />
}
