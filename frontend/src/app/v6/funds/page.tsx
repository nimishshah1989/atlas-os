// frontend/src/app/v6/funds/page.tsx
// D.5 — /v6/funds list: SwitchProposalsBanner + IndustrySnapshot (funds variant
//         with AMC leaderboard) + BubbleRiskReturnChart + SignatureMatrix +
//         ranked table with PortfolioBadge column (default visible).
//
// Thin RSC shell (≤250 LOC). All list logic lives in FundsList.tsx.
// v6.0 note: atlas_paper_portfolio is empty → SwitchProposalsBanner renders
// nothing, PortfolioBadge silent. Both degrade gracefully without errors.

import { getFundRowsForDate } from '@/lib/queries/v6/funds'
import { getLatestSnapshotDate } from '@/lib/queries/v6/snapshot'
import { getIndustrySnapshot } from '@/lib/queries/v6/industry_snapshot'
import { getHeldIidSet } from '@/lib/queries/v6/portfolio_holdings'
import { getSwitchProposals } from '@/lib/queries/v6/switch_proposals'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { SwitchProposalsBanner } from '@/components/v6/SwitchProposalsBanner'
import { FundsList } from '@/components/v6/FundsList'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'

export const dynamic = 'force-dynamic'

export default async function V6FundsPage() {
  const snapshotDate = await getLatestSnapshotDate()

  // Parallel fetch: fund rows, industry snapshot, held iid set, switch proposals.
  // All error-safe: empty tables return graceful defaults.
  const [funds, snapshot, heldIidSet, switchProposals] = await Promise.all([
    getFundRowsForDate(snapshotDate),
    getIndustrySnapshot('funds'),
    getHeldIidSet(),
    getSwitchProposals(),
  ])

  // Build holdingMap for PortfolioBadge column.
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

  const leaderCount = funds.filter(f => f.is_atlas_leader).length
  const avoidCount = funds.filter(f => f.is_avoid).length

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* ── Page header ─────────────────────────────────────────────────── */}
      <div className="px-6 py-4 border-b border-paper-rule">
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
          Funds · v6
        </div>
        <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary">
          Funds Discovery
        </h1>
        <p className="font-sans text-sm text-ink-secondary leading-relaxed mt-2 max-w-[760px]">
          {funds.length} funds · {leaderCount} Atlas Leaders · {avoidCount} Avoid ·
          ranked by composite score · as of {snapshotDate}.
        </p>
      </div>

      <DataSourceBanner source="live" asOf={snapshotDate} />

      {/* ── SWITCH proposals banner (silent when no proposals) ────────── */}
      {switchProposals.length > 0 && (
        <div className="px-6 pt-4">
          <SwitchProposalsBanner proposals={switchProposals} />
        </div>
      )}

      {/* ── FundsList client component ────────────────────────────────── */}
      <FundsList
        funds={funds}
        snapshot={snapshot}
        holdingMap={holdingMap}
        snapshotDate={snapshotDate}
      />
    </div>
  )
}
