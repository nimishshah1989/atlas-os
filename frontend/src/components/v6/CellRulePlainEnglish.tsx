// frontend/src/components/v6/CellRulePlainEnglish.tsx
//
// Renders atlas_cell_definitions.rule_dsl JSONB as plain-English predicates.
//
// rule_dsl shape (from atlas/discovery pipeline):
//   { entry: [ { feature: string, op: string, threshold: number, weight?: number }, ... ],
//     exit?: [ ... ] }
//
// Each predicate is translated deterministically using a keyword-match table.
// Unknown features fall back to the raw predicate string.
//
// LOC budget: ≤200

'use client'

import React from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface RulePredicate {
  feature: string
  op: string          // ">=", "<=", ">", "<", "==", "in_top_decile", etc.
  threshold?: number | string
  weight?: number
}

export interface RuleDsl {
  entry?: RulePredicate[]
  exit?: RulePredicate[]
}

interface Props {
  rule_dsl: Record<string, unknown>
  /** Show exit predicates section when true. Default: false */
  showExit?: boolean
  className?: string
}

// ---------------------------------------------------------------------------
// Deterministic feature translations
// ---------------------------------------------------------------------------

const FEATURE_LABELS: Record<string, string> = {
  log_med_tv_60d: 'log median 60-day traded value',
  rs_percentile: 'relative strength percentile vs universe',
  rs_percentile_cap: 'relative strength percentile within cap-tier',
  ema_distance_20: 'distance above 20-day EMA',
  ema_distance_50: 'distance above 50-day EMA',
  ema_distance_200: 'distance above 200-day EMA',
  rsi_14: 'RSI (14-day)',
  atr_pct_14: 'ATR % (14-day volatility)',
  obv_slope_60d: '60-day OBV slope',
  dist_above_sma50: 'distance above SMA-50',
  dist_above_sma200: 'distance above SMA-200',
  bb_pct_20d: 'Bollinger Band % position (20-day)',
  momentum_1m: '1-month momentum',
  momentum_3m: '3-month momentum',
  momentum_6m: '6-month momentum',
  momentum_12m: '12-month momentum',
  vol_60d: '60-day realized volatility',
  beta: 'market beta',
  mcap_rank: 'market cap rank within universe',
  sector_rank: 'sector RS rank',
}

const OP_WORDS: Record<string, string> = {
  '>=': '≥',
  '<=': '≤',
  '>':  '>',
  '<':  '<',
  '==': '=',
  'in_top_decile': 'in top decile',
  'in_bottom_decile': 'in bottom decile',
  'in_top_quartile': 'in top quartile',
}

function translateFeature(feature: string): string {
  return FEATURE_LABELS[feature] ?? feature.replace(/_/g, ' ')
}

function translateOp(op: string): string {
  return OP_WORDS[op] ?? op
}

function formatThreshold(threshold: number | string | undefined): string {
  if (threshold == null) return ''
  if (typeof threshold === 'number') {
    return Math.abs(threshold) < 1 ? threshold.toFixed(3) : threshold.toFixed(2)
  }
  return String(threshold)
}

function predicateToEnglish(pred: RulePredicate): string {
  const featureLabel = translateFeature(pred.feature)
  const opWord = translateOp(pred.op)

  // Handle in_top_decile / in_bottom_decile / in_top_quartile (no threshold)
  if (pred.op === 'in_top_decile' || pred.op === 'in_bottom_decile' || pred.op === 'in_top_quartile') {
    return `${featureLabel} is ${opWord}`
  }

  const threshStr = formatThreshold(pred.threshold)
  return `${featureLabel} ${opWord} ${threshStr}`.trim()
}

// ---------------------------------------------------------------------------
// PredicateRow
// ---------------------------------------------------------------------------

function PredicateRow({ pred, index }: { pred: RulePredicate; index: number }): React.ReactElement {
  const english = predicateToEnglish(pred)
  return (
    <li
      key={index}
      className="flex items-start gap-2 py-1 text-sm font-sans text-ink-primary leading-snug"
      aria-label={`Predicate ${index + 1}: ${english}`}
    >
      <span className="mt-0.5 text-teal text-[10px] font-semibold font-mono select-none w-4 shrink-0">
        {index + 1}.
      </span>
      <span>{english}</span>
      {pred.weight != null && (
        <span className="ml-auto text-[11px] font-mono text-ink-tertiary shrink-0 whitespace-nowrap">
          w={pred.weight.toFixed(2)}
        </span>
      )}
    </li>
  )
}

// ---------------------------------------------------------------------------
// CellRulePlainEnglish
// ---------------------------------------------------------------------------

export function CellRulePlainEnglish({
  rule_dsl,
  showExit = false,
  className = '',
}: Props): React.ReactElement {
  const dsl = rule_dsl as RuleDsl
  const entryPreds: RulePredicate[] = Array.isArray(dsl?.entry) ? dsl.entry : []
  const exitPreds: RulePredicate[] = Array.isArray(dsl?.exit) ? dsl.exit : []

  if (entryPreds.length === 0 && exitPreds.length === 0) {
    return (
      <p className="text-sm font-sans text-ink-tertiary italic" role="note">
        Rule predicates not available.
      </p>
    )
  }

  return (
    <div className={['space-y-4', className].filter(Boolean).join(' ')}>
      {entryPreds.length > 0 && (
        <section aria-label="Entry predicates">
          <h3 className="text-[11px] font-sans font-semibold uppercase tracking-[0.1em] text-ink-tertiary mb-1">
            Entry conditions
          </h3>
          <ol className="list-none m-0 p-0 space-y-0.5">
            {entryPreds.map((pred, i) => (
              <PredicateRow key={i} pred={pred} index={i} />
            ))}
          </ol>
        </section>
      )}
      {showExit && exitPreds.length > 0 && (
        <section aria-label="Exit predicates">
          <h3 className="text-[11px] font-sans font-semibold uppercase tracking-[0.1em] text-ink-tertiary mb-1">
            Exit conditions
          </h3>
          <ol className="list-none m-0 p-0 space-y-0.5">
            {exitPreds.map((pred, i) => (
              <PredicateRow key={i} pred={pred} index={i} />
            ))}
          </ol>
        </section>
      )}
    </div>
  )
}

export default CellRulePlainEnglish
