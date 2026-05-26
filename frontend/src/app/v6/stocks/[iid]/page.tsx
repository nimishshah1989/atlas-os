// frontend/src/app/v6/stocks/[iid]/page.tsx
// v6 stock deep-dive — thin RSC wrapper. All UI in StockDetailClient.

import Link from 'next/link'
import { notFound } from 'next/navigation'
import { getInstrumentDetail } from '@/lib/queries/v6/instrument'
import { getLatestSnapshotDate } from '@/lib/queries/v6/snapshot'
import { getHoldingState } from '@/lib/queries/v6/portfolio_holdings'
import { getStockTechnicals } from '@/lib/queries/v6/stock_technicals'
import { getMultiTenureReturns } from '@/lib/queries/v6/multi_tenure_returns'
import { getSignalCallsByIid } from '@/lib/queries/v6/recent_signal_calls'
import { getFundsHoldingStock } from '@/lib/queries/v6/funds_holding_stock'
import { getAuditTrail } from '@/lib/queries/v6/audit_trail'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { StockDetailClient } from '@/components/v6/StockDetailClient'
import { generateThesis, deriveActionVerb } from '@/lib/eli5/thesis'
import sql from '@/lib/db'
import type { CrossRuleDepthData } from '@/components/v6/StockHero'
import type { StockDetailClientProps } from '@/components/v6/StockDetailClient'

export const dynamic = 'force-dynamic'

// CrossRuleDepth: count POSITIVE conviction_daily rows for this iid today.
// Graceful null on empty table or query failure.
async function fetchCrossRuleDepth(iid: string, date: string): Promise<CrossRuleDepthData | null> {
  try {
    const rows = await sql<Array<{ n: string }>>`
      SELECT COUNT(*)::text AS n
      FROM atlas.atlas_conviction_daily
      WHERE instrument_id = ${iid}::uuid
        AND snapshot_date = ${date}::date
        AND verdict = 'POSITIVE'
    `
    return { depth: Math.min(parseInt(rows[0]?.n ?? '0', 10), 5), total: 5 }
  } catch { return null }
}

// Waterfall: derive from ScreenStock returns (best-effort).
function buildWaterfallData(s: NonNullable<Awaited<ReturnType<typeof getInstrumentDetail>>>): StockDetailClientProps['waterfallData'] {
  if (s.ret_6m == null) return null
  const p = (v: number | null) => (v == null ? '0' : (v * 100).toFixed(4))
  return { stock_return: p(s.ret_6m), cohort_return: p(s.rs_pctile_3m != null ? s.rs_pctile_3m * 0.5 : null), nifty50_return: '0', nifty500_return: '0', gold_return: null, tenure: '6m' }
}

// RankDecomposition: derive from conviction tape IC values across both
// directions. Composite = average signed IC across non-NEUTRAL tenures × 100.
// For RELIANCE with only 1m=-4.1 active, composite reflects the negative
// conviction; previously it returned 0 because only POSITIVE was counted.
function buildRankData(s: NonNullable<Awaited<ReturnType<typeof getInstrumentDetail>>>): StockDetailClientProps['rankData'] {
  const tapes = ['1m', '3m', '6m', '12m'] as const
  let active = 0
  let signedSum = 0
  const components = tapes.map((t) => {
    const seg = s.conviction_tape[t]
    const ic = seg.ic
    const dir = seg.direction
    if (ic != null && dir !== 'NEUTRAL') {
      active++
      signedSum += dir === 'POSITIVE' ? ic : -ic
    }
    return {
      name: t,
      raw_score: ic != null ? (ic * 100).toFixed(2) : '—',
      percentile_in_category: dir === 'POSITIVE' ? '75' : dir === 'NEGATIVE' ? '25' : '50',
      weight_pct: '25',
      delta_vs_cohort: ic != null && dir !== 'NEUTRAL' ? (ic * 100).toFixed(2) : '0',
    }
  })
  const composite = active > 0 ? ((signedSum / active) * 100).toFixed(2) : '—'
  return { composite_score: composite, components, rank_in_category: 1, category_size: 100 }
}

// Thesis: derive action verb + bullets from stock signals.
function buildThesis(s: NonNullable<Awaited<ReturnType<typeof getInstrumentDetail>>>, held: boolean): { actionVerb: string; bullets: string[] } {
  let dir: 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE' = 'NEUTRAL'
  for (const t of ['12m', '6m', '3m', '1m'] as const) {
    if (s.conviction_tape[t].direction !== 'NEUTRAL') { dir = s.conviction_tape[t].direction as 'POSITIVE' | 'NEGATIVE'; break }
  }
  const actionVerb = deriveActionVerb(dir, held)
  try {
    const res = generateThesis({ archetype: 'momentum_breakout', cap_tier: s.tier as 'Large' | 'Mid' | 'Small', tenure: '6m', direction: dir, is_held: held, features: { sector_name: s.sector ?? 'this sector' } })
    return { actionVerb, bullets: res.bullets }
  } catch {
    const bullets = dir === 'POSITIVE' ? [`${s.tier}-cap stock showing positive momentum conviction.`, `RS state: ${s.rs_state ?? 'unknown'}.`]
      : dir === 'NEGATIVE' ? [`${s.tier}-cap stock under negative pressure.`, `Caution warranted. RS state: ${s.rs_state ?? 'unknown'}.`]
      : [`No strong directional conviction at present.`]
    return { actionVerb, bullets }
  }
}

export default async function V6StockDetailPage({ params }: { params: Promise<{ iid: string }> }) {
  const { iid } = await params
  const decoded = decodeURIComponent(iid)
  const snapshotDate = await getLatestSnapshotDate()

  const [stock, holdingState, technicals, returns, , fundsHolding, auditTrail, crossRuleDepth] =
    await Promise.all([
      getInstrumentDetail(decoded, snapshotDate),
      getHoldingState(decoded),
      getStockTechnicals(decoded),
      getMultiTenureReturns(decoded),
      getSignalCallsByIid(decoded, 20),
      getFundsHoldingStock(decoded),
      getAuditTrail(decoded, snapshotDate),
      fetchCrossRuleDepth(decoded, snapshotDate),
    ])

  if (!stock) notFound()

  const isHeld = holdingState !== null
  const { actionVerb, bullets } = buildThesis(stock, isHeld)

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="px-6 py-3 border-b border-paper-rule">
        <nav className="font-sans text-xs text-ink-tertiary" aria-label="Breadcrumb">
          <Link href="/v6/stocks" className="text-teal hover:underline">Stocks</Link>
          <span className="mx-1.5">›</span>
          <span>{stock.symbol}</span>
        </nav>
      </div>
      <DataSourceBanner source="live" asOf={snapshotDate} />
      <StockDetailClient
        stock={stock}
        holdingState={holdingState}
        technicals={technicals}
        returns={returns}
        fundsHolding={fundsHolding}
        auditTrail={auditTrail}
        crossRuleDepth={crossRuleDepth}
        deploymentMultiplier={1.0}
        sectorGapPp={0}
        actionVerb={actionVerb}
        bullets={bullets}
        waterfallData={buildWaterfallData(stock)}
        rankData={buildRankData(stock)}
      />
    </div>
  )
}
