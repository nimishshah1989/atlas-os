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

// rule_dsl JSONB shape (per atlas/discovery output, verified live 2026-05-26):
//   { "cmp": ">=", "value": "16.5", "feature": "log_med_tv_60d" }
//   { "cmp": "in_top_quantile", "value": "1", "feature": "rs_residual_12m",
//     "value_quantile_n": 10 }
// Note: field names are `cmp` and `value`, NOT `op` and `threshold`.
export interface RulePredicate {
  feature: string
  cmp: string                            // canonical name in DB
  op?: string                            // accept legacy alias
  value?: number | string
  threshold?: number | string             // legacy alias
  value_quantile_n?: number               // for in_top_quantile / in_bottom_quantile
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
  realized_vol_60d: '60-day realized volatility',
  realized_vol_252d: '252-day realized volatility',
  beta: 'market beta',
  mcap_rank: 'market cap rank within universe',
  sector_rank: 'sector RS rank',
  rs_residual_12m: '12-month RS residual (beta-adjusted)',
  rs_residual_6m: '6-month RS residual (beta-adjusted)',
  rs_residual_3m: '3-month RS residual (beta-adjusted)',
  pct_from_52w_high: '% from 52-week high',
  pct_from_52w_low: '% from 52-week low',
  drawdown_from_peak: 'drawdown from peak',
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
  'in_top_quantile': 'in top quantile',
  'in_bottom_quantile': 'in bottom quantile',
}

function translateFeature(feature: string): string {
  return FEATURE_LABELS[feature] ?? feature.replace(/_/g, ' ')
}

function translateOp(op: string): string {
  return OP_WORDS[op] ?? op
}

function formatThreshold(threshold: number | string | undefined): string {
  if (threshold == null) return ''
  // JSONB serialises numerics as strings (e.g. "0.018", "16.5"). Coerce to
  // number for the magnitude-based precision rule, but fall back to the raw
  // string when it isn't parseable.
  const n = typeof threshold === 'number' ? threshold : Number(threshold)
  if (Number.isFinite(n)) {
    return Math.abs(n) < 1 ? n.toFixed(3) : n.toFixed(2)
  }
  return String(threshold)
}

function predicateToEnglish(pred: RulePredicate): string {
  // Accept both canonical (cmp/value) and legacy alias (op/threshold) shapes.
  const op = pred.cmp ?? pred.op ?? ''
  const featureLabel = translateFeature(pred.feature)
  const opWord = translateOp(op)
  const rawValue = pred.value ?? pred.threshold

  // Handle quantile / decile / quartile ops — append "of N" when value_quantile_n
  // is set (e.g. "in top quantile of 10" for top decile, "of 4" for top quartile).
  if (
    op === 'in_top_decile' ||
    op === 'in_bottom_decile' ||
    op === 'in_top_quartile' ||
    op === 'in_top_quantile' ||
    op === 'in_bottom_quantile'
  ) {
    if (pred.value_quantile_n) {
      return `${featureLabel} is ${opWord} of ${pred.value_quantile_n}`
    }
    return `${featureLabel} is ${opWord}`
  }

  const threshStr = formatThreshold(rawValue)
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
