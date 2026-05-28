'use client'
// allow-large: page coordinator — 6 sections + Recharts line chart; splitting would require prop drilling

import type { ReactNode } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'

// frontend/src/components/v6/calls/CallsClient.tsx
//
// Main client component for /calls (Page 08 — Calls Performance).
// Receives all server-fetched data; coordinates interactive sections.
//
// Sections (per mockup 08-calls-performance.html):
//   1. Hero stats strip (6 tiles)
//   2. Realized win-rate matrix (24 cells — real data from mv_calls_performance)
//   3. Cell realized-excess trajectories (6-cell strip)
//   4. Six cells worth a click (3 best + 3 worst)
//   5. Cumulative avg realized excess line chart (M5)
//   6. All calls ledger (full table, 587 rows, virtualized)
//
// C4: Removed misleading "earliest 30 days from data_as_of for 1m calls" text.
//     Status is shown via mv_calls_performance.status column instead.

import type {
  CallsHero,
  CallRow,
  WinRateCell,
  TopSixResult,
  TopCell,
  CumulativeExcessPoint,
} from '@/lib/queries/v6/calls'
import { fmtSignedPct } from '@/lib/format-number'
import { CallsHeroStrip } from './CallsHeroStrip'
import { WinRateMatrix } from './WinRateMatrix'
import { CellTrajectories } from './CellTrajectories'
import { SixCellCards } from './SixCellCards'
import { CallsLedger } from './CallsLedger'

interface CallsClientProps {
  hero: CallsHero
  ledger: CallRow[]
  matrix: WinRateCell[]
  /** Pre-split {best: [3], worst: [3]} — C3 */
  topSix: TopSixResult
  allCells: TopCell[]
  excessSeries: CumulativeExcessPoint[]
}

function Section({
  title,
  sub,
  children,
}: {
  title: string
  sub?: string
  children: ReactNode
}) {
  return (
    <section className="py-9 border-b border-paper-rule last:border-b-0">
      <div className="max-w-[1400px] mx-auto px-8">
        <div className="flex items-baseline justify-between mb-5 flex-wrap gap-3">
          <div>
            <h2 className="font-serif text-[28px] font-normal tracking-[-0.011em] text-ink-primary">
              {title}
            </h2>
            {sub && (
              <p className="text-[13px] text-ink-4 max-w-[800px] leading-[1.45] mt-1">{sub}</p>
            )}
          </div>
        </div>
        {children}
      </div>
    </section>
  )
}

/** M5: Cumulative avg realized excess line chart */
function CumulativeExcessChart({ series }: { series: CumulativeExcessPoint[] }) {
  if (series.length === 0) {
    return (
      <div className="h-[200px] flex items-center justify-center text-ink-4 text-sm">
        No daily excess data available
      </div>
    )
  }

  // Build chart data with % values for display
  const chartData = series.map((pt) => ({
    date: pt.entry_date,
    excess: pt.avg_realized_excess != null ? +(pt.avg_realized_excess * 100).toFixed(2) : null,
  }))

  const allValues = chartData.map((d) => d.excess).filter((v): v is number => v != null)
  const minVal = Math.min(...allValues, 0)
  const maxVal = Math.max(...allValues, 0)

  return (
    <div className="border border-paper-rule rounded-[2px] bg-paper p-5">
      <div className="flex items-baseline gap-3 mb-4">
        <h3 className="font-serif text-[18px] text-ink-primary">
          Avg realized excess by entry date
        </h3>
        <span className="text-[12px] text-ink-4 font-mono">
          {series.length} date points · all calls
        </span>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-paper-rule, #E5E5E5)" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: 'var(--color-ink-tertiary, #9CA3AF)' }}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 10, fill: 'var(--color-ink-tertiary, #9CA3AF)' }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v) => `${v > 0 ? '+' : ''}${v.toFixed(1)}%`}
            domain={[Math.floor(minVal * 10) / 10 - 0.5, Math.ceil(maxVal * 10) / 10 + 0.5]}
          />
          <ReferenceLine y={0} stroke="var(--color-ink-rule, #D1D5DB)" strokeWidth={1} />
          <RechartsTooltip
            contentStyle={{
              background: 'var(--color-paper, #FFFFFF)',
              border: '1px solid var(--color-paper-rule, #E5E5E5)',
              borderRadius: '2px',
              fontSize: 12,
            }}
            formatter={(value: unknown) => {
              const num = typeof value === 'number' ? value : 0
              return [fmtSignedPct(num / 100), 'Avg realized excess']
            }}
            labelFormatter={(label: unknown) => `Entry date: ${String(label)}`}
          />
          <Line
            type="monotone"
            dataKey="excess"
            stroke="var(--color-accent, #1D9E75)"
            strokeWidth={1.5}
            dot={false}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
      <p className="mt-2 text-[10px] text-ink-4 font-mono">
        Each point = avg realized excess of all calls fired on that date · null dates excluded
      </p>
    </div>
  )
}

