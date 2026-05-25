'use client'

// RankDecompositionCards — composite score breakdown for fund / ETF / stock detail pages.
// Props transport all numeric values as strings (Postgres NUMERIC stringified).
// Conversion via toNumber() from lib/v6/decimal.ts happens only at the render boundary.

import { toNumber } from '@/lib/v6/decimal'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type RankComponent = {
  name: string
  raw_score: string
  percentile_in_category: string
  weight_pct: string
  delta_vs_cohort: string
}

export interface RankDecompositionCardsProps {
  composite_score: string
  components: RankComponent[]
  rank_in_category: number
  category_size: number
  className?: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Map percentile (0-100) to a quartile CSS class for chip background/text. */
function percentileClass(pctStr: string): string {
  const p = toNumber(pctStr) ?? 0
  if (p >= 75) return 'bg-signal-pos/20 text-signal-pos'
  if (p >= 50) return 'bg-signal-warn/20 text-signal-warn'
  if (p >= 25) return 'bg-signal-warn/40 text-signal-warn'
  return 'bg-signal-neg/20 text-signal-neg'
}

/** Ordinal suffix for rank display (1st, 2nd, 3rd, 4th…). */
function ordinal(n: number): string {
  const abs = Math.abs(n)
  const mod10 = abs % 10
  const mod100 = abs % 100
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`
  if (mod10 === 1) return `${n}st`
  if (mod10 === 2) return `${n}nd`
  if (mod10 === 3) return `${n}rd`
  return `${n}th`
}

/** Format a signed pp delta string, e.g. "5" → "+5.0 pp", "-3" → "-3.0 pp". */
function formatDeltaPP(deltaStr: string): string {
  const n = toNumber(deltaStr)
  if (n === null) return '—'
  const fixed = Math.abs(n).toFixed(1)
  if (n > 0) return `+${fixed} pp`
  if (n < 0) return `-${fixed} pp`
  return `0.0 pp`
}

/** Delta sign CSS class. */
function deltaClass(deltaStr: string): string {
  const n = toNumber(deltaStr) ?? 0
  if (n > 0) return 'text-signal-pos'
  if (n < 0) return 'text-signal-neg'
  return 'text-ink-secondary'
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ComponentCard({ component }: { component: RankComponent }) {
  const scoreNum = toNumber(component.raw_score) ?? 0
  const pctNum = toNumber(component.percentile_in_category) ?? 0
  const weightNum = toNumber(component.weight_pct) ?? 0

  const ariaLabel = [
    `${component.name}: score ${scoreNum.toFixed(1)},`,
    `percentile ${pctNum.toFixed(0)},`,
    `delta ${formatDeltaPP(component.delta_vs_cohort)}`,
  ].join(' ')

  return (
    <div
      className="flex-1 min-w-[160px] rounded-md border border-paper-rule bg-paper p-4 flex flex-col gap-2"
      aria-label={ariaLabel}
    >
      {/* Title */}
      <p className="text-xs font-medium text-ink-secondary leading-tight capitalize">
        {component.name}
      </p>

      {/* Big raw score */}
      <p className="text-2xl font-semibold text-ink-primary tabular-nums">
        {scoreNum.toFixed(2)}
      </p>

      {/* Percentile chip */}
      <span
        className={`inline-flex self-start items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${percentileClass(component.percentile_in_category)}`}
      >
        {pctNum.toFixed(0)}th percentile
      </span>

      {/* Delta vs cohort */}
      <p className={`text-xs font-medium ${deltaClass(component.delta_vs_cohort)}`}>
        {formatDeltaPP(component.delta_vs_cohort)} vs cohort median
      </p>

      {/* Weight chip */}
      <span className="inline-flex self-start items-center rounded-sm border border-paper-rule px-1.5 py-0.5 text-[11px] text-ink-tertiary">
        {weightNum.toFixed(0)}% weight
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function RankDecompositionCards({
  composite_score,
  components,
  rank_in_category,
  category_size,
  className = '',
}: RankDecompositionCardsProps) {
  const compositeNum = toNumber(composite_score) ?? 0

  return (
    <section className={`flex flex-col gap-4 ${className}`}>
      {/* Hero strip */}
      <div className="flex items-baseline gap-2 border-b border-paper-rule pb-3">
        <span className="text-2xl font-semibold text-ink-primary tabular-nums">
          {compositeNum.toFixed(1)}
        </span>
        <span className="text-sm text-ink-secondary">Composite</span>
        <span className="mx-2 text-ink-tertiary">·</span>
        <span className="text-sm text-ink-primary font-medium">
          Rank {ordinal(rank_in_category)} of {category_size}
        </span>
      </div>

      {/* Component cards row */}
      {components.length > 0 && (
        <div className="flex flex-wrap gap-3">
          {components.map((c) => (
            <ComponentCard key={c.name} component={c} />
          ))}
        </div>
      )}
    </section>
  )
}

export default RankDecompositionCards
