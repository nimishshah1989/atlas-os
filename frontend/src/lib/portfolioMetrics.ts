// Daily-series risk/return metrics for the portfolio leaderboard — pure, client-safe.
// CAGR annualized from calendar span; vol from daily returns ×√252; Sharpe vs the
// same 6.5% risk-free used by fundStats; Calmar = CAGR / |MaxDD|. Young series
// (< minDays) return nulls rather than absurd annualizations.

import { RISK_FREE } from '@/lib/fundStats'

export type SeriesPoint = { d: string; nav: number }
export type SeriesMetrics = {
  days: number
  cagr: number | null
  volAnn: number | null
  sharpe: number | null
  maxDd: number | null
  calmar: number | null
}

export function computeSeriesMetrics(points: SeriesPoint[], minDays = 90): SeriesMetrics {
  const navs = points.map((p) => p.nav).filter((v) => v > 0)
  const n = navs.length
  if (n < 2) return { days: 0, cagr: null, volAnn: null, sharpe: null, maxDd: null, calmar: null }

  let peak = navs[0]
  let maxDd = 0
  for (const v of navs) {
    if (v > peak) peak = v
    maxDd = Math.min(maxDd, v / peak - 1)
  }

  const spanDays =
    (new Date(points[points.length - 1].d).getTime() - new Date(points[0].d).getTime()) / 86400000
  if (spanDays < minDays)
    return { days: spanDays, cagr: null, volAnn: null, sharpe: null, maxDd, calmar: null }

  const cagr = Math.pow(navs[n - 1] / navs[0], 365.25 / spanDays) - 1
  const rets: number[] = []
  for (let i = 1; i < n; i++) rets.push(navs[i] / navs[i - 1] - 1)
  const mean = rets.reduce((a, b) => a + b, 0) / rets.length
  const volAnn =
    Math.sqrt(rets.reduce((a, r) => a + (r - mean) ** 2, 0) / rets.length) * Math.sqrt(252)
  return {
    days: spanDays,
    cagr,
    volAnn,
    sharpe: volAnn > 0 ? (cagr - RISK_FREE) / volAnn : null,
    maxDd,
    calmar: maxDd < 0 ? cagr / Math.abs(maxDd) : null,
  }
}
