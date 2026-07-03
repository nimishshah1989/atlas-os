// Pure fund analytics for the detail page — what a fund manager actually decides on:
//  • sectorComposition: the fund's holdings rolled up to sector weights (from the holdings, which
//    already carry each name's sector).
//  • computeFundRiskStats: return + risk ratios from the NAV history (returns, CAGR, annualised
//    volatility, Sharpe, Sortino, max drawdown). All derived from real NAV; windows that the fund
//    isn't old enough for return null rather than a fabricated number.
// Pure + client-safe so the cards and tests derive the same numbers.

export type SectorSlice = { sector: string; weight: number; count: number }

// Roll the holdings up to sector weights (sum of holding weights per sector), sorted desc.
export function sectorComposition(holdings: { sector: string | null; weight: number | null }[]): SectorSlice[] {
  const m = new Map<string, { weight: number; count: number }>()
  for (const h of holdings) {
    const s = h.sector ?? 'Unclassified'
    const cur = m.get(s) ?? { weight: 0, count: 0 }
    cur.weight += h.weight ?? 0
    cur.count += 1
    m.set(s, cur)
  }
  return [...m.entries()]
    .map(([sector, v]) => ({ sector, weight: v.weight, count: v.count }))
    .sort((a, b) => b.weight - a.weight)
}

// ── sector composition over time (how the holdings' sector mix has shifted) ──
export type SectorHistory = { dates: string[]; rows: { sector: string; weights: (number | null)[] }[] }

// Pivot (date, sector, weight) tuples into a sector × date matrix. Dates ascending; sectors ordered
// by the LATEST snapshot's weight (biggest current bets on top); a sector absent in a snapshot → null.
export function pivotSectorHistory(tuples: { d: string; sector: string; w: number }[]): SectorHistory {
  if (tuples.length === 0) return { dates: [], rows: [] }
  const dates = [...new Set(tuples.map((t) => t.d))].sort()
  const dateIdx = new Map(dates.map((d, i) => [d, i]))
  const bySector = new Map<string, (number | null)[]>()
  for (const t of tuples) {
    if (!bySector.has(t.sector)) bySector.set(t.sector, dates.map(() => null))
    bySector.get(t.sector)![dateIdx.get(t.d)!] = t.w
  }
  const latest = dates.length - 1
  const rows = [...bySector.entries()]
    .map(([sector, weights]) => ({ sector, weights }))
    .sort((a, b) => (b.weights[latest] ?? -1) - (a.weights[latest] ?? -1))
  return { dates, rows }
}

export type NavPoint = { d: string; nav: number }
export type FundRiskStats = {
  months: number
  ret1y: number | null
  cagr3y: number | null
  cagr5y: number | null
  cagrIncept: number | null
  volAnn: number | null
  sharpe: number | null
  sortino: number | null
  maxDrawdown: number | null
  navFrom: string | null
  navTo: string | null
}

// Assumed annual risk-free rate (Indian short rate) for Sharpe/Sortino — shown to the user as
// "rf 6.5%" so the assumption is transparent.
export const RISK_FREE = 0.065

const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length
const std = (xs: number[]) => {
  const m = mean(xs)
  return Math.sqrt(xs.reduce((a, x) => a + (x - m) ** 2, 0) / xs.length)
}

// Return + risk stats from a month-end NAV series (ascending by date). Windows (1y/3y/5y) are
// null when the fund doesn't have that much history.
export function computeFundRiskStats(points: NavPoint[], rf: number = RISK_FREE): FundRiskStats {
  const navs = points.map((p) => p.nav).filter((v) => v != null && v > 0)
  const n = navs.length
  const empty: FundRiskStats = {
    months: Math.max(0, n - 1), ret1y: null, cagr3y: null, cagr5y: null, cagrIncept: null,
    volAnn: null, sharpe: null, sortino: null, maxDrawdown: null,
    navFrom: points[0]?.d ?? null, navTo: points[n - 1]?.d ?? null,
  }
  if (n < 2) return empty

  const rets: number[] = []
  for (let i = 1; i < n; i++) rets.push(navs[i] / navs[i - 1] - 1)
  const volAnn = std(rets) * Math.sqrt(12)
  const downside = Math.sqrt(mean(rets.map((r) => Math.min(r, 0) ** 2))) * Math.sqrt(12)

  // annualised compound return over the last k months (null if not enough history)
  const cagrLast = (k: number): number | null =>
    n - 1 >= k ? Math.pow(navs[n - 1] / navs[n - 1 - k], 12 / k) - 1 : null
  const months = n - 1
  const cagrIncept = Math.pow(navs[n - 1] / navs[0], 12 / months) - 1

  // max drawdown: worst close-to-trough decline from a running peak
  let peak = navs[0]
  let maxDrawdown = 0
  for (const v of navs) {
    if (v > peak) peak = v
    const dd = v / peak - 1
    if (dd < maxDrawdown) maxDrawdown = dd
  }

  return {
    months,
    ret1y: cagrLast(12),
    cagr3y: cagrLast(36),
    cagr5y: cagrLast(60),
    cagrIncept,
    volAnn,
    sharpe: volAnn > 0 ? (cagrIncept - rf) / volAnn : null,
    sortino: downside > 0 ? (cagrIncept - rf) / downside : null,
    maxDrawdown,
    navFrom: points[0].d,
    navTo: points[n - 1].d,
  }
}
