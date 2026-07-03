// Fund equity-curve + relative-strength transforms (pure, unit-tested on REAL data).
//
// Two reads for the fund-detail chart:
//  • Equity curves — the fund's NAV alongside Nifty 50 and Nifty 500, all rebased to 100
//    at the first common month so absolute performance is comparable on one axis.
//  • Relative strength — the fund's rebased curve ÷ each benchmark's rebased curve × 100.
//    Rising = the fund is outperforming that benchmark; flat at 100 = tracking it.
//
// Aligning + rebasing live here (not SQL) so they're testable without a DB. The query
// hands over month-aligned raw NAV/index closes; no synthetic inputs (rule #0). These are
// the SAME two baselines (Nifty 50, Nifty 500) the /funds RS matrix already uses.

export type EqPoint = { d: string; fund: number | null; nifty50: number | null; nifty500: number | null }
export type EquityRow = { d: string; fund: number | null; nifty50: number | null; nifty500: number | null }
export type RsRow = { d: string; vsNifty50: number | null; vsNifty500: number | null }

const reb = (v: number | null, v0: number) => (v == null || v <= 0 ? null : (100 * v) / v0)

// Rebase all three series to 100 at the first month where ALL three are present (so the
// RS lines genuinely start at 100), then RS = fund_rebased ÷ index_rebased × 100.
export function buildFundCurves(points: EqPoint[]): { equity: EquityRow[]; rs: RsRow[] } {
  const start = points.findIndex(
    (p) => p.fund != null && p.fund > 0 && p.nifty50 != null && p.nifty50 > 0 && p.nifty500 != null && p.nifty500 > 0,
  )
  if (start < 0) return { equity: [], rs: [] }
  const base = points[start]
  const f0 = base.fund as number
  const n50 = base.nifty50 as number
  const n500 = base.nifty500 as number
  const slice = points.slice(start)
  const equity: EquityRow[] = slice.map((p) => ({
    d: p.d,
    fund: reb(p.fund, f0),
    nifty50: reb(p.nifty50, n50),
    nifty500: reb(p.nifty500, n500),
  }))
  const rs: RsRow[] = slice.map((p) => {
    const fr = reb(p.fund, f0)
    const r50 = reb(p.nifty50, n50)
    const r500 = reb(p.nifty500, n500)
    return {
      d: p.d,
      vsNifty50: fr != null && r50 != null && r50 > 0 ? (100 * fr) / r50 : null,
      vsNifty500: fr != null && r500 != null && r500 > 0 ? (100 * fr) / r500 : null,
    }
  })
  return { equity, rs }
}
