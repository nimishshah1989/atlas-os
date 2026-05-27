// frontend/src/app/v6/sectors/page.tsx
// v6 sectors — D.3: Book Strip + RRG + Bubble + 30-row ladder + sparklines.
// Thin RSC shell (≤250 LOC). All interactive logic in SectorsListV6.tsx.

import { Suspense } from 'react'
import { getSectorsForDate } from '@/lib/queries/v6/sectors'
import { getLatestSnapshotDate } from '@/lib/queries/v6/snapshot'
import { getSectorBookExposure } from '@/lib/queries/v6/sector_book_exposure'
import { getSectorsWithMomentum, getRRGHistory } from '@/lib/queries/sectors'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { SectorsListV6 } from '@/components/v6/SectorsListV6'

export const dynamic = 'force-dynamic'

export default async function V6SectorsPage() {
  // Parallel data fetch — all independent queries
  const [snapshotDate, rrgCurrent, rrgHistory] = await Promise.all([
    getLatestSnapshotDate(),
    getSectorsWithMomentum(),
    getRRGHistory(84), // 12 weeks ≈ 84 calendar days
  ])

  const [sectors, exposures] = await Promise.all([
    getSectorsForDate(snapshotDate),
    getSectorBookExposure(),   // all sectors — list variant
  ])

  const overweight  = sectors.filter(s => s.sector_state === 'Overweight').length
  const neutral     = sectors.filter(s => s.sector_state === 'Neutral').length
  const underweight = sectors.filter(s => s.sector_state === 'Underweight').length
  const avoid       = sectors.filter(s => s.sector_state === 'Avoid').length

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* Page header */}
      <div className="px-6 py-4 border-b border-paper-rule">
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
          Sectors · v6
        </div>
        <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary">
          Sector Intelligence
        </h1>
        <p className="font-sans text-sm text-ink-secondary leading-relaxed mt-2 max-w-[760px]">
          {sectors.length} sectors — book strip, rotation graph, risk/return map, and ranked ladder.
          Click any sector row or RRG bubble to open the sector deep-dive.
        </p>
      </div>

      <DataSourceBanner source="live" asOf={snapshotDate} />

      {/* State summary band */}
      <div className="px-6 py-3 border-b border-paper-rule flex items-center gap-6 flex-wrap">
        <StateSummaryPill label="Overweight"  count={overweight}  color="bg-signal-pos" />
        <StateSummaryPill label="Neutral"     count={neutral}     color="bg-paper-rule" />
        <StateSummaryPill label="Underweight" count={underweight} color="bg-signal-warn" />
        <StateSummaryPill label="Avoid"       count={avoid}       color="bg-signal-neg" />
      </div>

      {/* Main content — SectorsListV6 client component */}
      <div className="px-6 py-6">
        <Suspense fallback={<SectorsSkeleton />}>
          <SectorsListV6
            sectors={sectors}
            exposures={exposures}
            rrgCurrent={rrgCurrent}
            rrgHistory={rrgHistory}
          />
        </Suspense>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// StateSummaryPill — server-side, no interactivity needed
// ---------------------------------------------------------------------------

function StateSummaryPill({
  label, count, color,
}: {
  label: string
  count: number
  color: string
}) {
  return (
    <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
      <span className={`inline-block w-2 h-2 rounded-full ${color}`} />
      {count} {label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Skeleton — used during Suspense streaming
// ---------------------------------------------------------------------------

function SectorsSkeleton() {
  return (
    <div className="space-y-8 animate-pulse" aria-label="Loading sectors…">
      {/* Book strip skeleton */}
      <div className="h-48 bg-paper-rule/20 rounded-sm" />
      {/* RRG skeleton */}
      <div className="h-64 bg-paper-rule/20 rounded-sm" />
      {/* Bubble chart skeleton */}
      <div className="h-48 bg-paper-rule/20 rounded-sm" />
      {/* Ladder skeleton */}
      <div className="h-64 bg-paper-rule/20 rounded-sm" />
    </div>
  )
}
