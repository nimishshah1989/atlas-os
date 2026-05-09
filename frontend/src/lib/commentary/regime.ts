// src/lib/commentary/regime.ts
import type { MarketRegimeRow } from '@/lib/queries/regime'

const f = (s: string | null | undefined): number =>
  s == null ? 0 : parseFloat(s)

function classifyIndicators(r: MarketRegimeRow): boolean[] {
  return [
    // Trend (4)
    r.nifty500_above_ema_50,
    r.nifty500_above_ema_200,
    f(r.nifty500_ema_50_slope) > 0,
    f(r.nifty500_ema_200_slope) > 0,
    // Breadth (7)
    f(r.pct_above_ema_20) > 0.5,
    f(r.pct_above_ema_50) > 0.5,
    f(r.pct_above_ema_200) > 0.5,
    f(r.ad_ratio) > 1,
    f(r.ad_line_slope_21) > 0,
    (r.new_52w_highs ?? 0) > (r.new_52w_lows ?? 0),
    f(r.new_high_low_ratio) > 1,
    // Momentum (4)
    f(r.mcclellan_oscillator) > 0,
    f(r.mcclellan_summation) > 0,
    (r.net_new_highs ?? 0) > 0,
    (r.new_52w_highs ?? 0) > 20,
    // Participation (3)
    f(r.pct_in_strong_states) > 0.4,
    f(r.pct_weinstein_pass) > 0.4,
    f(r.pct_above_ema_50) > 0.45,
  ]
}

export function countBullishIndicators(r: MarketRegimeRow): {
  bullish: number
  total: number
} {
  const indicators = classifyIndicators(r)
  return {
    bullish: indicators.filter(Boolean).length,
    total: indicators.length,
  }
}

export function generateRegimeCommentary(r: MarketRegimeRow): string {
  const deployment = Math.round(f(r.deployment_multiplier) * 100)
  const vix = f(r.india_vix)
  const { bullish, total } = countBullishIndicators(r)
  const direction = bullish > total / 2 ? 'bullish' : 'bearish'
  const conviction =
    bullish <= total * 0.25 || bullish >= total * 0.75 ? 'high' : 'low'

  const parts: string[] = [
    `Market is in ${r.regime_state}.`,
    `${bullish} of ${total} breadth indicators are ${direction} — ${conviction}-conviction signal.`,
    `Deployment at ${deployment}%.`,
  ]

  if (vix > 0) {
    const vixLabel = vix > 25 ? 'elevated' : vix > 18 ? 'moderate' : 'low'
    parts.push(`India VIX at ${vix.toFixed(1)} — ${vixLabel} fear.`)
  }

  if (r.dislocation_active) {
    parts.push('Dislocation active — all new deployment suspended.')
  }

  return parts.join(' ')
}
