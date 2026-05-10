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
  const n_leader_nav  = funds.filter(
    f => f.nav_state === 'Leader NAV' || f.nav_state === 'Strong NAV',
  ).length
  const n_aligned     = funds.filter(f => f.composition_state === 'Aligned').length
  const n_strong_hold = funds.filter(f => f.holdings_state === 'Strong-Holdings').length
  const n_suspended   = funds.filter(f => f.nav_state === 'DISLOCATION_SUSPENDED').length
  const n_weak_hold   = funds.filter(f => f.holdings_state === 'Weak-Holdings').length

  // Median RS pctile for selected period
  const pctileKey =
    period === '1M' ? 'rs_pctile_1m' :
    period === '3M' ? 'rs_pctile_3m' :
    'rs_pctile_6m'  // 6M and 1Y both use 6m column

  const pctiles = funds
    .map(f => parseFloat((f as Record<string, string | null>)[pctileKey] ?? ''))
    .filter(n => !isNaN(n))
    .sort((a, b) => a - b)
  const medianRsPctile = pctiles.length > 0
    ? pctiles[Math.floor(pctiles.length / 2)]
    : 0

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
  const medianRet = rets.length > 0 ? rets[Math.floor(rets.length / 2)] : 0

  // Top category by mean RS pctile
  const categoryMap: Record<string, number[]> = {}
  for (const f of funds) {
    const pct = parseFloat((f as Record<string, string | null>)[pctileKey] ?? '')
    if (isNaN(pct) || !f.category_name) continue
    if (!categoryMap[f.category_name]) categoryMap[f.category_name] = []
    categoryMap[f.category_name].push(pct)
  }
  let topCategory: string | null = null
  let topCategoryRsPctile = 0
  for (const [cat, values] of Object.entries(categoryMap)) {
    const mean = values.reduce((a, b) => a + b, 0) / values.length * 100
    if (mean > topCategoryRsPctile) {
      topCategoryRsPctile = mean
      topCategory = cat
    }
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
    top_category: topCategory,
    top_category_rs_pctile: topCategoryRsPctile,
  }
  const commentary = buildFundCommentary(commentaryCtx)

  const latestDate = funds[0]?.nav_date

  const tileCounts = {
    n_recommended,
    n_hold,
    n_leader_nav,
    n_aligned,
    n_strong_hold,
    medianRet,
    medianRsPctile,
    total: funds.length,
    latestDate,
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
        topCategory={topCategory}
        topCategoryRsPctile={topCategoryRsPctile}
      />
    </div>
  )
}
