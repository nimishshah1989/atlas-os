'use client'
import { BarChart2 } from 'lucide-react'
import { SectionHeader } from '@/components/regime/SectionHeader'
import { CategorySummary } from '@/components/regime/CategorySummary'
import { IndicatorChart } from '@/components/regime/IndicatorChart'
import type { GlobalRegimeRow, GlobalRegimeHistoryRow, CountryRow } from '@/lib/queries/global'

type Props = {
  current: GlobalRegimeRow
  history: GlobalRegimeHistoryRow[]
  countries: CountryRow[]
}

const f = (s: string | null | undefined): number => (s == null ? 0 : parseFloat(s))

const dateStr = (row: GlobalRegimeHistoryRow): string =>
  String(row.date).slice(0, 10)

// Quintile badge colours
const QUINTILE_COLORS: Record<number, { bg: string; text: string }> = {
  1: { bg: 'bg-signal-pos/10',  text: 'text-signal-pos' },
  2: { bg: 'bg-teal-500/10',    text: 'text-teal-600' },
  3: { bg: 'bg-amber-500/10',   text: 'text-amber-600' },
  4: { bg: 'bg-orange-500/10',  text: 'text-orange-600' },
  5: { bg: 'bg-signal-neg/10',  text: 'text-signal-neg' },
}

export function GlobalBreadthSection({ current, history, countries }: Props) {
  const pct50  = f(current.pct_countries_above_50dma)
  const pct200 = f(current.pct_countries_above_200dma)
  const total  = countries.length || 1

  // Q distribution from country data
  const q1Count    = countries.filter((c) => c.q_3m_vt === 1).length
  const q2Count    = countries.filter((c) => c.q_3m_vt === 2).length
  const q1q2Count  = q1Count + q2Count

  // 4 bullish signals
  const bullishSignals = [
    pct50  > 0.5,
    pct200 > 0.5,
    q1Count / total > 0.3,
    q1q2Count / total > 0.5,
  ]
  const bullishCount = bullishSignals.filter(Boolean).length
  const totalCount   = bullishSignals.length

  const pct50str  = `${(pct50 * 100).toFixed(0)}%`
  const pct200str = `${(pct200 * 100).toFixed(0)}%`
  const breadthLabel =
    bullishCount >= 3 ? 'BREADTH IS EXPANDING' :
    bullishCount >= 2 ? 'BREADTH IS MIXED' :
    'BREADTH IS CONTRACTING'
  const breadthSummary =
    `${pct50str} of ${total} country ETFs are above their 50-day MA and ${pct200str} above the 200-day. ` +
    `${q1Count} countries in Q1 (top quintile) vs VT; ${q1q2Count} in Q1/Q2 combined. ` +
    (bullishCount >= 3
      ? 'Country breadth is healthy — the global advance has genuine depth.'
      : bullishCount >= 2
        ? 'Mixed breadth — some countries leading but overall participation is thin.'
        : 'Country breadth is contracting — the advance is concentrated in a few names.')

  const pct50Data = history.map((row) => ({
    date: dateStr(row),
    value: row.pct_countries_above_50dma != null ? parseFloat(row.pct_countries_above_50dma) : null,
  }))

  const pct200Data = history.map((row) => ({
    date: dateStr(row),
    value: row.pct_countries_above_200dma != null ? parseFloat(row.pct_countries_above_200dma) : null,
  }))

  // Q distribution counts for display
  const qCounts = [1, 2, 3, 4, 5].map((q) => ({
    q,
    count: countries.filter((c) => c.q_3m_vt === q).length,
  }))
  const qNull = countries.filter((c) => c.q_3m_vt == null).length

  return (
    <section>
      <SectionHeader
        icon={<BarChart2 className="w-4 h-4" strokeWidth={2} />}
        title="Breadth"
        description="Country breadth measures how many of the 30 country ETFs are participating in the global advance. A rally driven by a handful of large developed-market countries while most ETFs decline is fragile and unsustainable. When breadth is strong — the majority of countries above their moving averages, most in Q1/Q2 vs VT — the global trend has genuine depth and is more likely to persist."
        bullishCount={bullishCount}
        totalCount={totalCount}
      />

      <CategorySummary
        bullishCount={bullishCount}
        totalCount={totalCount}
        headline={breadthLabel}
        summary={breadthSummary}
      />

      <div className="px-6 pb-6 pt-4 space-y-4">
        {/* Row 1: MA participation charts */}
        <div className="grid grid-cols-2 gap-4">
          <IndicatorChart
            title="% Country ETFs Above 50-day MA"
            description="The benchmark global breadth indicator. Above 50% means the majority of country ETFs are in medium-term uptrends. When this falls below 40%, global market health is narrowing — reduce international exposure."
            currentValue={`${(pct50 * 100).toFixed(1)}%`}
            isBullish={pct50 > 0.5}
            data={pct50Data}
            refLine={0.5}
            refLabel="50%"
            variant="area"
            yFormat="pct"
          />
          <IndicatorChart
            title="% Country ETFs Above 200-day MA"
            description="Long-term global participation quality. When most country ETFs are above their 200-day average, the world market cycle is in a healthy expansion. Below 40% defines a structural global bear environment regardless of where VT trades."
            currentValue={`${(pct200 * 100).toFixed(1)}%`}
            isBullish={pct200 > 0.5}
            data={pct200Data}
            refLine={0.5}
            refLabel="50%"
            variant="area"
            yFormat="pct"
          />
        </div>

        {/* Row 2: Q distribution */}
        <div className="border border-paper-rule rounded-sm p-5">
          <div className="flex items-start justify-between mb-3">
            <span className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary">
              Country RS Quintile Distribution vs VT (3M)
            </span>
            <span className={`font-sans text-[10px] font-medium ${q1q2Count / total > 0.5 ? 'text-signal-pos' : q1q2Count / total > 0.3 ? 'text-amber-500' : 'text-signal-neg'}`}>
              {q1q2Count}/{total} in Q1/Q2
            </span>
          </div>
          <p className="font-sans text-xs text-ink-tertiary leading-relaxed mb-4">
            Distribution of 30 country ETFs across relative-strength quintiles vs VT on a 3-month basis. Q1 = strongest outperformers. Q5 = weakest underperformers. High Q1/Q2 concentration = broad participation.
          </p>
          <div className="flex items-end gap-3">
            {qCounts.map(({ q, count }) => {
              const colors = QUINTILE_COLORS[q] ?? { bg: 'bg-paper-rule', text: 'text-ink-tertiary' }
              return (
                <div key={q} className="flex flex-col items-center gap-1.5 flex-1">
                  <span className={`font-mono text-sm font-semibold ${colors.text}`}>{count}</span>
                  <div className={`w-full rounded-sm py-1 text-center ${colors.bg}`}>
                    <span className={`font-sans text-[10px] font-medium ${colors.text}`}>Q{q}</span>
                  </div>
                </div>
              )
            })}
            {qNull > 0 && (
              <div className="flex flex-col items-center gap-1.5 flex-1">
                <span className="font-mono text-sm font-semibold text-ink-tertiary">{qNull}</span>
                <div className="w-full rounded-sm py-1 text-center bg-paper-rule/30">
                  <span className="font-sans text-[10px] font-medium text-ink-tertiary">N/A</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
