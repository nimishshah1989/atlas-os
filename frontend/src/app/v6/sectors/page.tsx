// frontend/src/app/v6/sectors/page.tsx
// v6 sectors — SectorLadder hero.

import { getSectorsForDate } from '@/lib/queries/v6/sectors'
import { getLatestSnapshotDate } from '@/lib/queries/v6/snapshot'
import { SectorLadder } from '@/components/v6/SectorLadder'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'

export const dynamic = 'force-dynamic'

export default async function V6SectorsPage() {
  const snapshotDate = await getLatestSnapshotDate()
  const sectors = await getSectorsForDate(snapshotDate)

  const overweight = sectors.filter(s => s.sector_state === 'Overweight').length
  const neutral = sectors.filter(s => s.sector_state === 'Neutral').length
  const underweight = sectors.filter(s => s.sector_state === 'Underweight').length
  const avoid = sectors.filter(s => s.sector_state === 'Avoid').length

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="px-6 py-4 border-b border-paper-rule">
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
          Sectors · v6
        </div>
        <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary">
          Sector Ladder
        </h1>
        <p className="font-sans text-sm text-ink-secondary leading-relaxed mt-2 max-w-[760px]">
          {sectors.length} sectors ranked by composite RS, breadth, and vol regime.
          Click any row → sector detail with constituent stocks.
        </p>
      </div>

      <DataSourceBanner source="live" asOf={snapshotDate} />

      <div className="px-6 py-3 border-b border-paper-rule flex items-center gap-6 flex-wrap">
        <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
          <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
          {overweight} Overweight
        </span>
        <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
          <span className="inline-block w-2 h-2 rounded-full bg-paper-rule" />
          {neutral} Neutral
        </span>
        <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
          <span className="inline-block w-2 h-2 rounded-full bg-signal-warn" />
          {underweight} Underweight
        </span>
        <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
          <span className="inline-block w-2 h-2 rounded-full bg-signal-neg" />
          {avoid} Avoid
        </span>
      </div>

      <div className="px-6 py-5">
        <SectorLadder sectors={sectors} />
      </div>
    </div>
  )
}