export function CallsClient({
  hero,
  ledger,
  matrix,
  topSix,
  allCells,
  excessSeries,
}: CallsClientProps) {
  return (
    <div className="min-h-screen bg-paper">
      {/* Page header */}
      <section className="py-8 border-b border-paper-rule">
        <div className="max-w-[1400px] mx-auto px-8">
          <nav className="text-[12px] text-ink-4 mb-3">
            <span className="text-accent">Atlas</span> › Calls Performance
          </nav>
          <div className="flex items-baseline gap-4 flex-wrap mb-2">
            <h1 className="font-serif text-[44px] font-normal tracking-[-0.011em] text-ink-primary leading-none">
              Calls Performance
            </h1>
            <span className="font-mono text-[12px] text-ink-4">
              {hero.total_calls.toLocaleString('en-IN')} calls ·{' '}
              {hero.open_calls.toLocaleString('en-IN')} in flight ·{' '}
              {hero.closed_calls.toLocaleString('en-IN')} closed
            </span>
          </div>
          <p className="text-[15px] text-ink-secondary max-w-[920px]">
            The accountability page. Every{' '}
            <strong>signal_call</strong> Atlas has fired, tracked from T+1 against its tier-anchor
            benchmark. Realized win rate, avg excess, cell trajectories by tier × tenure × direction.
            Read this page to know whether the methodology is earning its keep.
          </p>

          <CallsHeroStrip hero={hero} />
        </div>
      </section>

      {/* Section 2: Realized win-rate matrix */}
      <Section
        title="Realized win-rate matrix"
        sub="The 24-cell realized win-rate matrix — three tiers, four tenures, POSITIVE/NEGATIVE direction. Color-coded by win rate (% of calls that beat tier-anchor benchmark). 576 of 587 calls have realized data."
      >
        {/* C4: Removed misleading "earliest 30 days from data_as_of" text.
            Status is shown via status column from the MV instead. */}
        <WinRateMatrix cells={matrix} />
      </Section>

      {/* Section 3: Cell trajectories */}
      <Section
        title="Cell realized-excess trajectories"
        sub="Top 6 cells by avg realized excess. Each row shows win rate, avg realized excess, and whether the cell is below 40% win rate (drift-flagged)."
      >
        <CellTrajectories cells={allCells.slice(0, 6)} />
      </Section>

      {/* Section 4: Six cells worth a click */}
      <Section
        title="Six cells worth a click"
        sub="Top 3 cells by avg realized excess (best performers) and bottom 3 (worst — watching for drift). Each card shows win rate, realized excess, call count, and in-flight count."
      >
        <SixCellCards topSix={topSix} />
      </Section>

      {/* Section 5: Cumulative excess line chart (M5) */}
      <Section
        title="Avg realized excess by entry date"
        sub="Daily average realized excess across all calls fired on each date. Shows whether more recent calls are performing better or worse than older ones."
      >
        <CumulativeExcessChart series={excessSeries} />
      </Section>

      {/* Section 6: Full ledger */}
      <Section
        title={`All calls · ${hero.total_calls.toLocaleString('en-IN')}-row ledger`}
        sub="The full signal_call ledger from mv_calls_performance. Filter by status, direction, or search by symbol/company. Realized excess and win/loss shown for all 576 calls with data. Virtual scroll renders all rows."
      >
        <CallsLedger calls={ledger} />
      </Section>

      {/* Footnote */}
      <div className="max-w-[1400px] mx-auto px-8 py-6 pb-12 text-[12px] text-ink-4 leading-relaxed">
        <p>
          <strong className="text-ink-secondary">Data source:</strong>{' '}
          atlas.mv_calls_performance (587 rows · refreshed nightly).
          Win rate = % of calls where stock_ret_pct beat bench_ret_pct over the tenure window.
          Realized excess = stock_ret_pct − bench_ret_pct.
          Ticker/company from MV (no JOIN required).{' '}
          <strong className="text-ink-secondary">Methodology:</strong> Calls = POSITIVE/NEGATIVE
          conviction verdicts above friction threshold. POSITIVE → BUY, NEGATIVE → AVOID (per
          CONTEXT.md §Cell display name).
        </p>
      </div>
    </div>
  )
}
