// Sector composite score — the single, derivable number behind a sector. Same blend as a stock's
// conviction score (lens weights from atlas_thresholds): 0.30·Technical + 0.25·Fundamental +
// 0.25·Flow + 0.20·Catalyst, over the free-float-weighted sector lens vector. Weights renormalise
// over the lenses actually present, so the composite is always Σ(w·score)/Σw — fully traceable.
// Pure + client-safe (type-only import), so the list table, the detail tree and the methodology
// page all derive the score the SAME way. Valuation & Policy are context, not scored (weight 0).
import type { SectorLensVector } from '@/lib/queries/v6/sector_lens'

export const COMPOSITE_WEIGHTS: { key: 'technical' | 'fundamental' | 'flow' | 'catalyst'; label: string; short: string; w: number }[] = [
  { key: 'technical', label: 'Technical', short: 'Tech', w: 0.30 },
  { key: 'fundamental', label: 'Fundamental', short: 'Fund', w: 0.25 },
  { key: 'flow', label: 'Flow', short: 'Flow', w: 0.25 },
  { key: 'catalyst', label: 'Catalyst', short: 'Cat', w: 0.20 },
]

export type LensVec = Pick<SectorLensVector, 'technical' | 'fundamental' | 'flow' | 'catalyst'>

export type Contribution = { key: string; label: string; short: string; weight: number; score: number; contrib: number }

// The weighted contributions (weight × lens score), over present lenses with renormalised weights.
export function compositeContributions(v: LensVec): Contribution[] {
  const present = COMPOSITE_WEIGHTS.map((c) => ({ ...c, score: v[c.key] })).filter(
    (c): c is typeof c & { score: number } => c.score != null,
  )
  const tw = present.reduce((a, c) => a + c.w, 0)
  if (tw === 0) return []
  return present.map((c) => ({
    key: c.key, label: c.label, short: c.short, weight: c.w, score: c.score,
    contrib: (c.w / tw) * c.score, // renormalised contribution → Σ contrib = composite
  }))
}

// Composite 0–100 = Σ renormalised contributions. Null when no conviction lens is present.
export function sectorComposite(v: LensVec): number | null {
  const c = compositeContributions(v)
  return c.length ? c.reduce((a, x) => a + x.contrib, 0) : null
}
