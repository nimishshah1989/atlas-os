// Adapter: a holdings-weighted entity (ETF / fund) → the canonical ScoreDerivationTree model.
// Aggregate path (like a sector): Leadership-breadth → lens → HOLDINGS (ranked by contribution =
// holding weight × that name's lens decile), each holding linking to its own /stocks page.
// The headline is LEADERSHIP-BREADTH (the real ETF/fund headline), NOT a composite score.
// RULE #0: every number traces to a real foundation_staging field (holdings-weighted vector +
// per-holding deciles + weights) — no synthetic fallback; an absent datum renders as absence.
import type { DerivRoot, DerivNode } from '@/components/v6/shared/ScoreDerivationTree'
import { bandNodes } from './decileBands'

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
export function holdingsToDerivation(name: string, vector: HoldingsVector, holdings: LensHolding[]): DerivRoot {
  const n = holdings.length
  const breadthPct = vector.breadth == null ? null : vector.breadth * 100

  const lenses: DerivNode[] = LENSES
    .map(l => ({ ...l, v: vector[l.vkey] ?? null }))
    .filter((l): l is typeof l & { v: number } => l.v != null)
    .map(l => {
      // The composition for THIS lens = its holdings grouped into decile BANDS (D10 / D8–9 /
      // D5–7 / D1–4); each band's bar is its holdings-WEIGHT share (the real driver), so the
      // bands show where the fund's weight actually sits. Names sit under their band with their
      // own weight + real 1D/1W/1M returns; the symbol links out only as a secondary action.
      const banded = bandNodes(l.vkey, holdings
        .filter(h => h[l.dkey] != null)
        .map(h => ({
          id: `${l.vkey}-${h.symbol}`,
          symbol: h.symbol,
          decile: h[l.dkey] as number,
          weight: toPct(h.weight),
          metrics: retMetrics(h),
          href: `/stocks/${h.symbol}`,
        })))
      const nWithDecile = holdings.filter(h => h[l.dkey] != null).length
      return {
        id: l.vkey,
        label: l.label,
        score: l.v,
        term: l.term,
        formula: `${l.label} ${l.v.toFixed(0)} — ${nWithDecile} of ${n} holdings across decile bands (weight-share bars) · holdings-weighted`,
        children: banded.length ? banded : undefined,
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
