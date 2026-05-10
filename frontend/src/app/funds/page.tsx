export const dynamic = 'force-dynamic'

import { getAllFunds } from '@/lib/queries/funds'
import { validatePeriod } from '@/lib/url-params'
import { buildFundCommentary } from '@/lib/commentary/funds'
import { FundPageClient } from '@/components/funds/FundPageClient'
import type { FundCommentaryContext } from '@/lib/commentary/funds'
import type { Period } from '@/lib/url-params'

export default async function FundsPage({
  searchParams,
}: {
  searchParams: Promise<{ period?: string }>
}) {
  const { period: rawPeriod } = await searchParams
  const period: Period = validatePeriod(rawPeriod)
  const funds = await getAllFunds()

  if (funds.length === 0) {
    return (
      <div className="p-8">
        <p className="font-sans text-sm text-ink-secondary">
          No fund data available. Run the nightly pipeline first.
        </p>
      </div>
    )
  }

  // Tile counts (server-side computation)
  const n_recommended = funds.filter(f => f.recommendation === 'Recommended').length
  const n_hold        = funds.filter(f => f.recommendation === 'Hold').length
  const n_leader_nav  = funds.filter(f => f.nav_state === 'Leader NAV').length
  const n_aligned     = funds.filter(f => f.composition_state === 'Aligned').length
  const n_strong_hold = funds.filter(f => f.recommendation === 'Hold' && f.holdings_state === 'Strong-Holdings').length
  const n_suspended   = funds.filter(f => f.nav_state === 'DISLOCATION_SUSPENDED').length
  const n_weak_hold   = funds.filter(f => f.recommendation === 'Hold' && f.holdings_state === 'Weak-Holdings').length

  // Median RS pctile — always use rs_pctile_3m (90-day equivalent)
  const pctiles = funds
    .map(f => parseFloat(f.rs_pctile_3m ?? ''))
    .filter(n => !isNaN(n))
    .sort((a, b) => a - b)
  const medianRsPctile = (() => {
    if (pctiles.length === 0) return 0
    const mid = Math.floor(pctiles.length / 2)
    return pctiles.length % 2 === 1 ? pctiles[mid] : (pctiles[mid - 1] + pctiles[mid]) / 2
  })()

  // Median return for selected period
  const retKey =
    period === '1M' ? 'ret_1m' :
    period === '6M' ? 'ret_6m' :
    period === '1Y' ? 'ret_12m' :
    'ret_3m'

  const rets = funds
    .map(f => parseFloat((f as Record<string, string | null>)[retKey] ?? ''))
    .filter(n => !isNaN(n))
    .sort((a, b) => a - b)
  const medianReturn: number | null = (() => {
    if (rets.length === 0) return null
    const mid = Math.floor(rets.length / 2)
    return rets.length % 2 === 1 ? rets[mid] : (rets[mid - 1] + rets[mid]) / 2
  })()

  // Top category by mean RS pctile (rs_pctile_3m, stored as fraction 0-1)
  type TopCategory = { name: string; mean: number }
  let topCategory: TopCategory | null = null
  {
    const byCat: Record<string, number[]> = {}
    for (const f of funds) {
      if (f.rs_pctile_3m != null && f.category_name) {
        if (!byCat[f.category_name]) byCat[f.category_name] = []
        byCat[f.category_name].push(parseFloat(f.rs_pctile_3m))
      }
    }
    let bestName: string | null = null
    let bestMean = -1
    for (const [cat, vals] of Object.entries(byCat)) {
      const mean = vals.reduce((a, b) => a + b, 0) / vals.length
      if (mean > bestMean) { bestMean = mean; bestName = cat }
    }
    if (bestName != null) topCategory = { name: bestName, mean: bestMean }
  }

  const commentaryCtx: FundCommentaryContext = {
    total: funds.length,
    n_recommended,
    pct_recommended: n_recommended / funds.length,
    n_leader_nav,
    pct_leader_nav: n_leader_nav / funds.length,
    pct_aligned_composition: n_aligned / funds.length,
    pct_weak_holdings: n_weak_hold / funds.length,
    pct_suspended: n_suspended / funds.length,
    top_category: topCategory?.name ?? null,
    top_category_rs_pctile: topCategory != null ? topCategory.mean * 100 : 0,
  }
  const commentary = buildFundCommentary(commentaryCtx)

  const tileCounts = {
    n_recommended,
    n_hold,
    n_leader_nav,
    n_aligned,
    n_strong_hold,
    n_suspended,
    n_weak_hold,
  }

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="px-6 py-4 border-b border-paper-rule flex items-center justify-between">
        <h1 className="font-sans text-sm font-semibold text-ink-primary uppercase tracking-wide">
          Fund Universe
        </h1>
      </div>
      <FundPageClient
        funds={funds}
        period={period}
        tileCounts={tileCounts}
        commentary={commentary}
        medianRsPctile={medianRsPctile}
        medianReturn={medianReturn}
        topCategory={topCategory}
      />
    </div>
  )
}
