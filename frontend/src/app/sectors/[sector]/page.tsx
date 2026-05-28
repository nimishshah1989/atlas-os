// frontend/src/app/sectors/[sector]/page.tsx
// allow-large: Page 04a sector deep-dive — multi-section composition (hero + windows + RRG + constituents + signals). Cleanup tracked post-presentation.
// Page 04a — Sector deep-dive route. Final production path at /sectors/[sector].
// Replaces /v6/sectors/[name] (which is left untouched for redirect handling).
//
// Sections:
//   1. Hero strip — 6-tile verdict strip (returns, RS, constituents, breadth, verdict)
//   2. RS windows table — vs Nifty 500 across 5 windows (Nifty 50/Gold/S&P deferred)
//   3. Constituents top-30 table — sortable by composite/returns/RS
//   4. Top picks top-10 — stocks with positive composite score
//   5. Strength distribution chart — quintile bar chart
//   6. Open signals panel — all open BUY/SELL calls in sector
//   [Macro overlays — DEFERRED: requires separate macro query layer not in MV]

import Link from 'next/link'
import { notFound } from 'next/navigation'
import { Suspense } from 'react'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { SectorHeroStrip } from '@/components/v6/sectors/SectorHeroStrip'
import { RSWindowsTable } from '@/components/v6/sectors/RSWindowsTable'
import { ConstituentsTable } from '@/components/v6/sectors/ConstituentsTable'
import { TopPicksPanel } from '@/components/v6/sectors/TopPicksPanel'
import { StrengthDistChart } from '@/components/v6/sectors/StrengthDistChart'
import { OpenSignalsPanel } from '@/components/v6/sectors/OpenSignalsPanel'
import { getSectorDeepdive } from '@/lib/queries/v6/sectors'

export const dynamic = 'force-dynamic'

// ── Section header ────────────────────────────────────────────────────────────

function SectionHead({
  title, subtitle,
}: {
  title: string
  subtitle?: string
}) {
  return (
    <div className="mb-[18px]">
      <h2 className="font-serif text-[26px] font-normal tracking-tight text-ink-primary">{title}</h2>
      {subtitle && (
        <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px] leading-[1.45] mt-1">{subtitle}</p>
      )}
    </div>
  )
}

// ── Verdict stamp ─────────────────────────────────────────────────────────────

