// Adapter: a sector's free-float-weighted lens vector + its constituents → the canonical
// ScoreDerivationTree model. Aggregate path (unlike a stock): Conviction → lens → CONSTITUENTS
// (ranked by contribution = that name's lens decile × its weight if available, else by the decile),
// each constituent linking to its own /stocks page (where its full instrument tree lives).
// RULE #0: every number traces to a real atlas_foundation query (sector_lens_daily +
// per-constituent deciles) — no synthetic fallback; an absent datum renders as absence.
import type { SectorLensVector, SectorStock } from '@/lib/queries/sector_lens'
import type { DerivRoot, DerivNode } from '@/components/shared/ScoreDerivationTree'
import type { LensDrivers } from '@/lib/queries/drivers'
import type { ConstituentLens } from '@/lib/queries/constituent_trees'
import { bandNodes } from './decileBands'
import { constituentLensChildren } from './constituentTree'
import { sectorComposite, compositeContributions, type LensWeightMap } from '@/lib/sectorScore'

// lens key → the driver field on LensDrivers (only the 4 conviction lenses have a per-name driver)
const DRIVER_KEY: Record<string, keyof LensDrivers | undefined> = {
  technical: 'technical', fundamental: 'fundamental', catalyst: 'catalyst', flow: 'flow',
}

// lens key → {label, the per-constituent decile field, the lens breadth field, glossary term}
type DKey = 'd_tech' | 'd_fund' | 'd_cat' | 'd_flow' | 'd_val'
const LENSES: { key: keyof SectorLensVector; label: string; dkey: DKey | null; breadthKey: keyof SectorLensVector | null; term?: string }[] = [
  { key: 'technical', label: 'Technical', dkey: 'd_tech', breadthKey: 'breadth_technical', term: 'rs' },
  { key: 'fundamental', label: 'Fundamental', dkey: 'd_fund', breadthKey: 'breadth_fundamental', term: 'roe' },
  { key: 'valuation', label: 'Valuation', dkey: 'd_val', breadthKey: null, term: 'pe' },
  { key: 'catalyst', label: 'Catalyst', dkey: 'd_cat', breadthKey: null, term: 'conviction' },
  { key: 'flow', label: 'Flow', dkey: 'd_flow', breadthKey: 'breadth_flow', term: 'smart_money' },
  { key: 'policy', label: 'Policy', dkey: null, breadthKey: null },
]

const pct = (v: number | null) => (v == null ? null : `${(v <= 1 ? v * 100 : v).toFixed(0)}%`)
export function sectorToDerivation(sector: string, vector: SectorLensVector, stocks: SectorStock[], drivers: Record<string, LensDrivers> = {}, weights?: LensWeightMap, trees: Record<string, ConstituentLens> = {}): DerivRoot {
  const n = stocks.length
  // headline = the sector COMPOSITE (0–100), derived from the lens components — the same number
  // shown on the /sectors scores table. (Mean-decile "strength" is shown as a secondary read.)
  const composite = sectorComposite(vector, weights)
  const contribs = compositeContributions(vector, weights)
  const withStrength = stocks.filter((s): s is SectorStock & { strength: number } => s.strength != null)
  const strength = withStrength.length
    ? withStrength.reduce((a, s) => a + s.strength, 0) / withStrength.length
    : null

  const lenses: DerivNode[] = LENSES
    .map(l => ({ ...l, v: vector[l.key] as number | null }))
    .filter((l): l is typeof l & { v: number } => l.v != null)
    .map(l => {
      // The composition for THIS lens = its constituents grouped into decile BANDS (D10 / D8–9 /
      // D5–7 / D1–4). Each name shows its DECILE on this lens + its DRIVER — WHY it scores there
      // (top catalyst filing, flow input, RS, ROE) — and links to its own /stocks page. This is how
      // the sector's lens score is built bottom-up from its constituents' real drivers.
      const dk = DRIVER_KEY[l.key]
      const banded = l.dkey
        ? bandNodes(l.key, stocks
            .filter(s => (s[l.dkey!] as number | null) != null)
            .map(s => ({
              id: `${l.key}-${s.symbol}`,
              symbol: s.symbol,
              decile: s[l.dkey!] as number,
              weight: null,
              value: dk ? (drivers[s.symbol]?.[dk] ?? null) : null,
              href: `/stocks/${s.symbol}`,
              children: trees[s.symbol] ? constituentLensChildren(trees[s.symbol], weights) : undefined,
            })))
        : []
      const nWithDecile = l.dkey ? stocks.filter(s => (s[l.dkey!] as number | null) != null).length : n
      const breadthV = l.breadthKey ? (vector[l.breadthKey] as number | null) : null
      const bits = [
        `${nWithDecile} names across decile bands`,
        breadthV != null ? `breadth ${pct(breadthV)}` : null,
        vector.dispersion != null ? `dispersion ${vector.dispersion.toFixed(1)}` : null,
      ].filter(Boolean).join(' · ')
      return {
        id: l.key,
        label: l.label,
        score: l.v,
        term: l.term,
        formula: `${l.label} ${l.v.toFixed(0)} — ${bits}`,
        children: banded.length ? banded : undefined,
      }
    })

  return {
    title: sector,
    headline: {
      label: 'Sector score',
      value: composite != null ? `${composite.toFixed(0)}` : '—',
      decile: composite != null ? Math.max(1, Math.min(10, Math.round(composite / 10))) : null,
    },
    formula: composite != null
      ? `Sector score ${composite.toFixed(0)}/100 · avg-decile strength ${strength != null ? strength.toFixed(1) : '—'}/10`
      : '= 0.30·Tech + 0.25·Fund + 0.25·Flow + 0.20·Cat (free-float-weighted)',
    // Prepend a "Sector score" node that DERIVES the headline from the lens components (weight × score),
    // so the number is glass-box; the per-lens nodes (with their decile bands) follow.
    lenses: composite != null
      ? [{
          id: 'sector-score',
          label: 'Sector score',
          score: composite,
          formula: `Sector score ${composite.toFixed(0)}/100 = Σ (lens score × weight), free-float-weighted lens vector`,
          children: contribs.map((c) => ({
            id: `contrib-${c.key}`,
            label: `${c.short} · weight ${c.weight.toFixed(2)}`,
            value: `${c.score.toFixed(0)} → ${c.contrib.toFixed(1)}`,
            tone: 'neutral' as const,
          })),
        } as DerivNode, ...lenses]
      : lenses,
  }
}
