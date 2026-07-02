// Builder: a constituent stock's stored lens + sub-component scores → a lens→sub-component
// mini-tree (DerivNode[]), so a sector/fund/ETF tree can expand a constituent INLINE into its own
// decomposition without navigating to the stock page (recursive drill-to-atom). Lighter than the
// full stockToDerivation tree (no evidence/financials look-up) — it uses only the sub-component
// columns already stored per stock, so it's cheap to attach to every constituent on the page.
import type { DerivNode } from '@/components/v6/shared/ScoreDerivationTree'
import { DEFAULT_WEIGHTS, type LensWeightMap } from '@/lib/v6/sectorScore'
import type { ConstituentLens } from '@/lib/queries/v6/constituent_trees'

type LensKey = keyof LensWeightMap
type SubDef = { label: string; col: string; term?: string }
type LensDef = { key: LensKey | 'valuation'; label: string; additive: boolean; subs: SubDef[] }

// Lens order is active-first (the order is overridden at runtime by the live weights). Sub-component
// columns + their glossary terms mirror the stock page's decomposition and the methodology mind-map.
const LENSES: LensDef[] = [
  { key: 'technical', label: 'Technical', additive: true, subs: [
    { label: 'Trend', col: 'tech_trend', term: 'ema_stack' },
    { label: 'Rel. strength', col: 'tech_rs', term: 'rs' },
    { label: 'Vol contraction', col: 'tech_vol_contraction', term: 'vol_contraction' },
    { label: 'Volume', col: 'tech_volume', term: 'volume_ratio' },
  ] },
  { key: 'flow', label: 'Flow', additive: false, subs: [
    { label: 'Promoter', col: 'flow_promoter', term: 'promoter' },
    { label: 'Institutional', col: 'flow_institutional' },
    { label: 'Smart money', col: 'flow_smart_money', term: 'smart_money' },
  ] },
  { key: 'fundamental', label: 'Fundamental', additive: true, subs: [
    { label: 'Profitability', col: 'fund_profitability', term: 'roe' },
    { label: 'Margin', col: 'fund_margin', term: 'op_margin' },
    { label: 'Growth', col: 'fund_growth' },
    { label: 'Balance sheet', col: 'fund_balance_sheet', term: 'debt_equity' },
    { label: 'Operating leverage', col: 'fund_op_leverage' },
  ] },
  { key: 'catalyst', label: 'Catalyst', additive: false, subs: [
    { label: 'Earnings & momentum', col: 'cat_earnings_strategy' },
    { label: 'Capital actions', col: 'cat_capital_action' },
    { label: 'Governance', col: 'cat_governance' },
  ] },
  { key: 'valuation', label: 'Valuation', additive: false, subs: [
    { label: 'PE vs sector', col: 'val_pe_vs_sector', term: 'pe' },
    { label: 'Absolute PE', col: 'val_absolute_pe' },
    { label: 'P/B', col: 'val_pb', term: 'pb' },
    { label: 'EV / EBITDA', col: 'val_ev_ebitda', term: 'ev_ebitda' },
    { label: '52-week position', col: 'val_52w_position', term: 'pos_52w' },
  ] },
]

// The lens → sub-component children for one constituent. Lenses with no score are dropped; sub-
// components that weren't computed (null) are skipped; weight-0 lenses are flagged "· context".
const num = (v: number | null | string | undefined): number | null => (typeof v === 'number' ? v : null)

export function constituentLensChildren(c: ConstituentLens, weights: LensWeightMap = DEFAULT_WEIGHTS): DerivNode[] {
  return LENSES.map((lens): DerivNode | null => {
    const score = num(c[lens.key])
    if (score == null) return null
    const w = lens.key === 'valuation' ? 0 : (weights[lens.key as LensKey] ?? 0)
    const subKids: DerivNode[] = lens.subs
      .map((s) => ({ s, v: num(c[s.col]) }))
      .filter((x): x is { s: SubDef; v: number } => x.v != null)
      .map(({ s, v }) => ({ id: `${c.symbol}-${lens.key}-${s.col}`, label: s.label, score: v, term: s.term }))
    return {
      id: `${c.symbol}-${lens.key}`,
      label: w > 0 ? lens.label : `${lens.label} · context`,
      score,
      formula: lens.additive
        ? `${lens.label} ${score.toFixed(0)} = sum of the sub-component points below`
        : `${lens.label} ${score.toFixed(0)} = weighted average of the 0–100 sub-scores below`,
      children: subKids.length ? subKids : undefined,
    }
  })
    .filter((n): n is DerivNode => n != null)
    // active (weight>0) lenses first, then context — both in the canonical lens order above.
    .sort((a, b) => Number(b.label.indexOf('context') < 0) - Number(a.label.indexOf('context') < 0))
}
