// frontend/src/app/sectors/page.tsx
// Page 04 — Sectors list route. Final production path at /sectors.
// Replaces /v6/sectors (which is left untouched for redirect handling).
//
// Sections:
//   1. Hero readout (Leading / Lagging / Rotation) — from mv_sector_cards
//   2. RRG quadrant scatter chart with 6-week trails — from mv_sector_rrg
//   3. Sector cards grid (3-col, 30 sectors) — from mv_sector_cards
//   4. Heatmap table (multi-window returns + RS) — from mv_sector_cards
//   5. Breadth panel — from SectorBreadthPanel (existing component, mv_sector_breadth)

import { Suspense } from 'react'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { SectorHeroReadout } from '@/components/v6/sectors/SectorHeroReadout'
import { SectorPulseGrid } from '@/components/v6/sectors/SectorPulseGrid'
import { SectorRRGChart } from '@/components/v6/sectors/SectorRRGChart'
import { SectorHeatmapTable } from '@/components/v6/sectors/SectorHeatmapTable'
import { SectorBreadthMVPanel } from '@/components/v6/sectors/SectorBreadthMVPanel'
import { getSectorCards, getSectorRRG, getSectorBreadthMV } from '@/lib/queries/v6/sectors'
import { getSectorIndexRs } from '@/lib/queries/v6/sector_index_rs'
import { getSectorReturnBases } from '@/lib/queries/v6/sector_return_bases'

export const dynamic = 'force-dynamic'

// ── Skeleton ──────────────────────────────────────────────────────────────────

function PageSkeleton() {
  return (
    <div className="space-y-8 animate-pulse" aria-label="Loading sectors…">
      <div className="h-48 bg-paper-rule/20 rounded-sm" />
      <div className="h-[560px] bg-paper-rule/20 rounded-sm" />
      <div className="h-64 bg-paper-rule/20 rounded-sm" />
      <div className="h-64 bg-paper-rule/20 rounded-sm" />
    </div>
  )
}

// ── Section header ────────────────────────────────────────────────────────────

function SectionHead({
  title, subtitle, controls,
}: {
  title: string
  subtitle?: string
  controls?: React.ReactNode
}) {
  return (
    <div className="flex items-baseline justify-between mb-5 flex-wrap gap-3">
      <div>
        <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary">{title}</h2>
        {subtitle && (
          <p className="font-sans text-[13px] text-ink-tertiary max-w-[720px] leading-[1.45] mt-1">{subtitle}</p>
        )}
      </div>
      {controls}
    </div>
  )
}

// ── Summary band ──────────────────────────────────────────────────────────────

