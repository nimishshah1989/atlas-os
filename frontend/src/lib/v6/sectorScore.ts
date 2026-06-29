// Composite lens score — the single, derivable number behind a sector, fund, ETF (and the same blend
// as a stock's conviction score). Weights come from atlas_thresholds (via getLensWeights, threaded in
// from the server); a hard-coded DEFAULT_WEIGHTS is only the fallback when none are passed. Weights
// renormalise over the lenses that are present AND carry weight > 0, so the composite is always
// Σ(w·score)/Σw — fully traceable. A lens with weight 0 (e.g. Fundamental/Catalyst when the FM runs a
// 2-lens model) still appears in the contributions list as context (contrib 0), but does not move the
// score. Pure + client-safe (type-only import), so the list table, the detail tree and the
// methodology page all derive the score the SAME way.
import type { SectorLensVector } from '@/lib/queries/v6/sector_lens'

export type LensWeightMap = { technical: number; fundamental: number; flow: number; catalyst: number }

// Fallback only — real weights come from atlas_thresholds. Mirrors the table's historical default.
export const DEFAULT_WEIGHTS: LensWeightMap = { technical: 0.3, fundamental: 0.25, flow: 0.25, catalyst: 0.2 }

const LENS_META: { key: keyof LensWeightMap; label: string; short: string }[] = [
  { key: 'technical', label: 'Technical', short: 'Tech' },
  { key: 'fundamental', label: 'Fundamental', short: 'Fund' },
  { key: 'flow', label: 'Flow', short: 'Flow' },
  { key: 'catalyst', label: 'Catalyst', short: 'Cat' },
]

// Back-compat export (a couple of call sites import this for labels). Uses the default weights.
export const COMPOSITE_WEIGHTS = LENS_META.map((m) => ({ ...m, w: DEFAULT_WEIGHTS[m.key] }))

export type LensVec = Pick<SectorLensVector, 'technical' | 'fundamental' | 'flow' | 'catalyst'>

export type Contribution = { key: string; label: string; short: string; weight: number; score: number; contrib: number }

// Weighted contributions over present lenses, renormalised across the weight>0 lenses. Lenses with
// weight 0 are returned with contrib 0 (shown as context), so the breakdown lists every component.
export function compositeContributions(v: LensVec, weights: LensWeightMap = DEFAULT_WEIGHTS): Contribution[] {
  const present = LENS_META.map((m) => ({ ...m, w: weights[m.key], score: v[m.key] })).filter(
    (c): c is typeof c & { score: number } => c.score != null,
  )
  const tw = present.reduce((a, c) => a + (c.w > 0 ? c.w : 0), 0)
  if (tw === 0) return []
  return present.map((c) => ({
    key: c.key, label: c.label, short: c.short, weight: c.w, score: c.score,
    contrib: c.w > 0 ? (c.w / tw) * c.score : 0, // renormalised over weight>0 → Σ contrib = composite
  }))
}

// Composite 0–100 = Σ contributions (weight>0 lenses only). Null when no weighted lens is present.
export function sectorComposite(v: LensVec, weights: LensWeightMap = DEFAULT_WEIGHTS): number | null {
  const c = compositeContributions(v, weights)
  return c.length ? c.reduce((a, x) => a + x.contrib, 0) : null
}
