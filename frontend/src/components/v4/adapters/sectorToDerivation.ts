// Adapter: a sector's free-float-weighted lens vector + its constituents → the canonical
// ScoreDerivationTree model. Aggregate path (unlike a stock): Conviction → lens → CONSTITUENTS
// (ranked by contribution = that name's lens decile × its weight if available, else by the decile),
// each constituent linking to its own /stocks page (where its full instrument tree lives).
// RULE #0: every number traces to a real foundation_staging query (sector_lens_daily +
// per-constituent deciles) — no synthetic fallback; an absent datum renders as absence.
import type { SectorLensVector, SectorStock } from '@/lib/queries/v6/sector_lens'
import type { DerivRoot, DerivNode } from '@/components/v6/shared/ScoreDerivationTree'

// The composite the sector conviction expresses (lens_weight_* in atlas_thresholds; valuation/policy=0).
// TODO(thresholds-panel): read live so the tree tracks FM edits.
const COMPOSITE_FORMULA = 'free-float-weighted lens vector · composite 0.30·Tech + 0.25·Fund + 0.25·Flow + 0.20·Cat'

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
const fmtRet = (r: number | null) => (r == null ? '—' : `${r >= 0 ? '+' : '−'}${Math.abs(r * 100).toFixed(1)}%`)
const toneRet = (r: number | null): 'pos' | 'neg' | 'neutral' => (r == null ? 'neutral' : r >= 0 ? 'pos' : 'neg')
const retMetrics = (s: SectorStock) => [
  { label: '1D', value: fmtRet(s.ret_1d), tone: toneRet(s.ret_1d) },
  { label: '1W', value: fmtRet(s.ret_1w), tone: toneRet(s.ret_1w) },
  { label: '1M', value: fmtRet(s.ret_1m), tone: toneRet(s.ret_1m) },
]
// decile distribution summary for a lens ("5 at D10 · 4 at D8–9 · …") — how the aggregate forms.
function distribution(stocks: SectorStock[], dkey: DKey): string {
  const ds = stocks.map((s) => s[dkey] as number | null).filter((d): d is number => d != null)
  const band = (lo: number, hi: number) => ds.filter((d) => d >= lo && d <= hi).length
  const parts = [[10, 10, 'D10'], [8, 9, 'D8–9'], [5, 7, 'D5–7'], [1, 4, 'D1–4']] as const
  return parts.map(([lo, hi, lbl]) => `${band(lo, hi)} at ${lbl}`).join(' · ')
}

const CONSTITUENT_CAP = 30

export function sectorToDerivation(sector: string, vector: SectorLensVector, stocks: SectorStock[]): DerivRoot {
  const n = stocks.length
  // headline = sector conviction = mean of constituents' strength (avg-decile, 0–10).
  const withStrength = stocks.filter((s): s is SectorStock & { strength: number } => s.strength != null)
  const conviction = withStrength.length
    ? withStrength.reduce((a, s) => a + s.strength, 0) / withStrength.length
    : null

  const lenses: DerivNode[] = LENSES
    .map(l => ({ ...l, v: vector[l.key] as number | null }))
    .filter((l): l is typeof l & { v: number } => l.v != null)
    .map(l => {
      // constituents that have a decile for THIS lens, ranked by contribution (decile = its weight-proxy
      // here, since per-constituent free-float weights aren't exposed by getSectorStocks — sort by decile,
      // omit weightPct rather than invent a weight; RULE #0).
      // constituents that have a decile for THIS lens, ranked by decile — shown IN PLACE with
      // their 1D/1W/1M returns (the symbol links out only as a secondary action). RULE #0: real
      // per-constituent returns from technical_daily; per-name free-float weights aren't exposed,
      // so we rank by decile and omit weightPct rather than invent one.
      const ranked = l.dkey
        ? stocks
            .filter(s => (s[l.dkey!] as number | null) != null)
            .sort((a, b) => (b[l.dkey!] as number) - (a[l.dkey!] as number))
            .slice(0, CONSTITUENT_CAP)
            .map<DerivNode>(s => ({
              id: `${l.key}-${s.symbol}`,
              label: s.symbol,
              decile: s[l.dkey!] as number,
              metrics: retMetrics(s),
              href: `/stocks/${s.symbol}`,
            }))
        : []
      const breadthV = l.breadthKey ? (vector[l.breadthKey] as number | null) : null
      const bits = [
        l.dkey ? distribution(stocks, l.dkey) : `free-float-weighted avg of ${n}`,
        breadthV != null ? `breadth ${pct(breadthV)}` : null,
        vector.dispersion != null ? `dispersion ${vector.dispersion.toFixed(1)}` : null,
      ].filter(Boolean).join(' · ')
      return {
        id: l.key,
        label: l.label,
        score: l.v,
        term: l.term,
        formula: `${l.label} ${l.v.toFixed(0)} — ${bits}`,
        children: ranked.length ? ranked : undefined,
      }
    })

  return {
    title: sector,
    headline: {
      label: 'Conviction',
      value: conviction != null ? `${conviction.toFixed(1)}/10` : '—',
      decile: conviction != null ? Math.round(conviction) : null,
    },
    formula: `= ${COMPOSITE_FORMULA}`,
    lenses,
  }
}
