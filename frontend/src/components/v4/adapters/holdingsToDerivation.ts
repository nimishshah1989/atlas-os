// Adapter: a holdings-weighted entity (ETF / fund) → the canonical ScoreDerivationTree model.
// Aggregate path (like a sector): Leadership-breadth → lens → HOLDINGS (ranked by contribution =
// holding weight × that name's lens decile), each holding linking to its own /stocks page.
// The headline is LEADERSHIP-BREADTH (the real ETF/fund headline), NOT a composite score.
// RULE #0: every number traces to a real foundation_staging field (holdings-weighted vector +
// per-holding deciles + weights) — no synthetic fallback; an absent datum renders as absence.
import type { DerivRoot, DerivNode } from '@/components/v6/shared/ScoreDerivationTree'

// Minimal shape this adapter needs from a holding — satisfied by both EtfHolding and FundHolding.
export type LensHolding = {
  symbol: string
  weight: number | null
  d_tech: number | null
  d_fund: number | null
  d_cat: number | null
  d_flow: number | null
  d_val: number | null
}

type VectorKey = 'v_tech' | 'v_fund' | 'v_cat' | 'v_flow' | 'v_val'
type DecileKey = 'd_tech' | 'd_fund' | 'd_cat' | 'd_flow' | 'd_val'
type HoldingsVector = Partial<Record<VectorKey, number | null>> & {
  breadth?: number | null; n_holdings?: number | null; n_leaders?: number | null
}

const LENSES: { vkey: VectorKey; dkey: DecileKey; label: string; term?: string }[] = [
  { vkey: 'v_tech', dkey: 'd_tech', label: 'Technical', term: 'rs' },
  { vkey: 'v_fund', dkey: 'd_fund', label: 'Fundamental', term: 'roe' },
  { vkey: 'v_cat', dkey: 'd_cat', label: 'Catalyst', term: 'conviction' },
  { vkey: 'v_flow', dkey: 'd_flow', label: 'Flow', term: 'smart_money' },
  { vkey: 'v_val', dkey: 'd_val', label: 'Valuation', term: 'pe' },
]

const HOLDING_CAP = 15

// Weight may be a FRACTION (ETF, 0.0617) or a PERCENT (fund, 6.17) — normalise either to a %.
const toPct = (w: number | null): number | null => (w == null ? null : w <= 1 ? w * 100 : w)

export function holdingsToDerivation(name: string, vector: HoldingsVector, holdings: LensHolding[]): DerivRoot {
  const n = holdings.length
  const breadthPct = vector.breadth == null ? null : vector.breadth * 100

  const lenses: DerivNode[] = LENSES
    .map(l => ({ ...l, v: vector[l.vkey] ?? null }))
    .filter((l): l is typeof l & { v: number } => l.v != null)
    .map(l => {
      // holdings ranked by contribution = weight × this holding's lens decile (the real driver).
      const ranked = holdings
        .filter(h => h[l.dkey] != null)
        .map(h => ({ h, contrib: (toPct(h.weight) ?? 0) * (h[l.dkey] as number) }))
        .sort((a, b) => b.contrib - a.contrib)
        .slice(0, HOLDING_CAP)
        .map<DerivNode>(({ h }) => ({
          id: `${l.vkey}-${h.symbol}`,
          label: h.symbol,
          decile: h[l.dkey] as number,
          weightPct: toPct(h.weight),
          href: `/stocks/${h.symbol}`,
        }))
      return {
        id: l.vkey,
        label: l.label,
        score: l.v,
        term: l.term,
        formula: `${l.label} ${l.v.toFixed(0)} = holdings-weighted avg of ${n} holdings · ranked by contribution (weight × decile)`,
        children: ranked.length ? ranked : undefined,
      }
    })

  return {
    title: name,
    headline: {
      label: 'Leadership breadth',
      value: breadthPct == null ? '—' : `${breadthPct.toFixed(0)}%`,
      // breadth 0–100% → a 0–10 decile-tone proxy so the headline takes the perceptual ramp.
      decile: breadthPct == null ? null : Math.max(1, Math.min(10, Math.round(breadthPct / 10))),
    },
    formula: vector.n_leaders != null && vector.n_holdings != null
      ? `= ${vector.n_leaders} of ${vector.n_holdings} holdings lead ≥2 lenses (weighted) · lenses below are holdings-weighted`
      : '= weighted share of holdings leading ≥2 conviction lenses · lenses below are holdings-weighted',
    lenses,
  }
}
