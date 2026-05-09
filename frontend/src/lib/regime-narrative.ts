import type { MarketRegimeRow } from '@/lib/queries/regime'

const f = (s: string | null | undefined): number => (s == null ? 0 : parseFloat(s))

export function getRegimeTintClass(state: string): string {
  if (state === 'Risk-On' || state === 'Constructive') return 'bg-signal-pos/5 border-signal-pos/20'
  if (state === 'Cautious') return 'bg-signal-warn/5 border-signal-warn/20'
  if (state === 'Risk-Off') return 'bg-signal-neg/5 border-signal-neg/20'
  return 'bg-accent/5 border-accent/20'
}

export function getRegimeAccentClass(state: string): string {
  if (state === 'Risk-On' || state === 'Constructive') return 'text-signal-pos'
  if (state === 'Cautious') return 'text-signal-warn'
  if (state === 'Risk-Off') return 'text-signal-neg'
  return 'text-accent'
}

export function getRegimeDotClass(state: string): string {
  if (state === 'Risk-On' || state === 'Constructive') return 'bg-signal-pos'
  if (state === 'Cautious') return 'bg-signal-warn'
  if (state === 'Risk-Off') return 'bg-signal-neg'
  return 'bg-accent'
}

// Data-driven description — actual numbers, not generic prose
export function getRegimeDescription(r: MarketRegimeRow): string {
  const state = r.regime_state
  const pctEma50 = f(r.pct_above_ema_50)
  const adRatio = f(r.ad_ratio)
  const mcOsc = f(r.mcclellan_oscillator)
  const mcSum = f(r.mcclellan_summation)
  const vix = f(r.india_vix)

  const pctStr = `${Math.round(pctEma50 * 100)}%`
  const adStr = adRatio.toFixed(2)
  const vixNote = vix > 25 ? ` VIX at ${vix.toFixed(1)} signals elevated fear.` : ''

  if (state === 'Risk-On') {
    return `${pctStr} of the Nifty 500 is above its 50-day EMA. Advances outnumber declines ${adStr}× and the McClellan Oscillator is positive. Broad participation supports the regime.`
  }
  if (state === 'Constructive') {
    return `${pctStr} above the 50-day EMA with A/D ratio at ${adStr}. Momentum building but not yet fully confirmed across all breadth signals.`
  }
  if (state === 'Cautious') {
    const momNote = mcOsc < 0 ? ` McClellan Oscillator at ${mcOsc.toFixed(0)} — breadth momentum has stalled.` : ''
    return `Breadth is narrowing — only ${pctStr} above the 50-day EMA. A/D ratio at ${adStr}.${momNote}${vixNote}`
  }
  if (state === 'Risk-Off') {
    return `Conditions have deteriorated. ${pctStr} above the 50-day EMA, A/D ratio at ${adStr}, McClellan Summation at ${mcSum.toFixed(0)}.${vixNote} Defensive posture required.`
  }
  return `Regime in transition — mixed signals across breadth, trend, and momentum. Monitor before adjusting exposure.`
}

// Portfolio action guidance — specific, not generic
export function getRegimeAction(state: string, deploymentMul: number): string {
  const pct = Math.round(deploymentMul * 100)
  if (state === 'Risk-On') return `Stay fully deployed at ${pct}%. Add quality growth names. Trim defensive hedges.`
  if (state === 'Constructive') return `Deploy at ${pct}%. Concentrate in leaders. Reduce laggards.`
  if (state === 'Cautious') return `Deploy at ${pct}%. Exit weak mid/small names. Large-cap quality bias only.`
  if (state === 'Risk-Off') return `Hold at ${pct}%. Raise cash from speculative positions. Capital preservation first.`
  return `Maintain ${pct}% deployment. Avoid new large positions until direction confirms.`
}

export type StrengthLevel = 'Very Weak' | 'Weak' | 'Mixed' | 'Building' | 'Strong'

export function getStrengthLevel(bullish: number, total: number): StrengthLevel {
  if (total === 0) return 'Mixed'
  const r = bullish / total
  if (r >= 0.8) return 'Strong'
  if (r >= 0.6) return 'Building'
  if (r >= 0.4) return 'Mixed'
  if (r >= 0.2) return 'Weak'
  return 'Very Weak'
}

export function getStrengthDots(bullish: number, total: number): boolean[] {
  const score = total > 0 ? Math.round((bullish / total) * 5) : 0
  return [1, 2, 3, 4, 5].map((i) => i <= score)
}

export function getStrengthColorClass(level: StrengthLevel): string {
  if (level === 'Strong' || level === 'Building') return 'text-signal-pos'
  if (level === 'Mixed') return 'text-signal-warn'
  return 'text-signal-neg'
}

export function getStrengthDotFillClass(level: StrengthLevel): string {
  if (level === 'Strong' || level === 'Building') return 'bg-signal-pos'
  if (level === 'Mixed') return 'bg-signal-warn'
  return 'bg-signal-neg'
}

// Compute category-level scores from the raw regime row
export function getCategoryScores(r: MarketRegimeRow) {
  const trend = [
    r.nifty500_above_ema_50 === true,
    r.nifty500_above_ema_200 === true,
    f(r.nifty500_ema_50_slope) > 0,
    f(r.nifty500_ema_200_slope) > 0,
  ]
  const breadth = [
    f(r.pct_above_ema_20) > 0.5,
    f(r.pct_above_ema_50) > 0.5,
    f(r.pct_above_ema_200) > 0.5,
    f(r.ad_ratio) > 1,
    f(r.ad_line_slope_21) > 0,
    (r.new_52w_highs ?? 0) > (r.new_52w_lows ?? 0),
    f(r.new_high_low_ratio) > 1,
  ]
  const momentum = [
    f(r.mcclellan_oscillator) > 0,
    f(r.mcclellan_summation) > 0,
    (r.net_new_highs ?? 0) > 0,
    (r.new_52w_highs ?? 0) > 20,
  ]
  const participation = [
    f(r.pct_in_strong_states) > 0.4,
    f(r.pct_weinstein_pass) > 0.4,
    f(r.pct_above_ema_50) > 0.45,
  ]

  const count = (arr: boolean[]) => arr.filter(Boolean).length
  return {
    trend:         { bullish: count(trend),         total: trend.length },
    breadth:       { bullish: count(breadth),        total: breadth.length },
    momentum:      { bullish: count(momentum),       total: momentum.length },
    participation: { bullish: count(participation),  total: participation.length },
  }
}
