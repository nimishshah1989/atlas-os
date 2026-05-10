import { describe, it, expect, vi } from 'vitest'

vi.mock('server-only', () => ({}))

import { buildFundCommentary, type FundCommentaryContext } from '@/lib/commentary/funds'
import { buildSingleFundCommentary } from '@/lib/commentary/funds'
import type { FundMasterRow } from '@/lib/queries/funds'

const base: FundCommentaryContext = {
  total: 191,
  n_recommended: 20,
  pct_recommended: 0.10,   // <0.15 → won't fire condition 1
  n_leader_nav: 50,
  pct_leader_nav: 0.26,    // <0.40 → won't fire condition 3
  pct_aligned_composition: 0.45,  // <0.50 → won't fire condition 5
  pct_weak_holdings: 0.30,        // <0.60 → won't fire condition 6
  pct_suspended: 0.05,            // <0.30 → won't fire condition 7
  top_category: 'Flexi Cap',
  top_category_rs_pctile: 65,     // <70 → won't fire condition 4
}

describe('buildFundCommentary', () => {
  // Condition 1: pct_recommended > 0.15
  it('fires broad momentum when >15% recommended', () => {
    const r = buildFundCommentary({ ...base, pct_recommended: 0.20, n_recommended: 38 })
    expect(r.narrative).toMatch(/broad|Recommended/i)
  })
  it('does not fire broad momentum at exactly 15%', () => {
    const r = buildFundCommentary({ ...base, pct_recommended: 0.15 })
    expect(r.narrative).not.toMatch(/Momentum is broad/i)
  })

  // Condition 2: pct_recommended === 0
  it('fires no-recommended when 0% recommended', () => {
    const r = buildFundCommentary({ ...base, pct_recommended: 0, n_recommended: 0 })
    expect(r.narrative).toMatch(/no funds|market-wide caution/i)
  })
  it('does not fire no-recommended when any recommended', () => {
    const r = buildFundCommentary({ ...base, pct_recommended: 0.01, n_recommended: 2 })
    expect(r.narrative).not.toMatch(/No funds currently carry/i)
  })

  // Condition 3: pct_leader_nav > 0.4
  it('fires leader NAV when >40% are Leader NAV', () => {
    const r = buildFundCommentary({ ...base, pct_leader_nav: 0.45, n_leader_nav: 86 })
    expect(r.narrative).toMatch(/NAV quality|Leader NAV/i)
  })
  it('does not fire leader NAV at 40%', () => {
    const r = buildFundCommentary({ ...base, pct_leader_nav: 0.40 })
    expect(r.narrative).not.toMatch(/NAV quality is broadly strong/i)
  })

  // Condition 4: top category RS > 70
  it('fires category leadership when RS pctile > 70', () => {
    const r = buildFundCommentary({ ...base, top_category_rs_pctile: 75 })
    expect(r.narrative).toMatch(/Flexi Cap|lead on RS/i)
  })
  it('does not fire when RS pctile = 70', () => {
    const r = buildFundCommentary({ ...base, top_category_rs_pctile: 70 })
    expect(r.narrative).not.toMatch(/lead on RS/i)
  })
  it('does not fire category leadership when top_category is null', () => {
    const r = buildFundCommentary({ ...base, top_category: null, top_category_rs_pctile: 80 })
    expect(r.narrative).not.toMatch(/lead on RS/i)
  })

  // Condition 5: pct_aligned_composition > 0.5
  it('fires composition alignment when >50% aligned', () => {
    const r = buildFundCommentary({ ...base, pct_aligned_composition: 0.55 })
    expect(r.narrative).toMatch(/composition-aligned/i)
  })
  it('does not fire at 50%', () => {
    const r = buildFundCommentary({ ...base, pct_aligned_composition: 0.50 })
    expect(r.narrative).not.toMatch(/composition-aligned/i)
  })

  // Condition 6: pct_weak_holdings > 0.6
  it('fires holdings headwind when >60% weak', () => {
    const r = buildFundCommentary({ ...base, pct_weak_holdings: 0.65 })
    expect(r.narrative).toMatch(/headwind|weak stocks/i)
  })
  it('does not fire at 60%', () => {
    const r = buildFundCommentary({ ...base, pct_weak_holdings: 0.60 })
    expect(r.narrative).not.toMatch(/headwind/i)
  })

  // Condition 7: pct_suspended > 0.3
  it('fires dislocation when >30% suspended', () => {
    const r = buildFundCommentary({ ...base, pct_suspended: 0.35 })
    expect(r.narrative).toMatch(/DISLOCATION_SUSPENDED|paused/i)
  })
  it('does not fire at 30%', () => {
    const r = buildFundCommentary({ ...base, pct_suspended: 0.30 })
    expect(r.narrative).not.toMatch(/DISLOCATION_SUSPENDED/i)
  })

  // Condition 8: fallback
  it('fallback returns a non-empty string for base case', () => {
    const r = buildFundCommentary(base)
    expect(typeof r.narrative).toBe('string')
    expect(r.narrative.length).toBeGreaterThan(20)
  })
  it('fallback mentions total fund count', () => {
    const r = buildFundCommentary(base)
    expect(r.narrative).toMatch(/191/)
  })

  // Context cards
  it('returns 4 context cards', () => {
    expect(buildFundCommentary(base).contextCards).toHaveLength(4)
  })
  it('context cards include recommended count', () => {
    const card = buildFundCommentary(base).contextCards.find(c => c.label.toLowerCase().includes('recommend'))
    expect(card?.value).toBe('20')
  })
  it('suspended card deltaPositive is true when pct_suspended is 0', () => {
    const r = buildFundCommentary({ ...base, pct_suspended: 0 })
    const card = r.contextCards.find(c => c.label.toLowerCase().includes('suspend'))
    expect(card?.deltaPositive).toBe(true)
  })
  it('suspended card deltaPositive is falsy when pct_suspended > 0', () => {
    const r = buildFundCommentary({ ...base, pct_suspended: 0.05 })
    const card = r.contextCards.find(c => c.label.toLowerCase().includes('suspend'))
    expect(card?.deltaPositive).toBeFalsy()
  })
})

