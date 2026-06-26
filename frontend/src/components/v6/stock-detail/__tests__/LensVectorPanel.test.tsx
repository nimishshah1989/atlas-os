import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LensVectorPanel } from '../LensVectorPanel'
import type { LensScore } from '@/lib/queries/lens-scores'

function makeLens(overrides: Partial<LensScore> = {}): LensScore {
  return {
    instrument_id: 'iid-1',
    date: new Date('2026-06-19'),
    symbol: 'RELIANCE',
    name: 'Reliance Industries Ltd',
    sector: 'Energy',
    asset_class: 'EQ',
    technical: 72,
    fundamental: 65,
    valuation: 45,
    catalyst: 58,
    flow: 80,
    policy: 50,
    tech_trend: 78,
    tech_rs: 70,
    tech_vol_contraction: 65,
    tech_volume: 75,
    fund_profitability: 70,
    fund_margin: 62,
    fund_growth: 68,
    fund_balance_sheet: 55,
    fund_op_leverage: 70,
    val_pe_vs_sector: 40,
    val_absolute_pe: 45,
    val_pb: 50,
    val_ev_ebitda: 42,
    val_52w_position: 48,
    cat_earnings_strategy: 60,
    cat_capital_action: 55,
    cat_governance: 59,
    flow_promoter: 85,
    flow_institutional: 75,
    flow_smart_money: 80,
    policy_tailwind: 50,
    composite: 63.5,
    conviction_tier: 'HIGH',
    valuation_zone: 'FAIR',
    valuation_multiplier: 1.0,
    smart_money_score: 75,
    degradation_score: 0,
    risk_flags: null,
    evidence: null,
    lenses_active: 6,
    coverage_factor: 1.0,
    ...overrides,
  }
}

describe('LensVectorPanel', () => {
  it('renders composite score and conviction tier', () => {
    render(<LensVectorPanel lens={makeLens()} />)
    expect(screen.getByText('63.5')).toBeDefined()
    expect(screen.getByText('HIGH')).toBeDefined()
  })

  it('renders all 6 lens labels', () => {
    render(<LensVectorPanel lens={makeLens()} />)
    expect(screen.getByText('Technical')).toBeDefined()
    expect(screen.getByText('Fundamental')).toBeDefined()
    expect(screen.getByText('Valuation')).toBeDefined()
    expect(screen.getByText('Catalyst')).toBeDefined()
    expect(screen.getByText('Flow')).toBeDefined()
    expect(screen.getByText('Policy')).toBeDefined()
  })

  it('renders subcomponent values', () => {
    render(<LensVectorPanel lens={makeLens()} />)
    expect(screen.getByText('Trend')).toBeDefined()
    expect(screen.getByText('RS')).toBeDefined()
    expect(screen.getByText('Profitability')).toBeDefined()
    expect(screen.getByText('Promoter')).toBeDefined()
  })

  it('renders risk flags when present', () => {
    render(<LensVectorPanel lens={makeLens({ risk_flags: ['auditor_change'] })} />)
    // The flag is rendered as "⚑ auditor_change"
    const flagEl = screen.getByText(/auditor_change/)
    expect(flagEl).toBeDefined()
  })

  it('renders valuation zone', () => {
    render(<LensVectorPanel lens={makeLens()} />)
    expect(screen.getByText('FAIR')).toBeDefined()
  })

  it('renders coverage info', () => {
    render(<LensVectorPanel lens={makeLens()} />)
    expect(screen.getByText(/6 lenses/)).toBeDefined()
    expect(screen.getByText(/coverage 100%/)).toBeDefined()
  })

  it('handles null composite gracefully', () => {
    render(<LensVectorPanel lens={makeLens({ composite: null })} />)
    // Should show "—" for null composite
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThan(0)
  })
})
