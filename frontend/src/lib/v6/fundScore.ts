// Fund composite score — the single derivable number behind a fund. A fund is a holdings-weighted
// roll-up of the stock atom, so its score uses the EXACT same blend as a sector or a stock
// (0.30·Technical + 0.25·Fundamental + 0.25·Flow + 0.20·Catalyst, weights renormalised over the
// lenses actually present), applied to the fund's holdings-weighted lens vector. Reusing
// sectorScore keeps the methodology locked in ONE place — the list table, the detail tree and the
// methodology page all derive the score the SAME way. Valuation is context, not scored (weight 0).
//
// This replaces the legacy atlas_fund_scorecard composite (a separate NAV/risk-adjusted-return
// model whose compute pipeline was removed and whose inputs were never shown), so the fund rank is
// now (a) explicable from the columns on screen, (b) consistent with sectors/stocks, and (c) always
// as fresh as the stock scores + holdings it rolls up from — no stale standalone pipeline.
import { sectorComposite, compositeContributions, type LensVec, type LensWeightMap, type Contribution } from './sectorScore'

export type FundLensVec = { v_tech: number | null; v_fund: number | null; v_flow: number | null; v_cat: number | null }

// Map the fund's holdings-weighted lens vector onto the shared composite lens vector.
function toLensVec(r: FundLensVec): LensVec {
  return { technical: r.v_tech, fundamental: r.v_fund, flow: r.v_flow, catalyst: r.v_cat }
}

// Composite 0–100, or null when no weighted lens is present. Weights come from atlas_thresholds.
export function fundComposite(r: FundLensVec, weights?: LensWeightMap): number | null {
  return sectorComposite(toLensVec(r), weights)
}

// Per-lens weighted contributions (Σ contrib = composite) for the glass-box derivation tree.
export function fundCompositeContributions(r: FundLensVec, weights?: LensWeightMap): Contribution[] {
  return compositeContributions(toLensVec(r), weights)
}

type Rankable = { category: string | null; composite: number | null; breadth: number | null; mstar_id: string }

// Stamp cat_rank / cat_size on each fund, ranked WITHIN its SEBI category over the cohort passed in
// (the displayed list), so "N / M" always matches what's on screen. Order: composite desc, then
// breadth desc, then mstar_id — a deterministic TOTAL order, so two funds that round to the same
// score still get distinct, explicable ranks (the original "two rank-1s" confusion). Unscored funds
// (no composite) get cat_rank null but cat_size still reflects the scored cohort.
export function rankFundsInCategory<T extends Rankable>(rows: T[]): (T & { cat_rank: number | null; cat_size: number | null })[] {
  const scoredByCat = new Map<string, T[]>()
  for (const r of rows) {
    if (r.composite == null) continue
    const key = r.category ?? '—'
    ;(scoredByCat.get(key) ?? scoredByCat.set(key, []).get(key)!).push(r)
  }
  const rankOf = new Map<string, number>()
  for (const [, group] of scoredByCat) {
    group.sort(
      (a, b) =>
        b.composite! - a.composite! || (b.breadth ?? -Infinity) - (a.breadth ?? -Infinity) || a.mstar_id.localeCompare(b.mstar_id),
    )
    group.forEach((r, i) => rankOf.set(r.mstar_id, i + 1))
  }
  return rows.map((r) => {
    const key = r.category ?? '—'
    return { ...r, cat_rank: rankOf.get(r.mstar_id) ?? null, cat_size: scoredByCat.get(key)?.length ?? 0 }
  })
}
