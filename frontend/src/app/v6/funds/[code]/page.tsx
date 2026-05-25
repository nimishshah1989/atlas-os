// frontend/src/app/v6/funds/[code]/page.tsx
//
// Fund detail page — RSC thin shell (≤250 LOC).
// All logic lives in FundDetailClient.tsx.
//
// Data fetched in parallel:
//   1. getFundDetail(code) — scorecard + sub_metrics + top_holdings
//   2. getHoldingState(iid) — portfolio badge state
//   3. getSwitchProposals() — MF SWITCH proposals (filters to this fund in client)
//
// 404 when no scorecard row found for this scheme code.

import { notFound } from 'next/navigation'
import { FundDetailClient } from '@/components/v6/FundDetailClient'
import { getFundDetail } from '@/lib/queries/v6/funds'
import { getHoldingState } from '@/lib/queries/v6/portfolio_holdings'
import { getSwitchProposals } from '@/lib/queries/v6/switch_proposals'

export const dynamic = 'force-dynamic'

export default async function FundDetailPage({
  params,
}: {
  params: Promise<{ code: string }>
}) {
  const { code } = await params

  // Parallel fetch — all three queries are independent
  const [fund, switchProposals] = await Promise.all([
    getFundDetail(code),
    getSwitchProposals(),
  ])

  if (!fund) {
    notFound()
  }

  // Portfolio badge: keyed by fund iid (= scheme_code for funds)
  const holdingState = await getHoldingState(fund.iid)

  // Waterfall data: not yet available for funds in v6.0
  // (atlas_fund_metrics_daily has ret_* but no cohort/benchmark breakdown).
  // TODO(v6.1): derive from atlas_fund_metrics_daily benchmark columns.
  const waterfallData = null

  return (
    <main className="min-h-screen bg-[#F8F4EC]">
      <FundDetailClient
        fund={fund}
        holdingState={holdingState}
        switchProposals={switchProposals}
        waterfallData={waterfallData}
      />
    </main>
  )
}
