// Sector fundamentals — REVENUE-WEIGHTED margin aggregation (the honest "what is the
// sector's margin"). The earlier table averaged per-stock margin RATIOS, which is wrong
// twice over: (1) it treats a ₹5 Cr micro-cap the same as a ₹18,000 Cr major, and (2) a
// single tiny-revenue loss-maker (stored margin −423 = −42,300%) dragged the whole
// universe average negative. Revenue-weighting (Σebitda/Σrevenue) is both the correct
// aggregate and naturally outlier-robust. Pure functions so they're unit-tested on REAL
// records pulled from atlas_foundation (rule #0) — no DB, no synthetic inputs.

export type RawFin = {
  symbol: string
  ebitda: number | null
  revenue: number | null
  pat: number | null
}

export type SectorFinAgg = {
  n: number // constituents with revenue > 0
  ebitda_margin: number | null // 100 · Σebitda / Σrevenue  (%, revenue-weighted)
  net_margin: number | null // 100 · Σpat / Σrevenue
  pct_profitable: number | null // 100 · count(pat>0) / count(pat present)
}

const hasRev = (r: RawFin) => r.revenue != null && r.revenue > 0

// Revenue-weighted margin: numerator and denominator summed over the SAME rows
// (those with both the component and positive revenue present).
function weighted(rows: RawFin[], pick: (r: RawFin) => number | null): number | null {
  let num = 0
  let den = 0
  for (const r of rows) {
    const v = pick(r)
    if (v == null || r.revenue == null || r.revenue <= 0) continue
    num += v
    den += r.revenue
  }
  return den === 0 ? null : (100 * num) / den
}

export function aggregateMargins(rows: RawFin[]): SectorFinAgg {
  const valid = rows.filter(hasRev)
  if (valid.length === 0) return { n: 0, ebitda_margin: null, net_margin: null, pct_profitable: null }
  const withPat = valid.filter((r) => r.pat != null)
  const pctProfitable = withPat.length === 0 ? null : (100 * withPat.filter((r) => (r.pat as number) > 0).length) / withPat.length
  return {
    n: valid.length,
    ebitda_margin: weighted(valid, (r) => r.ebitda),
    net_margin: weighted(valid, (r) => r.pat),
    pct_profitable: pctProfitable,
  }
}

export type ConstituentFin = {
  symbol: string
  ebitda_margin: number | null // 100 · ebitda / revenue
  net_margin: number | null // 100 · pat / revenue
  profitable: boolean | null // pat > 0
}

const margin = (part: number | null, rev: number | null) =>
  part == null || rev == null || rev <= 0 ? null : (100 * part) / rev

// Per-constituent margins for the within-sector drill, strongest EBITDA margin first,
// names without revenue (null margin) sorted last.
export function perConstituentMargins(rows: RawFin[]): ConstituentFin[] {
  return rows
    .map((r) => ({
      symbol: r.symbol,
      ebitda_margin: margin(r.ebitda, r.revenue),
      net_margin: margin(r.pat, r.revenue),
      profitable: r.pat == null || !hasRev(r) ? null : r.pat > 0,
    }))
    .sort((a, b) => (b.ebitda_margin ?? -Infinity) - (a.ebitda_margin ?? -Infinity))
}
