export const revalidate = 300

// /funds — leads with the v2 IC-weighted composite scorecard ranking
// (composite_score, Atlas grade, rank-in-category, momentum). Sources the
// already-built getFundListPage (mv_fund_list_v6, returns joined from
// atlas_fund_metrics_daily) and the FundsList surface. Replaces the legacy
// nav-state/recommendation model as the primary view.

import { getFundListPage, type FundListRow } from '@/lib/queries/v6/fund-list'
import { getIndustrySnapshot } from '@/lib/queries/v6/industry_snapshot'
import { FundsList, type FundRow } from '@/components/v6/FundsList'
import { LENS_V4_ENABLED } from '@/lib/feature-flags'
import { FundsPageV4 } from '@/components/v6/funds/FundsPageV4'

/** Map the composite-scorecard row to the FundsList table row shape. */
function toFundRow(r: FundListRow): FundRow {
  return {
    iid: r.scheme_code,
    code: r.scheme_code,
    name: r.fund_name,
    category: r.fund_category,
    aum_cr: r.aum_cr != null ? String(r.aum_cr) : null,
    expense_ratio: r.expense_ratio != null ? String(r.expense_ratio) : null,
    composite_score: r.composite_score != null ? String(r.composite_score) : null,
    rank_in_category: r.rank_in_category,
    category_size: r.category_size,
    is_atlas_leader: r.is_atlas_leader,
    is_avoid: r.is_avoid,
    ret_1m: r.ret_1m,
    ret_3m: r.ret_3m,
    ret_6m: r.ret_6m,
    ret_12m: r.ret_12m,
    rs_pctile_3m: r.rs_pctile_3m != null ? String(r.rs_pctile_3m) : null,
    sector_tilt: null,
    realized_vol_63: r.realized_vol_63 ?? null,
    risk_adjusted_return_score: r.risk_adjusted_return_score != null ? String(r.risk_adjusted_return_score) : null,
    holdings_conviction_score: r.holdings_conviction_score != null ? String(r.holdings_conviction_score) : null,
    style_sector_score: r.style_sector_score != null ? String(r.style_sector_score) : null,
    cost_manager_score: r.cost_manager_score != null ? String(r.cost_manager_score) : null,
  }
}

export default async function FundsPage() {
  if (LENS_V4_ENABLED) return <FundsPageV4 />

  const [page, snapshot] = await Promise.all([
    getFundListPage(),
    getIndustrySnapshot('funds'),
  ])

  if (page.rows.length === 0) {
    return (
      <div className="p-8">
        <p className="font-sans text-sm text-ink-secondary">
          No fund data available. Run the nightly pipeline first.
        </p>
      </div>
    )
  }

  const funds = page.rows.map(toFundRow)

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="px-6 py-4 border-b border-paper-rule flex items-center justify-between">
        <h1 className="font-sans text-sm font-semibold text-ink-primary uppercase tracking-wide">
          Fund Universe
        </h1>
        <span className="font-mono text-[11px] text-ink-tertiary">
          {funds.length} schemes · ranked by Atlas composite score
        </span>
      </div>
      <FundsList
        funds={funds}
        snapshot={snapshot}
        holdingMap={{}}
        snapshotDate={page.as_of_date ?? ''}
      />
    </div>
  )
}
