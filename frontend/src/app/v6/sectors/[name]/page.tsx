// frontend/src/app/v6/sectors/[name]/page.tsx
// v6 sector detail — thin RSC wrapper. All render logic in SectorDetailClient.

import Link from 'next/link'
import { notFound } from 'next/navigation'
import { getSectorsForDate } from '@/lib/queries/v6/sectors'
import { getStocksForDate } from '@/lib/queries/v6/stocks'
import { getLatestSnapshotDate } from '@/lib/queries/v6/snapshot'
import { getSectorBookExposure } from '@/lib/queries/v6/sector_book_exposure'
import { getSectorBreadth } from '@/lib/queries/v6/sector_breadth'
import { getHeldIidSet } from '@/lib/queries/v6/portfolio_holdings'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { SectorDetailClient } from '@/components/v6/SectorDetailClient'

export const dynamic = 'force-dynamic'

export default async function V6SectorDetailPage({
  params,
}: {
  params: Promise<{ name: string }>
}) {
  const { name } = await params
  const decoded = decodeURIComponent(name)

  const snapshotDate = await getLatestSnapshotDate()

  const [sectors, sectorStocks, exposures, breadths, heldIidSet] =
    await Promise.all([
      getSectorsForDate(snapshotDate),
      getStocksForDate(snapshotDate, { sector: decoded }),
      getSectorBookExposure(decoded),
      getSectorBreadth(decoded),
      getHeldIidSet(),
    ])

  const sector = sectors.find((s) => s.sector_name === decoded)
  if (!sector) notFound()

  const exposure = exposures[0] ?? null
  const breadth  = breadths[0]  ?? null

  return (
    <div>
      {/* Breadcrumb */}
      <div className="px-6 py-3 border-b border-paper-rule">
        <nav className="font-sans text-xs text-ink-tertiary" aria-label="Breadcrumb">
          <Link href="/v6/sectors" className="text-teal hover:underline">
            Sectors
          </Link>
          <span className="mx-1.5">›</span>
          <span aria-current="page">{decoded}</span>
        </nav>
      </div>

      <DataSourceBanner source="live" asOf={snapshotDate} />

      <SectorDetailClient
        sector={sector}
        sectorName={decoded}
        stocks={sectorStocks}
        exposure={exposure}
        breadth={breadth}
        heldIidSet={heldIidSet}
        snapshotDate={snapshotDate}
      />
    </div>
  )
}
