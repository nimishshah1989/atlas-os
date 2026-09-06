// src/app/etfs/page.tsx — the ETF universe, explorable. Logic lives in components/explorer.
import { ExplorerPage } from '@/components/explorer/ExplorerPage'

export const metadata = { title: 'ETFs' }

export default function EtfsPage() {
  return <ExplorerPage assetClass="etf" />
}
