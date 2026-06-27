// SectorDeepDiveV4 — revamped sector deep-dive (behind LENS_V4). Drops the verdict header,
// open-signals, sub-industry, and methodology cruft. Keeps the D/W/M Lightweight RS-ratio
// charts (TV's Advanced-Chart embed refuses NSE index symbols), the constituents drill, top
// picks, and strength distribution. Adds the native lens read, two 2x2s of the sector's
// stocks, within-sector breadth, and sector fundamentals + fund-flow tables. All new data
// from foundation_staging.
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { Suspense } from 'react'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { SectorHeroStrip } from '@/components/v6/sectors/SectorHeroStrip'
import { SectorRSRatioCharts } from '@/components/v6/sectors/SectorRSRatioCharts'
import { ConstituentsTable } from '@/components/v6/sectors/ConstituentsTable'
import { TopPicksPanel } from '@/components/v6/sectors/TopPicksPanel'
import { StrengthDistChart } from '@/components/v6/sectors/StrengthDistChart'
import { ScoreDerivationTree } from '@/components/v6/shared/ScoreDerivationTree'
import { sectorToDerivation } from '@/components/v4/adapters/sectorToDerivation'
import { SectorStock2x2 } from '@/components/v6/sectors/SectorStock2x2'
import { SectorBreadthWithin } from '@/components/v6/sectors/SectorBreadthWithin'
import { SectorFundamentalsTable } from '@/components/v6/sectors/SectorFundamentalsTable'
import { SectorFundFlowTable } from '@/components/v6/sectors/SectorFundFlowTable'
import { getSectorDeepdive } from '@/lib/queries/v6/sectors'
import { getSectorRatioSeries } from '@/lib/queries/v6/sector_index_rs'
import { getSectorLensVector, getSectorStocks, getSectorFundamentals, getSectorFundFlow } from '@/lib/queries/v6/sector_lens'
import { getConstituentDrivers } from '@/lib/queries/v6/drivers'

function SectionHead({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-[18px]">
      <h2 className="font-display text-[26px] font-normal tracking-tight text-txt-1">{title}</h2>
      {subtitle && <p className="font-sans text-[13px] text-txt-3 max-w-[760px] leading-[1.45] mt-1">{subtitle}</p>}
    </div>
  )
}
const Skeleton = ({ h = 48 }: { h?: number }) => <div style={{ height: h }} className="bg-surface-inset rounded-tile animate-pulse" />

export async function SectorDeepDiveV4({ sector }: { sector: string }) {
  // Batched fetches — Supabase session pooler caps clients at 15.
  const [deepdive, ratioSeries, lensVector] = await Promise.all([
    getSectorDeepdive(sector),
    getSectorRatioSeries(sector),
    getSectorLensVector(sector).catch(() => null),
  ])
  if (!deepdive) notFound()
  const [stocks, fundamentals, fundflow] = await Promise.all([
    getSectorStocks(sector).catch(() => []),
    getSectorFundamentals(sector).catch(() => null),
    getSectorFundFlow(sector).catch(() => null),
  ])
  // Per-constituent drivers (top catalyst filing, flow input, RS, ROE) → shown on each name in the
  // score tree so the sector's lens scores read bottom-up from real constituent drivers.
  const drivers = await getConstituentDrivers(stocks.map((s) => s.symbol)).catch(() => ({}))

  return (
    <div className="max-w-[1400px] mx-auto">
      <section className="px-8 py-8 border-b border-edge-hair">
        <nav className="font-sans text-[12px] text-txt-3 mb-3" aria-label="Breadcrumb">
          <Link href="/" className="text-brand hover:underline no-underline">Atlas</Link> ›{' '}
          <Link href="/sectors" className="text-brand hover:underline no-underline">Sectors</Link> ›{' '}
          <span aria-current="page">{sector}</span>
        </nav>
        <div className="flex items-baseline gap-4 flex-wrap mb-1.5">
          <h1 className="font-display text-[44px] font-normal tracking-[-0.011em] text-txt-1 leading-[1.05]">{sector}</h1>
          <span className="font-num text-[12px] tabular-nums text-txt-3">{deepdive.constituent_count} constituents</span>
        </div>
        <p className="font-sans text-[15px] text-txt-2 max-w-[880px]">
          What the six lenses say about the sector, where its stocks sit on momentum × quality and strength × leadership,
          its relative strength, fundamentals and fund flow — and the constituent drill-down.
        </p>
        <Suspense fallback={<Skeleton h={80} />}><SectorHeroStrip sector={deepdive} /></Suspense>
      </section>

      <DataSourceBanner source="live" asOf={deepdive.data_as_of} />

      {/* RS ratio charts (kept — key) */}
      <section className="px-8 py-9 border-b border-edge-hair" aria-label="RS ratio charts">
        <SectionHead title="Relative strength · sector vs Nifty 50" subtitle="Sector index ÷ Nifty 50 across Daily / Weekly / Monthly. Rising = outperforming the broad market." />
        <Suspense fallback={<Skeleton h={360} />}>
          <SectorRSRatioCharts sectorName={sector} indexCode={ratioSeries.index_code} daily={ratioSeries.daily} />
        </Suspense>
      </section>

      {/* Glass box: canonical Score-Derivation Tree (Conviction → lens → constituents by contribution) */}
      {lensVector && (
        <section className="px-8 py-10 border-b border-edge-hair" aria-label="How the score is built">
          <div className="mb-4">
            <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Glass box</p>
            <h2 className="font-display text-[28px] font-normal tracking-tight text-txt-1">How the score is built</h2>
            <p className="mt-1 max-w-[820px] font-sans text-[13px] text-txt-2">
              Click a lens to expand its constituents, ranked by contribution; each name links to its own evidence. The eye icon on any term explains it.
            </p>
          </div>
          <ScoreDerivationTree root={sectorToDerivation(sector, lensVector, stocks, drivers)} />
        </section>
      )}
      {stocks.length > 0 && <SectorStock2x2 stocks={stocks} />}
      {stocks.length > 0 && <SectorBreadthWithin stocks={stocks} />}

      {/* NEW: fundamentals + fund flow */}
      {fundamentals && <SectorFundamentalsTable data={fundamentals} />}
      {fundflow && <SectorFundFlowTable data={fundflow} />}

      {/* Top-picks table removed (FM 2026-06-26) — redundant with the full constituents
          table below; that table already surfaces the strongest names by return/RS. */}
      <section className="px-8 py-9 border-b border-edge-hair" aria-label="Constituents">
        <SectionHead title="Constituents · top 30" subtitle="The sector's stocks, ranked by 3-month return. Click any header to re-sort." />
        <Suspense fallback={<Skeleton h={400} />}><ConstituentsTable constituents={deepdive.constituents_top30} /></Suspense>
      </section>
      <section className="px-8 py-9 border-b border-edge-hair" aria-label="Strength distribution">
        <SectionHead title="Constituent strength distribution" subtitle="NTILE(5) on 3M absolute return within sector." />
        <div className="bg-surface-panel border border-edge-hair rounded-panel p-5 shadow-panel">
          <Suspense fallback={<Skeleton h={170} />}><StrengthDistChart dist={deepdive.strength_dist} /></Suspense>
        </div>
      </section>

      <div className="px-8 py-6 font-sans text-[12px] text-txt-3 leading-[1.6]">
        Native from <strong className="text-txt-2">foundation_staging</strong> — sector deep-dive, lens journal, financials, delivery.{' '}
        <Link href="/sectors" className="text-brand hover:underline">← Back to Sectors</Link>
      </div>
    </div>
  )
}
