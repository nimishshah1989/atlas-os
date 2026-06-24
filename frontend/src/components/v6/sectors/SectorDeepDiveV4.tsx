// SectorDeepDiveV4 — revamped sector deep-dive (behind LENS_V4). Drops the verdict header,
// open-signals, sub-industry, and methodology cruft. Keeps the RS windows table, the D/W/M
// Lightweight RS-ratio charts (TV's Advanced-Chart embed refuses NSE index symbols), the
// constituents drill, top picks, and strength distribution. Adds the
// native lens read, two 2x2s of the sector's stocks, within-sector breadth, and sector
// fundamentals + fund-flow tables. All new data from foundation_staging.
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { Suspense } from 'react'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { SectorHeroStrip } from '@/components/v6/sectors/SectorHeroStrip'
import { RSWindowsTable } from '@/components/v6/sectors/RSWindowsTable'
import { SectorRSRatioCharts } from '@/components/v6/sectors/SectorRSRatioCharts'
import { ConstituentsTable } from '@/components/v6/sectors/ConstituentsTable'
import { TopPicksPanel } from '@/components/v6/sectors/TopPicksPanel'
import { StrengthDistChart } from '@/components/v6/sectors/StrengthDistChart'
import { SectorLensRead } from '@/components/v6/sectors/SectorLensRead'
import { SectorStock2x2 } from '@/components/v6/sectors/SectorStock2x2'
import { SectorBreadthWithin } from '@/components/v6/sectors/SectorBreadthWithin'
import { SectorFundamentalsTable } from '@/components/v6/sectors/SectorFundamentalsTable'
import { SectorFundFlowTable } from '@/components/v6/sectors/SectorFundFlowTable'
import { getSectorDeepdive } from '@/lib/queries/v6/sectors'
import { getSectorRatioSeries } from '@/lib/queries/v6/sector_index_rs'
import { getSectorLensVector, getSectorStocks, getSectorFundamentals, getSectorFundFlow } from '@/lib/queries/v6/sector_lens'

function SectionHead({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-[18px]">
      <h2 className="font-serif text-[26px] font-normal tracking-tight text-ink-primary">{title}</h2>
      {subtitle && <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px] leading-[1.45] mt-1">{subtitle}</p>}
    </div>
  )
}
const Skeleton = ({ h = 48 }: { h?: number }) => <div style={{ height: h }} className="bg-paper-rule/20 rounded-sm animate-pulse" />

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

  return (
    <div className="max-w-[1400px] mx-auto">
      <section className="px-8 py-8 border-b border-paper-rule">
        <nav className="font-sans text-[12px] text-ink-tertiary mb-3" aria-label="Breadcrumb">
          <Link href="/" className="text-teal hover:underline no-underline">Atlas</Link> ›{' '}
          <Link href="/sectors" className="text-teal hover:underline no-underline">Sectors</Link> ›{' '}
          <span aria-current="page">{sector}</span>
        </nav>
        <div className="flex items-baseline gap-4 flex-wrap mb-1.5">
          <h1 className="font-serif text-[44px] font-normal tracking-[-0.011em] text-ink-primary leading-[1.05]">{sector}</h1>
          <span className="font-mono text-[12px] text-ink-tertiary">{deepdive.constituent_count} constituents</span>
        </div>
        <p className="font-sans text-[15px] text-ink-secondary max-w-[880px]">
          What the six lenses say about the sector, where its stocks sit on momentum × quality and strength × leadership,
          its relative strength, fundamentals and fund flow — and the constituent drill-down.
        </p>
        <Suspense fallback={<Skeleton h={80} />}><SectorHeroStrip sector={deepdive} /></Suspense>
      </section>

      <DataSourceBanner source="live" asOf={deepdive.data_as_of} />

      {/* RS windows + RS ratio charts (kept — key) */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="RS windows">
        <SectionHead title="RS vs the baselines · 5 windows" subtitle="Percentage-point spread vs Nifty 500 over 5 windows; rank relative to all sectors." />
        <Suspense fallback={<Skeleton h={200} />}><RSWindowsTable sector={deepdive} /></Suspense>
      </section>
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="RS ratio charts">
        <SectionHead title="Relative strength · sector vs Nifty 50" subtitle="Sector index ÷ Nifty 50 across Daily / Weekly / Monthly. Rising = outperforming the broad market." />
        <Suspense fallback={<Skeleton h={360} />}>
          <SectorRSRatioCharts sectorName={sector} indexCode={ratioSeries.index_code} daily={ratioSeries.daily} />
        </Suspense>
      </section>

      {/* NEW: lens read + 2x2 + within-sector breadth */}
      {lensVector && <SectorLensRead vector={lensVector} stocks={stocks} />}
      {stocks.length > 0 && <SectorStock2x2 stocks={stocks} />}
      {stocks.length > 0 && <SectorBreadthWithin stocks={stocks} />}

      {/* NEW: fundamentals + fund flow */}
      {fundamentals && <SectorFundamentalsTable data={fundamentals} />}
      {fundflow && <SectorFundFlowTable data={fundflow} />}

      {/* Instrument drill — kept */}
      {deepdive.top_picks_top10.length > 0 && (
        <section className="px-8 py-9 border-b border-paper-rule" aria-label="Top picks">
          <SectionHead title="Top picks" subtitle="Highest-composite constituents in the sector." />
          <Suspense fallback={<Skeleton h={160} />}><TopPicksPanel picks={deepdive.top_picks_top10} /></Suspense>
        </section>
      )}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="Constituents">
        <SectionHead title="Constituents · top 30" subtitle="Stocks ranked by composite. Click headers to re-sort." />
        <Suspense fallback={<Skeleton h={400} />}><ConstituentsTable constituents={deepdive.constituents_top30} /></Suspense>
      </section>
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="Strength distribution">
        <SectionHead title="Constituent strength distribution" subtitle="NTILE(5) on 3M absolute return within sector." />
        <div className="bg-paper border border-paper-rule rounded-[2px] p-5">
          <Suspense fallback={<Skeleton h={170} />}><StrengthDistChart dist={deepdive.strength_dist} /></Suspense>
        </div>
      </section>

      <div className="px-8 py-6 font-sans text-[12px] text-ink-tertiary leading-[1.6]">
        Native from <strong className="text-ink-secondary">foundation_staging</strong> — sector deep-dive, lens journal, financials, delivery.{' '}
        <Link href="/sectors" className="text-teal hover:underline">← Back to Sectors</Link>
      </div>
    </div>
  )
}