function VerdictStamp({ verdict }: { verdict: string }) {
  const cls =
    verdict === 'Overweight' ? 'bg-signal-pos text-paper'
    : verdict === 'Underweight' || verdict === 'Avoid' ? 'bg-signal-neg text-paper'
    : 'bg-signal-warn/15 text-signal-warn border border-signal-warn/30'
  const label =
    verdict === 'Overweight' ? `OVERWEIGHT`
    : verdict === 'Underweight' ? 'UNDERWEIGHT'
    : verdict === 'Avoid' ? 'AVOID'
    : verdict.toUpperCase()

  return (
    <span className={`font-mono text-[11px] px-[9px] py-[3px] rounded-[2px] font-semibold tracking-[0.06em] ${cls}`}>
      {label}
    </span>
  )
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function Skeleton({ h = 48 }: { h?: number }) {
  return (
    <div
      style={{ height: h }}
      className="bg-paper-rule/20 rounded-sm animate-pulse"
      aria-hidden="true"
    />
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default async function SectorDetailPage({
  params,
}: {
  params: Promise<{ sector: string }>
}) {
  const { sector } = await params
  const decoded = decodeURIComponent(sector)

  const deepdive = await getSectorDeepdive(decoded)

  if (!deepdive) notFound()

  return (
    <div className="max-w-[1400px] mx-auto">

      {/* Page header */}
      <section className="px-8 py-8 border-b border-paper-rule">
        {/* Breadcrumb */}
        <nav className="font-sans text-[12px] text-ink-tertiary mb-3" aria-label="Breadcrumb">
          <Link href="/" className="text-teal hover:underline no-underline">Atlas</Link>
          {' '}›{' '}
          <Link href="/sectors" className="text-teal hover:underline no-underline">Sectors</Link>
          {' '}›{' '}
          <span aria-current="page">{decoded}</span>
        </nav>

        {/* Title row */}
        <div className="flex items-baseline gap-4 flex-wrap mb-1.5">
          <h1 className="font-serif text-[44px] font-normal tracking-[-0.011em] text-ink-primary leading-[1.05]">
            {decoded}
          </h1>
          <VerdictStamp verdict={deepdive.verdict} />
          <span className="font-mono text-[12px] text-ink-tertiary">
            {deepdive.constituent_count} constituents
          </span>
        </div>

        <p className="font-sans text-[15px] text-ink-secondary max-w-[880px]">
          Sector deep-dive: multidim returns, RS grid vs Nifty 500 across 5 windows, top-30 constituent
          stocks ranked by composite conviction score, open signal calls, and strength distribution.
        </p>

        {/* Hero strip */}
        <Suspense fallback={<Skeleton h={80} />}>
          <SectorHeroStrip sector={deepdive} />
        </Suspense>
      </section>

      <DataSourceBanner source="live" asOf={deepdive.data_as_of} />

      {/* Section 0 — Multidim chart (v6.1 placeholder) */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="Multidim sector chart">
        <SectionHead
          title={`${decoded} · multidim view`}
          subtitle="Sector price + support/resistance + RS-signal diamonds + volume + 20D-MA in one frame. Requires sector OHLCV aggregate query (not yet in mv_sector_deepdive)."
        />
        <div className="bg-paper-soft border border-dashed border-ink-rule rounded-[2px] p-8 text-center">
          <div className="font-sans text-[13px] font-semibold text-ink-secondary mb-2">
            Coming in v6.1
          </div>
          <p className="font-sans text-[12px] text-ink-4 max-w-[560px] mx-auto leading-[1.55]">
            The multidim chart (price + S/R + RS-signal diamonds + volume + 20D-MA stacked)
            requires aggregated OHLCV for sector index members. This will be added as a separate
            query layer in v6.1 when sector OHLCV aggregation is wired into the MV pipeline.
          </p>
        </div>
      </section>

      {/* Section 1 — RS windows */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="RS windows vs baselines">
        <SectionHead
          title="RS vs the baselines · 5 windows"
          subtitle="Percentage-point spread between this sector and Nifty 500 over 5 time windows. Rank is relative to all sectors. Nifty 50, Gold, and S&P 500 baselines are deferred."
        />
        <Suspense fallback={<Skeleton h={200} />}>
          <RSWindowsTable sector={deepdive} />
        </Suspense>
      </section>

      {/* Section 2 — Top picks */}
      {deepdive.top_picks_top10.length > 0 && (
        <section className="px-8 py-9 border-b border-paper-rule" aria-label="Top picks">
          <SectionHead
            title="Top picks"
            subtitle="Stocks with the highest positive composite conviction score in this sector. Ranked by composite score descending."
          />
          <Suspense fallback={<Skeleton h={160} />}>
            <TopPicksPanel picks={deepdive.top_picks_top10} />
          </Suspense>
        </section>
      )}

      {/* Section 3 — Constituents table */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="Constituents">
        <SectionHead
          title={`Constituents · top 30`}
          subtitle="Stocks ranked by composite conviction score. Click column headers to re-sort. Returns already in percentage points from the MV."
        />
        <Suspense fallback={<Skeleton h={400} />}>
          <ConstituentsTable constituents={deepdive.constituents_top30} />
        </Suspense>
      </section>

      {/* Section 4 — Strength distribution */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="Strength distribution">
        <SectionHead
          title="Constituent strength distribution"
          subtitle="NTILE(5) on 3M absolute return within sector. Very Strong = top quintile, Very Weak = bottom quintile."
        />
        <div className="bg-paper border border-paper-rule rounded-[2px] p-5">
          <Suspense fallback={<Skeleton h={170} />}>
            <StrengthDistChart dist={deepdive.strength_dist} />
          </Suspense>
        </div>
      </section>

      {/* Section 5 — Open signals */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="Open signals">
        <SectionHead
          title="Open signals"
          subtitle="Active BUY / SELL signal calls in this sector with exit_date IS NULL. Sorted by signal date descending."
        />
        <Suspense fallback={<Skeleton h={120} />}>
          <OpenSignalsPanel signals={deepdive.open_signals} />
        </Suspense>
      </section>

      {/* Section — Sub-industry decomposition (v6.1 placeholder) */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="Sub-industry decomposition">
        <SectionHead
          title="Sub-industry decomposition"
          subtitle="Break the sector into sub-industries and rank by RS. Requires sub-industry classification column in atlas_universe_stocks."
        />
        <div className="bg-paper-soft border border-dashed border-ink-rule rounded-[2px] p-6 text-center">
          <div className="font-sans text-[13px] font-semibold text-ink-secondary mb-1">Coming in v6.1</div>
          <p className="font-sans text-[12px] text-ink-4 max-w-[520px] mx-auto leading-[1.55]">
            Sub-industry grouping requires a classification field in the universe table.
            Once available, each sub-industry will show its own RS grid and constituent count.
          </p>
        </div>
      </section>

      {/* Section — Atlas methodology (v6.1 placeholder) */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="Atlas methodology">
        <SectionHead
          title="Atlas methodology · why this verdict"
          subtitle="Explains the signal factors, thresholds, and regime adjustments that produced the current sector verdict."
        />
        <div className="bg-paper-soft border border-dashed border-ink-rule rounded-[2px] p-6 text-center">
          <div className="font-sans text-[13px] font-semibold text-ink-secondary mb-1">Coming in v6.1</div>
          <p className="font-sans text-[12px] text-ink-4 max-w-[520px] mx-auto leading-[1.55]">
            The methodology panel will show the exact thresholds from{' '}
            <code className="font-mono text-[11px]">atlas.atlas_thresholds</code>{' '}
            that drove this verdict, including regime adjustment factors and the composite scoring breakdown.
          </p>
        </div>
      </section>

      {/* Section — Cross-market comparison (v6.1 placeholder) */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="Cross-market comparison">
        <SectionHead
          title="Cross-market · how India compares globally"
          subtitle="India sector RS stacked against global peers (e.g., India Energy vs XLE, India IT vs QQQ). Requires global sector ETF mapping layer."
        />
        <div className="bg-paper-soft border border-dashed border-ink-rule rounded-[2px] p-6 text-center">
          <div className="font-sans text-[13px] font-semibold text-ink-secondary mb-1">Coming in v6.1</div>
          <p className="font-sans text-[12px] text-ink-4 max-w-[520px] mx-auto leading-[1.55]">
            Cross-market panels require a mapping table from India sector names to global ETF tickers
            (e.g., Energy → XLE, IT → QQQ), plus Stooq/yfinance ingest for those ETFs. Planned for v6.1.
          </p>
        </div>
      </section>

      {/* Macro overlay placeholder */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="Macro overlays">
        <SectionHead
          title="Macro overlays"
          subtitle="Crude oil, USD/INR, and global risk indicators overlaid with sector price. Deferred — requires macro query layer not yet in mv_sector_deepdive."
        />
        <div className="bg-paper-soft border border-dashed border-paper-rule rounded-[2px] p-6 text-center">
          <p className="font-sans text-[13px] text-ink-tertiary">
            Macro overlays are planned. The Energy sector will show crude oil + USD/INR panels;
            IT will show DXY + US10Y. This requires a separate macro time-series query layer
            which is not yet wired to the sector deep-dive MV.
          </p>
        </div>
      </section>

      {/* Footer */}
      <div className="px-8 py-6 font-sans text-[12px] text-ink-tertiary leading-[1.6]">
        Data from{' '}
        <strong className="text-ink-secondary">atlas.mv_sector_deepdive</strong>{' '}
        — latest snapshot only, refreshed nightly at 20:55 IST via pg_cron.{' '}
        <Link href="/sectors" className="text-teal hover:underline">
          ← Back to Sectors list
        </Link>
      </div>

    </div>
  )
}
