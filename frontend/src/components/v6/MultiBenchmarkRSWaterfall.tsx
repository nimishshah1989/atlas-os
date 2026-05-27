'use client'

/**
 * MultiBenchmarkRSWaterfall.tsx
 *
 * Signed-bar waterfall: Gold (opt) → Nifty 50 → Nifty 500 → Cohort → Stock
 * with attribution cascade summary above the chart.
 *
 * Input convention: all return values are in percentage points
 * (18.4 = 18.4 %, NOT 0.184). `toNumber` is used at the prop boundary.
 *
 * Attribution:
 *   nifty500 beats nifty50 by: nifty50_return − nifty500_return
 *   cohort adds on top of 500: nifty500_return − cohort_return
 *   stock adds on top of cohort: cohort_return
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import { toNumber } from '@/lib/v6/decimal'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type WaterfallInput = {
  /** Returns in % (stringified Decimals from the query layer) */
  stock_return: string
  cohort_return: string
  nifty50_return: string
  nifty500_return: string
  gold_return: string | null
  tenure: '1m' | '3m' | '6m' | '12m'
}

export interface MultiBenchmarkRSWaterfallProps {
  data: WaterfallInput
  className?: string
}

// ---------------------------------------------------------------------------
// Color tokens (used both inline and as data-* attributes for tests)
// ---------------------------------------------------------------------------

export const FILL_POS = 'signal-pos'
export const FILL_NEG = 'signal-neg'

function fillColor(v: number): string {
  return v >= 0
    ? 'var(--color-signal-pos, #1a7f64)'
    : 'var(--color-signal-neg, #c0392b)'
}

// ---------------------------------------------------------------------------
// Attribution helpers
// ---------------------------------------------------------------------------

function signedPp(delta: number, d = 1): string {
  const abs = Math.abs(delta).toFixed(d)
  return delta >= 0 ? `+${abs}pp` : `-${abs}pp`
}

export function buildAttributionSentence(
  stock: number,
  cohort: number,
  nifty500: number,
  nifty50: number,
): string {
  const benchmarkDelta = nifty50 - nifty500  // nifty500 outperformed nifty50 by this
  const cohortDelta    = nifty500 - cohort   // cohort added on top of nifty500
  const stockDelta     = cohort              // stock added on top of cohort

  return (
    `Nifty 500 beat Nifty 50 by ${signedPp(benchmarkDelta)} → ` +
    `Cohort added ${signedPp(cohortDelta)} → ` +
    `Stock added ${signedPp(stockDelta)} on top`
  )
}

// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------

interface TPayload {
  value: number
  payload: { label: string }
}

function WaterfallTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: TPayload[]
}) {
  if (!active || !payload?.length) return null
  const { value, payload: row } = payload[0]
  const abs = Math.abs(value).toFixed(1)
  const formatted = value >= 0 ? `+${abs}%` : `-${abs}%`
  return (
    <div className="bg-paper border border-paper-rule px-3 py-2 rounded-sm shadow-sm text-[11px] font-sans">
      <p className="text-ink-secondary">{row?.label}</p>
      <p className="font-mono tabular-nums font-semibold mt-0.5">{formatted}</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

type BarRow = { label: string; value: number; fillType: string }

export function MultiBenchmarkRSWaterfall({
  data,
  className = '',
}: MultiBenchmarkRSWaterfallProps) {
  // Convert all string returns → numbers at the prop boundary
  const stockNum    = toNumber(data.stock_return)    ?? 0
  const cohortNum   = toNumber(data.cohort_return)   ?? 0
  const nifty50Num  = toNumber(data.nifty50_return)  ?? 0
  const nifty500Num = toNumber(data.nifty500_return) ?? 0
  const goldNum     = toNumber(data.gold_return)

  // Bar order: Gold (if present), Nifty 50, Nifty 500, Cohort, Stock
  const bars: BarRow[] = []
  if (goldNum !== null) {
    bars.push({ label: 'Gold',      value: goldNum,     fillType: goldNum     >= 0 ? FILL_POS : FILL_NEG })
  }
  bars.push({ label: 'Nifty 50',  value: nifty50Num,  fillType: nifty50Num  >= 0 ? FILL_POS : FILL_NEG })
  bars.push({ label: 'Nifty 500', value: nifty500Num, fillType: nifty500Num >= 0 ? FILL_POS : FILL_NEG })
  bars.push({ label: 'Cohort',    value: cohortNum,   fillType: cohortNum   >= 0 ? FILL_POS : FILL_NEG })
  bars.push({ label: 'Stock',     value: stockNum,    fillType: stockNum    >= 0 ? FILL_POS : FILL_NEG })

  const attribution = buildAttributionSentence(
    stockNum, cohortNum, nifty500Num, nifty50Num,
  )

  const ariaLabel =
    `Relative strength waterfall for ${data.tenure} tenure: stock vs cohort, Nifty 50, Nifty 500` +
    (goldNum !== null ? ', Gold' : '')

  return (
    <div
      className={`bg-paper rounded-md border border-paper-rule p-4 ${className}`}
      aria-label={ariaLabel}
    >
      {/* Attribution cascade summary */}
      <p
        data-testid="attribution-summary"
        className="text-[12px] text-ink-secondary font-sans mb-4 leading-snug"
      >
        {attribution}
      </p>

      <ResponsiveContainer width="100%" height={220}>
        <BarChart
          data={bars}
          layout="vertical"
          margin={{ top: 4, right: 28, bottom: 4, left: 72 }}
        >
          <XAxis
            type="number"
            tickFormatter={(v: number) =>
              `${v > 0 ? '+' : ''}${v.toFixed(1)}%`
            }
            tick={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              fill: 'var(--color-ink-tertiary)',
            }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            type="category"
            dataKey="label"
            width={68}
            tick={{
              fontFamily: 'var(--font-sans)',
              fontSize: 11,
              fill: 'var(--color-ink-secondary)',
            }}
            tickLine={false}
            axisLine={false}
          />
          <ReferenceLine
            x={0}
            stroke="var(--color-paper-rule)"
            strokeWidth={1}
          />
          <Tooltip
            content={<WaterfallTooltip />}
            cursor={{ fill: 'var(--color-paper-rule)', opacity: 0.3 }}
          />
          <Bar dataKey="value" isAnimationActive={false} radius={[0, 2, 2, 0]}>
            {bars.map((entry) => (
              <Cell
                key={entry.label}
                fill={fillColor(entry.value)}
                data-fill-type={entry.fillType}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
