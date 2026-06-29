// Pure helpers for the fund rank-history visuals (daily-slice bar, stability, swing) and
// the within-category percentile tag. Pure + client-safe so the table cell and any tests
// derive the same numbers. The daily data comes from foundation_staging.fund_rank_daily
// (see lib/queries/v6/fund_rank_history.ts); the math here mirrors the backend
// scripts/foundation/fund_rank_core.py (pct_band) so a fund's tag is identical either side.

export type RankSlice = { d: string; r: number; s: number } // date, cat_rank, cat_size

// Within-category percentile tag. Based on the fraction of the cohort AHEAD, (rank-1)/size,
// so the best fund in a category of any size is always Top 10% (boundaries fall to the lower
// band). Null when unranked or the cohort is empty. Mirrors fund_rank_core.pct_band.
export function pctBand(rank: number | null | undefined, size: number | null | undefined): string | null {
  if (rank == null || !size || size <= 0) return null
  const ahead = (rank - 1) / size
  if (ahead < 0.1) return 'Top 10%'
  if (ahead < 0.2) return 'Top 20%'
  if (ahead < 0.5) return 'Top 50%'
  return 'Bottom 50%'
}

// Days the fund has held its current rank: the trailing run of equal ranks at the end of the
// (date-ascending) series. 1 means it changed on the latest day; 0 only for an empty series.
export function stableDays(slices: RankSlice[]): number {
  if (slices.length === 0) return 0
  const latest = slices[slices.length - 1].r
  let n = 0
  for (let i = slices.length - 1; i >= 0; i--) {
    if (slices[i].r === latest) n++
    else break
  }
  return n
}

// Max-min rank swing over the trailing `windowDays` CALENDAR days (measured back from the last
// slice's date, inclusive). A small number = a stable rank; a large number = a churny one.
// Null for an empty series.
export function rankSwing(slices: RankSlice[], windowDays: number): number | null {
  if (slices.length === 0) return null
  const last = slices[slices.length - 1].d
  const cutoff = new Date(last)
  cutoff.setDate(cutoff.getDate() - windowDays)
  const inWindow = slices.filter((x) => new Date(x.d) >= cutoff)
  if (inWindow.length === 0) return null
  const ranks = inWindow.map((x) => x.r)
  return Math.max(...ranks) - Math.min(...ranks)
}
