// frontend/src/app/v6/stocks/[iid]/page.tsx
// v6 stock deep-dive — large ConvictionTape + segment-expanded RuleCard.

import Link from 'next/link'
import { notFound } from 'next/navigation'
import { getCellDefinitions } from '@/lib/api/v1'
import { getInstrumentDetail } from '@/lib/queries/v6/instrument'
import { getLatestSnapshotDate } from '@/lib/queries/v6/snapshot'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { StockDetailClient } from '@/components/v6/StockDetailClient'
import type { CellRule } from '@/lib/api/v1'

export const dynamic = 'force-dynamic'

export default async function V6StockDetailPage({ params }: { params: Promise<{ iid: string }> }) {
  const { iid } = await params
  const decoded = decodeURIComponent(iid)
  const snapshotDate = await getLatestSnapshotDate()
  const [stock, cellsRes] = await Promise.all([
    getInstrumentDetail(decoded, snapshotDate),
    getCellDefinitions(),
  ])
  if (!stock) notFound()

  const cellRules = new Map<string, CellRule[]>(
    cellsRes.data.map(c => [c.cell_id, c.rules])
  )

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="px-6 py-4 border-b border-paper-rule">
        <div className="font-sans text-xs text-ink-tertiary mb-1">
          <Link href="/v6/stocks" className="text-teal hover:underline">Stocks</Link>
          <span className="mx-1.5">›</span>
          {stock.symbol}
        </div>
        <div className="flex items-baseline gap-3 flex-wrap">
          <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary">
            {stock.symbol}
          </h1>
          <span className="font-sans text-sm text-ink-secondary">
            {stock.company_name}
          </span>
          <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">
            {stock.tier} · {stock.sector}
          </span>
        </div>
      </div>

      <DataSourceBanner source="live" asOf={snapshotDate} />

      <StockDetailClient stock={stock} cellRules={cellRules} />
    </div>
  )
}
