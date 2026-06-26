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
import { SectorTraderViewHeader } from '@/components/v6/sectors/SectorTraderViewHeader'
import { RSWindowsTable } from '@/components/v6/sectors/RSWindowsTable'
import { SectorRSRatioCharts } from '@/components/v6/sectors/SectorRSRatioCharts'
import { ConstituentsTable } from '@/components/v6/sectors/ConstituentsTable'
import { TopPicksPanel } from '@/components/v6/sectors/TopPicksPanel'
import { StrengthDistChart } from '@/components/v6/sectors/StrengthDistChart'
import { OpenSignalsPanel } from '@/components/v6/sectors/OpenSignalsPanel'
import { getSectorDeepdive } from '@/lib/queries/v6/sectors'
import { getSectorRatioSeries } from '@/lib/queries/v6/sector_index_rs'
import { LENS_V4_ENABLED } from '@/lib/feature-flags'
import { SectorDeepDiveV4 } from '@/components/v6/sectors/SectorDeepDiveV4'

export const revalidate = 300

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

  // v4: revamped lens-first deep-dive (native foundation_staging)
  if (LENS_V4_ENABLED) return <SectorDeepDiveV4 sector={decoded} />

  const [deepdive, ratioSeries] = await Promise.all([
    getSectorDeepdive(decoded),
    getSectorRatioSeries(decoded),
  ])

  if (!deepdive) notFound()

  // Index-basis (cap-weighted) figures for this sector — replaces the legacy
  // equal-weighted MV returns that over-counted micro-caps.
  const bases = returnBases.sectors.find((s) => s.sector_name === decoded) ?? null
  // Headline figures: prefer the official cap-weighted index; fall back to the
  // free-float bottom-up where the NSE index price series is too sparse, so the
  // hero never shows "—" or a wrong number.
  const ix = bases?.index
  const bu = bases?.bottomup
  const n500 = returnBases.nifty500
  const pick = (k: 'ret_3m' | 'ret_12m') => ix?.[k] ?? bu?.[k] ?? null
  const headRet3m = pick('ret_3m')
  const headRet12m = pick('ret_12m')
  const pct = (v: number | null | undefined) => (v == null ? null : v * 100)
  const heroRet12m = pct(headRet12m)
  const heroRet3m = pct(headRet3m)
  const heroRs3m =
    headRet3m != null && n500.ret_3m != null ? (headRet3m - n500.ret_3m) * 100 : null

  return (
    <div className="max-w-[1400px] mx-auto">

      {/* Trader-view verdict header — index-basis 3M return + RS (fractions) */}
      <SectorTraderViewHeader
        sector={deepdive}
        ret3mOverride={headRet3m}
        rs3mOverride={headRet3m != null && n500.ret_3m != null ? headRet3m - n500.ret_3m : null}
      />

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
          Sector deep-dive: returns &amp; RS vs Nifty 500 across six windows (Index / Bottom-up basis),
          top-30 constituent stocks ranked by composite conviction score, open signal calls, and strength distribution.
        </p>

        {/* Hero strip — return tiles use the cap-weighted index basis */}
        <Suspense fallback={<Skeleton h={80} />}>
          <SectorHeroStrip
            sector={deepdive}
            ret12mOverride={heroRet12m}
            ret3mOverride={heroRet3m}
            rs3mOverride={heroRs3m}
          />
        </Suspense>
      </section>

      <DataSourceBanner source="live" asOf={deepdive.data_as_of} />

      {/* Section 1 — RS windows */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="RS windows vs baselines">
        <SectionHead
          title="RS vs the baselines · 5 windows"
          subtitle="Percentage-point spread between this sector and Nifty 500 over 5 time windows. Rank is relative to all sectors."
        />
        <Suspense fallback={<Skeleton h={360} />}>
          <SectorRSRatioCharts
            sectorName={decoded}
            indexCode={ratioSeries.index_code}
            daily={ratioSeries.daily}
          />
        </Suspense>
      </section>

      {/* Section 1b — RS ratio charts (sector index / Nifty 50) */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="Relative strength ratio charts">
        <SectionHead
          title="Relative strength · sector vs Nifty 50"
          subtitle="Sector index divided by Nifty 50 across Daily / Weekly / Monthly intervals. A rising line means the sector is outperforming the broad market."
        />
        <Suspense fallback={<Skeleton h={360} />}>
          <SectorRSRatioCharts
            sectorName={decoded}
            indexCode={ratioSeries.index_code}
            daily={ratioSeries.daily}
          />
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

      {/* Section — Sub-industry decomposition (v6.1: now LIVE) */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="Sub-industry decomposition">
        <SectionHead
          title="Sub-industry decomposition"
          subtitle="Sector broken into sub-industries from atlas_universe_stocks.industry, ranked by avg RS-3M vs Nifty 500. Buy/avoid counts derived from open conviction signals."
        />
        {deepdive.sub_industries.length === 0 ? (
          <div className="bg-paper-soft border border-paper-rule rounded-[2px] p-4 text-center text-[12px] text-ink-tertiary">
            No sub-industry classification for this sector.
          </div>
        ) : (
          <div className="overflow-x-auto border border-paper-rule rounded-[2px]">
            <table className="w-full font-sans text-[12.5px]">
              <thead className="bg-paper-soft border-b border-paper-rule">
                <tr>
                  <th className="text-left px-4 py-2 font-semibold text-ink-secondary tracking-wide">Sub-industry</th>
                  <th className="text-right px-4 py-2 font-semibold text-ink-secondary tracking-wide">Stocks</th>
                  <th className="text-right px-4 py-2 font-semibold text-ink-secondary tracking-wide">Avg RS 3M (pp)</th>
                  <th className="text-right px-4 py-2 font-semibold text-ink-secondary tracking-wide">Avg composite</th>
                  <th className="text-right px-4 py-2 font-semibold text-ink-secondary tracking-wide">BUY</th>
                  <th className="text-right px-4 py-2 font-semibold text-ink-secondary tracking-wide">AVOID</th>
                </tr>
              </thead>
              <tbody>
                {deepdive.sub_industries.map((s) => (
                  <tr key={s.industry} className="border-b border-paper-rule/60 last:border-b-0">
                    <td className="px-4 py-2 text-ink-primary">{s.industry}</td>
                    <td className="text-right px-4 py-2 font-mono text-ink-secondary">{s.n_stocks}</td>
                    <td className={`text-right px-4 py-2 font-mono ${
                      (s.avg_rs_3m_pp ?? 0) >= 0 ? 'text-signal-pos' : 'text-signal-neg'
                    }`}>
                      {s.avg_rs_3m_pp !== null ? `${s.avg_rs_3m_pp >= 0 ? '+' : ''}${s.avg_rs_3m_pp.toFixed(1)}` : '—'}
                    </td>
                    <td className={`text-right px-4 py-2 font-mono ${
                      (s.avg_composite_score ?? 0) >= 0 ? 'text-signal-pos' : 'text-signal-neg'
                    }`}>
                      {s.avg_composite_score !== null ? `${s.avg_composite_score >= 0 ? '+' : ''}${s.avg_composite_score.toFixed(2)}` : '—'}
                    </td>
                    <td className="text-right px-4 py-2 font-mono text-signal-pos">{s.n_buy || '—'}</td>
                    <td className="text-right px-4 py-2 font-mono text-signal-neg">{s.n_avoid || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Section — Atlas methodology · why this verdict (v6.1: now LIVE) */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="Atlas methodology">
        <SectionHead
          title="Atlas methodology · why this verdict"
          subtitle="Plain-English breakdown of the signal factors that produced the current sector verdict — derived from sector returns, RS vs Nifty 500, and breadth."
        />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {(() => {
            const ret3m = deepdive.returns?.ret_3m
            const ret6m = deepdive.returns?.ret_6m
            const rs3m = deepdive.rs_windows?.rs_3m
            const rs6m = deepdive.rs_windows?.rs_6m
            const breadth = deepdive.pct_above_ema21
            const verdict = deepdive.verdict
            const factors = [
              {
                label: 'Return trend',
                value: ret3m !== null && ret3m !== undefined
                  ? `${ret3m >= 0 ? '+' : ''}${ret3m.toFixed(1)}% / 3M  · ${ret6m !== null && ret6m !== undefined ? (ret6m >= 0 ? '+' : '') + ret6m.toFixed(1) + '% / 6M' : '—'}`
                  : '—',
                signal: ret3m !== null && ret3m !== undefined && ret3m >= 10 ? 'pos'
                      : ret3m !== null && ret3m !== undefined && ret3m <= -5 ? 'neg' : 'neu',
                note: ret3m !== null && ret3m !== undefined && ret3m >= 20 ? 'Strong outperformance vs flat market'
                    : ret3m !== null && ret3m !== undefined && ret3m >= 10 ? 'Positive trend confirmed'
                    : ret3m !== null && ret3m !== undefined && ret3m <= -5 ? 'Sector under pressure'
                    : 'Range-bound; watch for break',
              },
              {
                label: 'RS vs Nifty 500',
                value: rs3m !== null && rs3m !== undefined
                  ? `${rs3m >= 0 ? '+' : ''}${rs3m.toFixed(1)}pp / 3M  ·  ${rs6m !== null && rs6m !== undefined ? (rs6m >= 0 ? '+' : '') + rs6m.toFixed(1) + 'pp / 6M' : '—'}`
                  : '—',
                signal: rs3m !== null && rs3m !== undefined && rs3m >= 5 ? 'pos'
                      : rs3m !== null && rs3m !== undefined && rs3m <= -5 ? 'neg' : 'neu',
                note: rs3m !== null && rs3m !== undefined && rs3m >= 20 ? 'Sector is leading the market materially'
                    : rs3m !== null && rs3m !== undefined && rs3m >= 5 ? 'Outperforming the broad market'
                    : rs3m !== null && rs3m !== undefined && rs3m <= -5 ? 'Lagging the broad market'
                    : 'Tracking the market',
              },
              {
                label: 'Breadth (Above EMA20)',
                value: breadth !== null && breadth !== undefined
                  ? `${(breadth * 100).toFixed(0)}% of stocks above 20-day EMA`
                  : '—',
                signal: breadth !== null && breadth !== undefined && breadth >= 0.6 ? 'pos'
                      : breadth !== null && breadth !== undefined && breadth <= 0.4 ? 'neg' : 'neu',
                note: breadth !== null && breadth !== undefined && breadth >= 0.7 ? 'Broad-based participation — rally has depth'
                    : breadth !== null && breadth !== undefined && breadth >= 0.6 ? 'Healthy participation'
                    : breadth !== null && breadth !== undefined && breadth <= 0.4 ? 'Narrow participation — rally is thin'
                    : 'Mixed participation',
              },
              {
                label: 'Verdict alignment',
                value: verdict,
                signal: verdict === 'Overweight' ? 'pos'
                      : verdict === 'Underweight' || verdict === 'Avoid' ? 'neg' : 'neu',
                note: verdict === 'Overweight'
                  ? 'Trend + RS + breadth all positive — deploy capital'
                  : verdict === 'Neutral'
                  ? 'Mixed signals — maintain existing positions, no new adds'
                  : verdict === 'Underweight' || verdict === 'Avoid'
                  ? 'Multiple factors negative — reduce or avoid'
                  : 'Awaiting classification',
              },
            ]
            const sigCls = (s: string) => s === 'pos' ? 'border-l-signal-pos'
                                       : s === 'neg' ? 'border-l-signal-neg'
                                       : 'border-l-signal-warn'
            return factors.map((f) => (
              <div key={f.label} className={`border-l-4 ${sigCls(f.signal)} bg-paper-soft p-4 rounded-r-[2px]`}>
                <div className="font-sans text-[11px] font-semibold text-ink-tertiary uppercase tracking-[0.08em] mb-1">{f.label}</div>
                <div className="font-mono text-[14px] text-ink-primary mb-1">{f.value}</div>
                <div className="font-sans text-[12px] text-ink-tertiary leading-[1.45]">{f.note}</div>
              </div>
            ))
          })()}
        </div>
        <p className="font-sans text-[11px] text-ink-tertiary mt-4 leading-[1.55]">
          Inputs: bottomup return, RS spread vs Nifty 500, and % above EMA-20 from sector metrics. Verdict from sector states model.
        </p>
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
