import { describe, it, expect } from 'vitest'
import { constituentLensChildren } from '../constituentTree'
import type { ConstituentLens } from '@/lib/queries/v6/constituent_trees'

// REAL sub-component scores for RELIANCE (foundation_staging.atlas_lens_scores_daily, latest date) —
// NOT synthetic (rule #0). Technical 45 = Trend 4 + Rel.strength 5 + Vol-contraction 25 + Volume 11
// (the technical sub-components are points that SUM to the lens score). flow_accumulation is null →
// it must be skipped. Only the fields the builder reads are populated; the rest are null.
const RELIANCE: ConstituentLens = {
  symbol: 'RELIANCE',
  composite: 62.7, technical: 45, flow: 15, fundamental: 39.1, catalyst: 56.69, valuation: 38.46, policy: null,
  tech_trend: 4, tech_rs: 5, tech_vol_contraction: 25, tech_volume: 11,
  flow_promoter: 0, flow_institutional: 50, flow_smart_money: 0, flow_accumulation: null,
  fund_profitability: 5.11, fund_margin: 10, fund_growth: null, fund_balance_sheet: null, fund_op_leverage: null,
  cat_earnings_strategy: null, cat_capital_action: null, cat_governance: null,
  val_pe_vs_sector: null, val_absolute_pe: null, val_pb: null, val_ev_ebitda: null, val_52w_position: null,
}

// 2-lens model: Technical + Flow carry weight; the rest are context.
const W_2LENS = { technical: 0.6, fundamental: 0, flow: 0.4, catalyst: 0 }

describe('constituentLensChildren', () => {
  const nodes = constituentLensChildren(RELIANCE, W_2LENS)
  const byId = (suffix: string) => nodes.find((n) => n.id.endsWith(suffix))

  it('emits a node per lens that has a score, active lenses first', () => {
    // technical & flow (active) lead; policy (null score) is dropped.
    expect(nodes[0].id).toBe('RELIANCE-technical')
    expect(nodes[1].id).toBe('RELIANCE-flow')
    expect(nodes.some((n) => n.id === 'RELIANCE-policy')).toBe(false)
  })

  it('carries the lens score and its sub-component children', () => {
    const tech = byId('-technical')!
    expect(tech.score).toBe(45)
    const subScores = (tech.children ?? []).map((c) => c.score)
    expect(subScores).toEqual([4, 5, 25, 11]) // Trend, Rel.strength, Vol-contraction, Volume
    expect((tech.children ?? []).map((c) => c.label)).toEqual(['Trend', 'Rel. strength', 'Vol contraction', 'Volume'])
  })

  it('skips null sub-components (flow_accumulation)', () => {
    const flow = byId('-flow')!
    expect(flow.score).toBe(15)
    const labels = (flow.children ?? []).map((c) => c.label)
    expect(labels).toEqual(['Promoter', 'Institutional', 'Smart money']) // no Accumulation
  })

  it('marks weight-0 lenses as context', () => {
    const fund = byId('-fundamental')!
    expect(fund.score).toBe(39.1)
    expect(fund.label.toLowerCase()).toContain('context')
    const tech = byId('-technical')!
    expect(tech.label.toLowerCase()).not.toContain('context')
  })

  it('drops a lens whose sub-components are all null but keeps it if the lens score exists', () => {
    // valuation has a score (38.46) but all its sub-components are null → node present, no children.
    const val = byId('-valuation')!
    expect(val.score).toBe(38.46)
    expect(val.children).toBeUndefined()
  })

  it('returns [] for an all-null constituent', () => {
    const empty: ConstituentLens = { symbol: 'X', composite: null, technical: null, flow: null, fundamental: null, catalyst: null, valuation: null, policy: null }
    expect(constituentLensChildren(empty, W_2LENS)).toEqual([])
  })
})
