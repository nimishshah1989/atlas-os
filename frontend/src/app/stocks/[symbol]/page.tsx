export const revalidate = 300

import { StockDetailV4 } from '@/components/v6/stock-detail/StockDetailV4'

export default async function StockPage({ params }: { params: Promise<{ symbol: string }> }) {
  const symbol = decodeURIComponent((await params).symbol).toUpperCase()
  return <StockDetailV4 symbol={symbol} />
}