describe('buildSingleFundCommentary', () => {
  const baseMaster: FundMasterRow = {
    mstar_id: 'F00000YXB9',
    scheme_name: 'Axis Bluechip Fund',
    amc: 'Axis AMC',
    category_name: 'Large Cap',
    broad_category: 'Equity',
    inception_date: null,
    nav_state: 'Leader NAV',
    composition_state: 'Aligned',
    holdings_state: 'Strong-Holdings',
    recommendation: 'Recommended',
    weeks_in_current_state: '8',
    performance_gate: true,
    sectors_gate: true,
    stocks_gate: true,
    market_gate: true,
    entry_trigger: true,
    exit_trigger: false,
    reduce_trigger: false,
    add_trigger: false,
    data_as_of: null,
  }

  it('returns Recommended narrative with all gates passing', () => {
    const r = buildSingleFundCommentary(baseMaster, null)
    expect(r.narrative).toMatch(/Recommended/i)
    expect(r.narrative).toMatch(/4/)
  })

  it('includes active trigger in narrative', () => {
    const r = buildSingleFundCommentary(baseMaster, null)
    expect(r.narrative).toMatch(/entry/i)
  })

  it('includes weeks in state in narrative', () => {
    const r = buildSingleFundCommentary(baseMaster, null)
    expect(r.narrative).toMatch(/8 weeks/i)
  })

  it('returns DISLOCATION narrative for suspended state', () => {
    const r = buildSingleFundCommentary({ ...baseMaster, nav_state: 'DISLOCATION_SUSPENDED' }, null)
    expect(r.narrative).toMatch(/DISLOCATION_SUSPENDED/i)
  })

  it('DISLOCATION narrative suppresses entry/exit action language', () => {
    const r = buildSingleFundCommentary({ ...baseMaster, nav_state: 'DISLOCATION_SUSPENDED' }, null)
    expect(r.narrative).toMatch(/paused|No entry/i)
  })

  it('returns Reduce narrative with gate failures', () => {
    const r = buildSingleFundCommentary({
      ...baseMaster,
      recommendation: 'Reduce',
      performance_gate: false,
      sectors_gate: false,
    }, null)
    expect(r.narrative).toMatch(/Reduce/i)
    expect(r.narrative).toMatch(/Performance|Sectors/i)
  })

  it('returns Exit narrative with gate failures', () => {
    const r = buildSingleFundCommentary({
      ...baseMaster,
      recommendation: 'Exit',
      stocks_gate: false,
      market_gate: false,
    }, null)
    expect(r.narrative).toMatch(/Exit/i)
    expect(r.narrative).toMatch(/Holdings|Market/i)
  })

  it('returns Hold narrative when not Recommended and not Reduce/Exit', () => {
    const r = buildSingleFundCommentary({
      ...baseMaster,
      recommendation: 'Hold',
      performance_gate: false,
      sectors_gate: false,
    }, null)
    expect(r.narrative).toMatch(/Hold|Monitor/i)
  })

  it('handles null weeks_in_current_state gracefully', () => {
    const r = buildSingleFundCommentary({ ...baseMaster, weeks_in_current_state: null }, null)
    expect(r.narrative).not.toMatch(/null|undefined/i)
    const card = r.contextCards.find(c => c.label === 'In State')
    expect(card?.value).toBe('—')
  })

  it('shows 52+ weeks for very long tenure', () => {
    const r = buildSingleFundCommentary({ ...baseMaster, weeks_in_current_state: '300' }, null)
    expect(r.narrative).toMatch(/52\+/)
  })

  it('returns 4 context cards', () => {
    expect(buildSingleFundCommentary(baseMaster, null).contextCards).toHaveLength(4)
  })

  it('gateCount card shows 4/4 for all passing', () => {
    const r = buildSingleFundCommentary(baseMaster, null)
    const card = r.contextCards.find(c => c.label.includes('Gates'))
    expect(card?.value).toBe('4/4')
    expect(card?.deltaPositive).toBe(true)
  })

  it('gateCount card deltaPositive false when not all gates pass', () => {
    const r = buildSingleFundCommentary({ ...baseMaster, performance_gate: false }, null)
    const card = r.contextCards.find(c => c.label.includes('Gates'))
    expect(card?.deltaPositive).toBe(false)
  })

  it('NAV State card strips trailing " NAV" suffix', () => {
    const r = buildSingleFundCommentary(baseMaster, null)
    const card = r.contextCards.find(c => c.label === 'NAV State')
    expect(card?.value).toBe('Leader')
  })

  it('recommendation card shows null-safe dash when recommendation is null', () => {
    const r = buildSingleFundCommentary({ ...baseMaster, recommendation: null }, null)
    const card = r.contextCards.find(c => c.label === 'Recommendation')
    expect(card?.value).toBe('—')
  })
})
