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
  ret_1d: number | null
  ret_1w: number | null
  ret_1m: number | null
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

// Return formatting/tone — mirrors sectorToDerivation.ts (real ret_1d/1w/1m from technical_daily;
// an absent return renders as "—", never a synthetic zero — RULE #0).
const fmtRet = (r: number | null) => (r == null ? '—' : `${r >= 0 ? '+' : '−'}${Math.abs(r * 100).toFixed(1)}%`)
const toneRet = (r: number | null): 'pos' | 'neg' | 'neutral' => (r == null ? 'neutral' : r >= 0 ? 'pos' : 'neg')
const retMetrics = (h: LensHolding) => [
  { label: '1D', value: fmtRet(h.ret_1d), tone: toneRet(h.ret_1d) },
  { label: '1W', value: fmtRet(h.ret_1w), tone: toneRet(h.ret_1w) },
  { label: '1M', value: fmtRet(h.ret_1m), tone: toneRet(h.ret_1m) },
]
// decile distribution summary for a lens ("5 at D10 · 4 at D8–9 · …") over the holdings.
function distribution(holdings: LensHolding[], dkey: DecileKey): string {
  const ds = holdings.map((h) => h[dkey]).filter((d): d is number => d != null)
  const band = (lo: number, hi: number) => ds.filter((d) => d >= lo && d <= hi).length
  const parts = [[10, 10, 'D10'], [8, 9, 'D8–9'], [5, 7, 'D5–7'], [1, 4, 'D1–4']] as const
  return parts.map(([lo, hi, lbl]) => `${band(lo, hi)} at ${lbl}`).join(' · ')
}

export function holdingsToDerivation(name: string, vector: HoldingsVector, holdings: LensHolding[]): DerivRoot {
  const n = holdings.length
  const breadthPct = vector.breadth == null ? null : vector.breadth * 100

  const lenses: DerivNode[] = LENSES
    .map(l => ({ ...l, v: vector[l.vkey] ?? null }))
    .filter((l): l is typeof l & { v: number } => l.v != null)
    .map(l => {
      // holdings ranked by contribution = weight × this holding's lens decile (the real driver),
      // shown IN PLACE with their 1D/1W/1M returns; the symbol links out only as a secondary action.
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
          metrics: retMetrics(h),
          href: `/stocks/${h.symbol}`,
        }))
      return {
        id: l.vkey,
        label: l.label,
        score: l.v,
        term: l.term,
        formula: `${l.label} ${l.v.toFixed(0)} — ${distribution(holdings, l.dkey)} · holdings-weighted avg of ${n} · ranked by contribution (weight × decile)`,
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
