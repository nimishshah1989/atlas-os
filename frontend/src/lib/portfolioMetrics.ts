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

export type WindowMetrics = { cagr: number | null; maxDd: number | null; calmar: number | null }

// CAGR/MaxDD/Calmar over the LAST `years` of the series. Honest windows only:
// if the record covers less than ~95% of the requested span, every cell is null —
// a "3Y CAGR" computed on 2 years of data would be a lie with a confident label.
export function computeWindowMetrics(points: SeriesPoint[], years: number): WindowMetrics {
  const none = { cagr: null, maxDd: null, calmar: null }
  if (points.length < 2) return none
  const endMs = new Date(points[points.length - 1].d).getTime()
  const startMs = new Date(points[0].d).getTime()
  const wantMs = years * 365.25 * 86400000
  if (endMs - startMs < wantMs * 0.95) return none
  const win = points.filter((p) => endMs - new Date(p.d).getTime() <= wantMs && p.nav > 0)
  if (win.length < 2) return none
  const spanDays = (endMs - new Date(win[0].d).getTime()) / 86400000
  const cagr = Math.pow(win[win.length - 1].nav / win[0].nav, 365.25 / spanDays) - 1
  let peak = win[0].nav
  let maxDd = 0
  for (const p of win) {
    if (p.nav > peak) peak = p.nav
    maxDd = Math.min(maxDd, p.nav / peak - 1)
  }
  return { cagr, maxDd, calmar: maxDd < 0 ? cagr / Math.abs(maxDd) : null }
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
