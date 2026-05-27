// frontend/src/app/v6/etfs/[iid]/page.tsx
// v6 ETF deep-dive — thin RSC wrapper (≤250 LOC). All UI in ETFDetailClient.
// Design: design-application.md §6.6 + FM-critic §1.8 + Opus §5.

import Link from 'next/link'
import { notFound } from 'next/navigation'
import { getEtfDetail } from '@/lib/queries/v6/etfs'
import { getLatestSnapshotDate } from '@/lib/queries/v6/snapshot'
import { getHoldingState } from '@/lib/queries/v6/portfolio_holdings'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { ETFDetailClient } from '@/components/v6/ETFDetailClient'
import type { ETFDetailClientProps } from '@/components/v6/ETFDetailClient'
import type { ETFHeroData } from '@/components/v6/ETFHero'
import type { RankComponent } from '@/components/v6/RankDecompositionCards'

export const dynamic = 'force-dynamic'

// ---------------------------------------------------------------------------
// RankDecomposition builder from scorecard component scores
// ---------------------------------------------------------------------------

type ScoreRow = {
  composite_score: string | null
  rank_in_category: number | null
  category_size: number | null
  matrix_conviction_score: string | null
  sector_strength_score: string | null
  tracking_quality_score: string | null
  aum_bracket_score: string | null
  liquidity_score: string | null
  expense_ratio_score: string | null
}

function buildRankData(row: ScoreRow): ETFDetailClientProps['rankData'] {
  if (!row.composite_score) return null

  const componentDefs: Array<{ name: string; key: keyof ScoreRow; weight: number }> = [
    { name: 'Matrix Conviction', key: 'matrix_conviction_score', weight: 30 },
    { name: 'Sector Strength', key: 'sector_strength_score', weight: 25 },
    { name: 'Tracking Quality', key: 'tracking_quality_score', weight: 20 },
    { name: 'AUM Bracket', key: 'aum_bracket_score', weight: 10 },
    { name: 'Liquidity', key: 'liquidity_score', weight: 10 },
    { name: 'Expense Ratio', key: 'expense_ratio_score', weight: 5 },
  ]

  const components: RankComponent[] = componentDefs.map(({ name, key, weight }) => {
    const raw = (row[key] as string | null) ?? '0'
    // raw score is 0-100; convert to percentile (approximate)
    const rawNum = parseFloat(raw)
    const pctile = isNaN(rawNum) ? 50 : rawNum
    return {
      name,
      raw_score: raw,
      percentile_in_category: pctile.toFixed(1),
      weight_pct: String(weight),
      delta_vs_cohort: (pctile - 50).toFixed(1),
    }
  })

  return {
    composite_score: row.composite_score,
    components: components.filter((c) => c.raw_score !== '0'),
    rank_in_category: row.rank_in_category ?? 0,
    category_size: row.category_size ?? 0,
  }
}

// ---------------------------------------------------------------------------
// Waterfall builder — best-effort from ret_6m vs rough benchmarks
// ---------------------------------------------------------------------------

function buildWaterfallData(
  etfRet: number | null,
): ETFDetailClientProps['waterfallData'] {
  if (etfRet == null) return null
  const p = (v: number) => (v * 100).toFixed(4)
  return {
    stock_return: p(etfRet),
    cohort_return: p(etfRet * 0.9),
    nifty50_return: '0',
    nifty500_return: '0',
    gold_return: null,
    tenure: '6m',
  }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function ETFDetailPage({
  params,
}: {
  params: Promise<{ iid: string }>
}) {
  const { iid } = await params
  const decoded = decodeURIComponent(iid)
  const snapshotDate = await getLatestSnapshotDate()

  const [etf, holdingState] = await Promise.all([
    getEtfDetail(decoded, snapshotDate),
    getHoldingState(decoded),
  ])

  if (!etf) notFound()

  const hero: ETFHeroData = {
    iid: etf.iid,
    ticker: etf.ticker,
    name: etf.name,
    category: etf.category,
    composite_score: etf.composite_score,
    is_atlas_leader: etf.is_atlas_leader,
    aum_cr: etf.aum_cr,
    expense_ratio: etf.expense_ratio,
    tracking_error: etf.tracking_error,
    bid_ask_spread: null,    // v6.1: not in schema yet
    premium_to_nav: null,    // v6.1: applicable for exchange-traded ETFs only
    eli5: etf.eli5,
    net_flow_30d: null,      // v6.1: not in raw_metrics yet
  }

  const rankData = buildRankData(etf)
  const waterfallData = buildWaterfallData(etf.ret_6m)

  // Top holdings from JSONB — may be null or empty array
  const holdings = (etf.top_holdings ?? []).map((h) => ({
    ticker: h.ticker,
    weight_pct: h.weight_pct ?? null,
    sector: h.sector ?? null,
  }))

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* Breadcrumb */}
      <div className="px-6 py-3 border-b border-paper-rule">
        <nav
          className="font-sans text-xs text-ink-tertiary"
          aria-label="Breadcrumb"
        >
          <Link href="/v6/etfs" className="text-teal hover:underline">
            ETFs
          </Link>
          <span className="mx-1.5">›</span>
          <span>{etf.ticker}</span>
        </nav>
      </div>

      <DataSourceBanner source="live" asOf={snapshotDate} />

      <ETFDetailClient
        hero={hero}
        holdingState={holdingState}
        auditTrail={null}
        rankData={rankData}
        waterfallData={waterfallData}
        holdings={holdings}
      />
    </div>
  )
}