function SummaryBand({
  cards,
}: {
  cards: Awaited<ReturnType<typeof getSectorCards>>
}) {
  const ow = cards.filter((c) => c.verdict_abbr === 'OW').length
  const nw = cards.filter((c) => c.verdict_abbr === 'NW').length
  const uw = cards.filter((c) => c.verdict_abbr === 'UW').length
  const unknown = cards.length - ow - nw - uw

  const pills = [
    { label: 'Overweight',  count: ow,      color: 'bg-signal-pos' },
    { label: 'Neutral',     count: nw,      color: 'bg-signal-warn' },
    { label: 'Underweight', count: uw,      color: 'bg-signal-neg' },
    { label: 'Unknown',     count: unknown, color: 'bg-paper-rule' },
  ].filter((p) => p.count > 0)

  return (
    <div className="flex items-center gap-6 flex-wrap py-3 border-b border-paper-rule">
      {pills.map((p) => (
        <span key={p.label} className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
          <span className={`inline-block w-2 h-2 rounded-full ${p.color}`} aria-hidden="true" />
          {p.count} {p.label}
        </span>
      ))}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default async function SectorsPage() {
  // Parallel data fetch — all independent queries
  const [cards, rrg, breadth, indexRs, returnBases] = await Promise.all([
    getSectorCards(),
    getSectorRRG(),
    getSectorBreadthMV(),
    getSectorIndexRs(),
    getSectorReturnBases(),
  ])

  const latestDate = cards[0]?.as_of_date ?? null

  return (
    <div className="max-w-[1400px] mx-auto">

      {/* Page header */}
      <div className="px-8 py-8 border-b border-paper-rule">
        <div className="font-sans text-[12px] text-ink-tertiary mb-3">
          <a href="/" className="text-teal no-underline hover:underline">Atlas</a>
          {' '}›{' '}Sectors
        </div>
        <h1 className="font-serif text-[44px] font-normal tracking-[-0.011em] text-ink-primary leading-[1.1] mb-2">
          Sectors
        </h1>
        <p className="font-sans text-[15px] text-ink-secondary max-w-[820px]">
          {cards.length} actionable sectors. Where is leadership flowing, where is it fading,
          and which sectors does Atlas weight overweight given the current regime?
        </p>

        {/* Market-pulse relative-return grid (above the leading-sectors hero) */}
        <SectorPulseGrid data={indexRs} />

        {/* Hero readout */}
        <Suspense fallback={<div className="h-40 bg-paper-rule/20 rounded-sm mt-6 animate-pulse" />}>
          <SectorHeroReadout cards={cards} rrg={rrg} />
        </Suspense>
      </div>

      {latestDate && (
        <DataSourceBanner source="live" asOf={latestDate} />
      )}

      {/* Summary band */}
      <div className="px-8">
        <SummaryBand cards={cards} />
      </div>

      {/* Section 1 — RRG */}
      <section className="px-8 py-10 border-b border-paper-rule" aria-label="Sector Relative Rotation Graph">
        <SectionHead
          title="Sector rotation graph"
          subtitle="RS-ratio (x) vs RS-momentum (y). Sectors move counter-clockwise through four quadrants — Leading → Weakening → Lagging → Improving. Trailing dots show the 6-week path."
        />
        <Suspense fallback={<div className="h-[560px] bg-paper-rule/20 rounded-sm animate-pulse" />}>
          <SectorRRGChart data={rrg} />
        </Suspense>
      </section>

      {/* Section 2 — Heatmap table (consolidated: cards grid removed per M16 — heatmap is denser) */}
      <section className="px-8 py-10 border-b border-paper-rule" aria-label="Sector return heatmap">
        <SectionHead
          title="Multi-window return heatmap"
          subtitle="Returns and RS vs Nifty 500 across 1D / 1W / 1M / 3M / 6M / 12M. Toggle between the cap-weighted Index and the free-float cap-weighted Bottom-up basis. Color intensity = magnitude of move."
        />
        <Suspense fallback={<div className="h-64 bg-paper-rule/20 rounded-sm animate-pulse" />}>
          <SectorHeatmapTable cards={cards} returnBases={returnBases} />
        </Suspense>
      </section>

      {/* Section 4 — Breadth panel */}
      <section className="px-8 py-10 border-b border-paper-rule" aria-label="Sector breadth">
        <SectionHead
          title="Sector breadth · EMA participation"
          subtitle="Percentage of constituents above EMA20 / EMA50 / EMA200 per sector. From atlas.mv_sector_breadth."
        />
        <Suspense fallback={<div className="h-64 bg-paper-rule/20 rounded-sm animate-pulse" />}>
          <SectorBreadthMVPanel rows={breadth} />
        </Suspense>
      </section>

      {/* Footer */}
      <div className="px-8 py-6 font-sans text-[12px] text-ink-tertiary leading-[1.6]">
        Data from{' '}
        <strong className="text-ink-secondary">atlas.mv_sector_cards</strong>
        {', '}
        <strong className="text-ink-secondary">atlas.mv_sector_rrg</strong>
        {', and '}
        <strong className="text-ink-secondary">atlas.mv_sector_breadth</strong>{' '}
        — refreshed nightly at 20:40–20:55 IST via pg_cron.{' '}
        Click any sector to view the full deep-dive.
      </div>

    </div>
  )
}
