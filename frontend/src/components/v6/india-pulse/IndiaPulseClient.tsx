'use client'
// frontend/src/components/v6/india-pulse/IndiaPulseClient.tsx
//
// Client-side orchestrator for India Pulse page.
// Receives fully-typed server data, hands to section components.
// "use client" required because child components use Recharts.

import Link from 'next/link'
import type { IndiaPulsePageData } from '@/lib/queries/v6/india_pulse'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { HeroStrip } from './HeroStrip'
import { HeadlineIndices } from './HeadlineIndices'
import { BreadthTable } from './BreadthTable'
import { DispersionCharts } from './DispersionCharts'
import { VolatilitySection } from './VolatilitySection'
import { TierLeadership } from './TierLeadership'
import { SectorHeatmap } from './SectorHeatmap'
import { MacroCards } from './MacroCards'

type Props = {
  data: IndiaPulsePageData
}

export function IndiaPulseClient({ data }: Props) {
  const {
    as_of_date,
    smallcap_rs_z,
    breadth_pct_above_200dma,
    india_vix,
    cross_section_dispersion,
    vix_spot,
    vix_5y_pct,
    vix_term_structure,
    headline_indices,
    breadth_table,
    sector_heatmap,
    tier_leadership,
    dispersion_60d_series,
    macro_cards,
    narrative_ribbon,
  } = data

  return (
    <div className="min-h-screen bg-paper">
      {/* Data source banner */}
      <DataSourceBanner
        source="live"
        asOf={as_of_date ?? 'unknown'}
        hint="mv_india_pulse · nightly refresh at 20:30 IST"
      />

      {/* Page header */}
      <section className="border-b border-paper-rule pb-6">
        <div className="max-w-[1400px] mx-auto px-8 pt-8">
          <div className="text-[12px] text-ink-tertiary mb-3">
            <Link href="/" className="text-accent no-underline hover:underline">Atlas</Link>
            {' › '}India Pulse
          </div>
          <h1 className="font-serif text-[44px] font-normal tracking-[-0.011em] text-ink-primary leading-[1.1] mb-2">
            India Pulse
          </h1>
          <p className="text-[15px] text-ink-secondary max-w-[760px]">
            The four inputs to the regime classifier — plus the broader breadth, dispersion,
            volatility, and sectoral indices that contextualise the call. This is the page to come to
            when you want to verify the regime read for yourself.
          </p>

          {/* Hero strip */}
          <HeroStrip
            data={{ smallcap_rs_z, breadth_pct_above_200dma, india_vix, cross_section_dispersion }}
          />
        </div>
      </section>

      {/* Section 1 — Headline indices */}
      <section className="border-b border-paper-rule py-10">
        <div className="max-w-[1400px] mx-auto px-8">
          <div className="flex items-baseline justify-between mb-5">
            <div>
              <h2 className="font-serif text-[28px] font-normal tracking-[-0.011em] text-ink-primary">
                Headline indices
              </h2>
              <p className="text-[13px] text-ink-tertiary max-w-[720px] leading-[1.45] mt-1">
                Where each headline index sits today and across 1M / 3M / 6M, with RS vs the broad Nifty 500.
                Left-border tint = leadership stance.
              </p>
            </div>
          </div>
          <HeadlineIndices indices={headline_indices} />
        </div>
      </section>

      {/* Section 2 — Breadth */}
      <section className="border-b border-paper-rule py-10">
        <div className="max-w-[1400px] mx-auto px-8">
          <div className="flex items-baseline justify-between mb-5">
            <div>
              <h2 className="font-serif text-[28px] font-normal tracking-[-0.011em] text-ink-primary">
                Breadth
              </h2>
              <p className="text-[13px] text-ink-tertiary max-w-[720px] leading-[1.45] mt-1">
                How many stocks are participating? When breadth narrows, the index can keep rising while fewer
                names do the work. Δ columns are in percentage points (or count, where the row is a count).
              </p>
            </div>
          </div>
          <BreadthTable rows={breadth_table} />
        </div>
      </section>

      {/* Section 3 — Dispersion & concentration */}
      <section className="border-b border-paper-rule py-10">
        <div className="max-w-[1400px] mx-auto px-8">
          <div className="mb-5">
            <h2 className="font-serif text-[28px] font-normal tracking-[-0.011em] text-ink-primary">
              Dispersion &amp; concentration
            </h2>
            <p className="text-[13px] text-ink-tertiary max-w-[720px] leading-[1.45] mt-1">
              <strong className="text-ink-secondary">Dispersion</strong> measures how differently stocks
              are moving from each other. Together with sector RS, these tell you whether the headline
              number reflects a real broad-market move or a narrow few-stocks effect.
            </p>
          </div>
          <DispersionCharts
            dispersion_60d_series={dispersion_60d_series}
            sector_heatmap={sector_heatmap}
          />
        </div>
      </section>

      {/* Section 4 — Volatility */}
      <section className="border-b border-paper-rule py-10">
        <div className="max-w-[1400px] mx-auto px-8">
          <div className="mb-5">
            <h2 className="font-serif text-[28px] font-normal tracking-[-0.011em] text-ink-primary">
              Volatility
            </h2>
            <p className="text-[13px] text-ink-tertiary max-w-[720px] leading-[1.45] mt-1">
              India VIX in absolute terms, in percentile context, and as a term-structure curve.
              When VIX rises while spot stays flat, options markets are starting to hedge.
            </p>
          </div>
          <VolatilitySection data={{ vix_spot, vix_5y_pct, vix_term_structure }} />
        </div>
      </section>

      {/* Section 5 — Tier leadership */}
      <section className="border-b border-paper-rule py-10">
        <div className="max-w-[1400px] mx-auto px-8">
          <div className="mb-5">
            <h2 className="font-serif text-[28px] font-normal tracking-[-0.011em] text-ink-primary">
              Tier leadership · mid &amp; small vs large
            </h2>
            <p className="text-[13px] text-ink-tertiary max-w-[720px] leading-[1.45] mt-1">
              Small-cap leadership is one of the four canonical regime inputs. We track mid-cap alongside
              small-cap because the two often turn together — but when they diverge, that itself is a
              regime signal. Z-scores below are RS vs Nifty 100 anchor.
            </p>
          </div>
          <TierLeadership tier_leadership={tier_leadership} />
        </div>
      </section>

      {/* Section 6 — Sectoral heatmap */}
      <section className="border-b border-paper-rule py-10">
        <div className="max-w-[1400px] mx-auto px-8">
          <div className="mb-5">
            <h2 className="font-serif text-[28px] font-normal tracking-[-0.011em] text-ink-primary">
              Sectoral indices · heatmap
            </h2>
            <p className="text-[13px] text-ink-tertiary max-w-[720px] leading-[1.45] mt-1">
              {sector_heatmap.length} actionable sectors. Toggle the window — the heatmap re-ranks to
              that window (1W shows recent momentum, 3M shows the regime-relevant signal).
            </p>
          </div>
          <SectorHeatmap sectors={sector_heatmap} />
        </div>
      </section>

      {/* Section 7 — Macro context */}
      <section className="border-b border-paper-rule py-10">
        <div className="max-w-[1400px] mx-auto px-8">
          <div className="mb-5">
            <h2 className="font-serif text-[28px] font-normal tracking-[-0.011em] text-ink-primary">
              Macro context
            </h2>
            <p className="text-[13px] text-ink-tertiary max-w-[720px] leading-[1.45] mt-1">
              The forces pushing on equities from outside equities: currency, rates, oil, and flow.
              Eight indicators from <strong className="text-ink-secondary">India domestic</strong> to{' '}
              <strong className="text-ink-secondary">global / cross-asset</strong>, with a bond-vs-equity
              narrative below.
            </p>
          </div>
          <MacroCards macro_cards={macro_cards} narrative_ribbon={narrative_ribbon} />
        </div>
      </section>

      {/* Footnote */}
      <section className="max-w-[1400px] mx-auto px-8">
        <div className="py-6 text-[12px] text-ink-tertiary leading-[1.6]">
          Regime classifier is rule-based on four signals (small-cap RS Z, breadth % &gt; 200DMA, VIX percentile,
          cross-sectional dispersion) — see CONTEXT.md §Regime classifier thresholds. Macro context is sourced
          from NSE / RBI / FRED / NSDL FII-DII statements. For the cross-market context, open the{' '}
          <Link href="/markets-rs" className="text-accent hover:underline">Markets RS</Link> page; for the granular
          sector breakdown, open <Link href="/sectors" className="text-accent hover:underline">Sectors</Link>.
        </div>
      </section>
    </div>
  )
}
