// Shared: group an aggregate's constituents/holdings into decile-BAND nodes for the
// ScoreDerivationTree. This is what makes a sector / ETF / fund structurally MIRROR a
// stock's tight hierarchy: stock = lens → sub-component → variable; aggregate = lens →
// decile band (D10 / D8–9 / D5–7 / D1–4) → names. The decile distribution IS the
// composition — each band is the aggregate's "sub-component", a bar showing its count +
// free-float/holdings-weight share. RULE #0: deciles, weights and returns are all real
// (atlas_foundation); an absent datum renders as absence, never a synthetic fill.
import { decileColor } from '@/components/ui/decile'
import type { DerivNode } from '@/components/shared/ScoreDerivationTree'

// The four canonical bands, best → worst, with a representative decile for the band colour.
export const BANDS = [
  { lo: 10, hi: 10, label: 'D10', rep: 10 },
  { lo: 8, hi: 9, label: 'D8–9', rep: 9 },
  { lo: 5, hi: 7, label: 'D5–7', rep: 6 },
  { lo: 1, hi: 4, label: 'D1–4', rep: 2 },
] as const

// Cap names listed per band so a 60-name band stays readable; the band's COUNT label still
// reports the true total and a "+N more" leaf flags the truncation (no silent cap — RULE #0).
const NAME_CAP = 20

export type BandItem = {
  id: string
  symbol: string
  decile: number          // this item's decile for the lens being banded
  weight: number | null   // share weight as a % (holdings) or null (sectors → count-share)
  href?: string
  value?: string | null   // the constituent's DRIVER for this lens (e.g. "Acquisition +8", "RS +22%")
  metrics?: DerivNode['metrics']
  children?: DerivNode[]  // drill-to-atom: the constituent's own lens→sub-component mini-tree
}

// Group items into decile-band parent nodes. Each band shows count + share (by weight when
// weights exist, else by count) as a coloured bar; children = the names, decile-desc.
export function bandNodes(keyPrefix: string, items: BandItem[]): DerivNode[] {
  const hasWeights = items.some((i) => i.weight != null)
  const totalWeight = items.reduce((a, i) => a + (i.weight ?? 0), 0)
  const total = items.length
  return BANDS.flatMap((b) => {
    const inBand = items
      .filter((i) => i.decile >= b.lo && i.decile <= b.hi)
      .sort((a, z) => z.decile - a.decile || (z.weight ?? 0) - (a.weight ?? 0))
    if (!inBand.length) return []
    const count = inBand.length
    const share =
      hasWeights && totalWeight > 0
        ? (inBand.reduce((a, i) => a + (i.weight ?? 0), 0) / totalWeight) * 100
        : (count / total) * 100
    const kids = inBand.slice(0, NAME_CAP).map<DerivNode>((i) => ({
      id: i.id,
      label: i.symbol,
      decile: i.decile,
      weightPct: hasWeights ? i.weight : null,
      value: i.value ?? null,
      metrics: i.metrics,
      href: i.href,
      children: i.children, // drill-to-atom: expand the constituent into its own lens tree inline
    }))
    if (inBand.length > NAME_CAP)
      kids.push({ id: `${keyPrefix}-${b.label}-more`, label: `+${inBand.length - NAME_CAP} more` })
    return [
      {
        id: `${keyPrefix}-${b.label}`,
        label: b.label,
        accent: decileColor(b.rep),
        value: `${count} ${count === 1 ? 'name' : 'names'}`,
        weightPct: hasWeights ? share : null,
        bar: share,
        children: kids,
      } satisfies DerivNode,
    ]
  })
}
