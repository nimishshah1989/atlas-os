// src/lib/rule-catalogs.ts
// Frontend mirror of atlas/api/_rule_allowlist.py
// CRITICAL: values here MUST match the Python frozensets exactly.
// If you add a key to one without the other, security validation is broken.

export const RS_STATES = [
  'Leader',
  'Strong',
  'Consolidating',
  'Emerging',
  'Average',
  'Weak',
  'Laggard',
] as const

export const MOMENTUM_STATES = [
  'Accelerating',
  'Improving',
  'Flat',
  'Deteriorating',
  'Collapsing',
] as const

export const RISK_STATES = [
  'Low',
  'Normal',
  'Elevated',
  'High',
  'Below Trend',
] as const

export const VOLUME_STATES = [
  'Accumulation',
  'Steady-Buying',
  'Neutral',
  'Distribution',
  'Heavy Distribution',
] as const

export const SECTOR_STATES = [
  'Overweight',
  'Neutral',
  'Underweight',
  'Avoid',
] as const

export const REGIME_STATES = [
  'Risk-On',
  'Constructive',
  'Cautious',
  'Risk-Off',
] as const

export const POSITION_SIZING = [
  'equal_weight',
  'vol_target',
  'market_cap',
] as const

export const REBALANCE = [
  'signal_change',
  'weekly',
  'monthly',
] as const

export const BREADTH_GATES = [
  {
    key: 'pct_above_ema_50',
    label: 'Stocks above EMA-50',
    min: 0,
    max: 100,
    step: 1,
    fmt: 'pct',
    help: 'Percentage of universe trading above their 50-day EMA',
  },
  {
    key: 'ad_ratio',
    label: 'Advance / Decline ratio',
    min: 0,
    max: 3,
    step: 0.05,
    fmt: 'ratio',
    help: 'Ratio of advancing to declining stocks (latest day)',
  },
  {
    key: 'new_high_low_ratio',
    label: 'New highs / new lows ratio',
    min: 0,
    max: 5,
    step: 0.05,
    fmt: 'ratio',
    help: 'Ratio of stocks at 52w highs vs 52w lows',
  },
  {
    key: 'pct_in_strong_states',
    label: 'Pct in Leader/Strong states',
    min: 0,
    max: 1,
    step: 0.01,
    fmt: 'frac',
    help: 'Fraction of universe in Leader or Strong RS state',
  },
  {
    key: 'pct_weinstein_pass',
    label: 'Pct passing Weinstein gate',
    min: 0,
    max: 1,
    step: 0.01,
    fmt: 'frac',
    help: 'Fraction in Weinstein Stage 2 (price > 30wk MA + MA rising)',
  },
] as const

export type BreadthGateFmt = 'pct' | 'ratio' | 'frac'
export type BreadthGate = (typeof BREADTH_GATES)[number]

export type RsState = (typeof RS_STATES)[number]
export type MomentumState = (typeof MOMENTUM_STATES)[number]
export type RiskState = (typeof RISK_STATES)[number]
export type VolumeState = (typeof VOLUME_STATES)[number]
export type SectorState = (typeof SECTOR_STATES)[number]
export type RegimeState = (typeof REGIME_STATES)[number]
export type PositionSizing = (typeof POSITION_SIZING)[number]
export type RebalanceTrigger = (typeof REBALANCE)[number]

/** Format a breadth gate value for display */
export function formatBreadthValue(value: number, fmt: BreadthGateFmt): string {
  if (fmt === 'pct') return `${value.toFixed(0)}%`
  if (fmt === 'ratio') return value.toFixed(2)
  if (fmt === 'frac') return value.toFixed(2)
  return String(value)
}
