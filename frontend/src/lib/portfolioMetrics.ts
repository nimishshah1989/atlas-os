// Windowed risk/return metrics for the portfolio leaderboard — pure, client-safe.
// Per named window (1Y/3Y/5Y): CAGR annualized from the in-window calendar span,
// Max DD within that window, Calmar = CAGR / |Max DD|. Honest windows only — a
// window whose record is shorter than ~95% of the requested span returns nulls
// rather than a confidently-mislabelled number computed on too little data.


export type SeriesPoint = { d: string; nav: number }
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

