// frontend/src/app/v6/etfs/page.tsx
// D.7 — /v6/etfs list: IndustrySnapshot (ETF + AMC leaderboard) +
//         BubbleRiskReturnChart + SignatureMatrix + ranked table.
// Thin RSC shell (≤250 LOC). All logic lives in ETFsList.tsx.

import { getEtfsForDate } from '@/lib/queries/v6/etfs'
import { getLatestSnapshotDate } from '@/lib/queries/v6/snapshot'
import { getIndustrySnapshot } from '@/lib/queries/v6/industry_snapshot'
import { getHeldIidSet } from '@/lib/queries/v6/portfolio_holdings'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { ETFsList } from '@/components/v6/ETFsList'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'

export const dynamic = 'force-dynamic'

export default async function V6EtfsPage() {
  const snapshotDate = await getLatestSnapshotDate()

  // Parallel fetch: etfs + industry snapshot + held iid set
  const [etfs, snapshot, heldIidSet] = await Promise.all([
    getEtfsForDate(snapshotDate),
    getIndustrySnapshot('etfs'),
    getHeldIidSet(),
  ])

  // Build a minimal holdingMap for the PortfolioBadge column.
  // v6.0: atlas_paper_portfolio is empty at launch — map will be empty.
  const BADGE_STATE: HoldingState = {
    portfolio_count: 1,
    weight_range: ['0.00', '0.00'],
    aggregate_weight: '0.00',
    last_add_date: null,
  }
  const holdingMap: Record<string, HoldingState> = {}
  for (const iid of heldIidSet) {
    holdingMap[iid] = BADGE_STATE
  }

  const leaderCount = etfs.filter(e => e.is_atlas_leader).length

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* ── Page header ─────────────────────────────────────────────────── */}
      <div className="px-6 py-4 border-b border-paper-rule">
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
          ETFs · v6
        </div>
        <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary">
          ETF Universe
        </h1>
        <p className="font-sans text-sm text-ink-secondary leading-relaxed mt-2 max-w-[760px]">
          {etfs.length} ETFs · {leaderCount} Atlas Leaders · ranked by composite score · as of{' '}
          {snapshotDate}. ETFs carry POSITIVE/NEUTRAL directions only (no short domain).
        </p>
      </div>

      <DataSourceBanner source="live" asOf={snapshotDate} />

      {/* ── ETFsList client component ─────────────────────────────────── */}
      <ETFsList
        etfs={etfs}
        snapshot={snapshot}
        holdingMap={holdingMap}
        snapshotDate={snapshotDate}
      />
    </div>
  )
}
