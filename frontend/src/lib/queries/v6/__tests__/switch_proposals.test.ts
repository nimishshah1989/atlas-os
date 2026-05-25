// frontend/src/lib/queries/v6/__tests__/switch_proposals.test.ts
//
// 4 test cases for getSwitchProposals():
//   1. empty-portfolio: held set empty → returns [] without any SQL calls beyond getHeldIidSet
//   2. empty-reco-table: held funds present, but atlas_mf_recommendation_daily empty → returns []
//   3. switch-fires: held fund is Q3, rule says floor=Q3, target Q2 fund exists → 1 proposal
//   4. no-switch-criteria: held fund is Q2 (above floor Q3) → returns []

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))

vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>()
  return {
    ...actual,
    cache: (fn: (...args: unknown[]) => unknown) => fn,
  }
})

// Shared sql mock for all calls
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

// Mock getHeldIidSet from portfolio_holdings
const getHeldIidSetMock = vi.fn()
vi.mock('../portfolio_holdings', () => ({
  getHeldIidSet: () => getHeldIidSetMock(),
}))

import { getSwitchProposals } from '../switch_proposals'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeRule(overrides: Partial<{
  category: string
  current_quartile_floor: string
  target_quartile_ceiling: string
  min_target_consistency_months: number
  tie_break: string
}> = {}) {
  return {
    category: 'India Fund Large-Cap',
    current_quartile_floor: 'Q3',
    target_quartile_ceiling: 'Q2',
    min_target_consistency_months: 6,
    tie_break: 'lowest_expense_ratio',
    ...overrides,
  }
}

function makeRecoRow(overrides: Partial<{
  mf_instrument_id: string
  category: string
  peer_quartile: string
  consistency_months: number
  expense_ratio: string | null
  date: string
  scheme_code: string | null
  fund_name: string | null
}> = {}) {
  return {
    mf_instrument_id: 'aaaa0000-0000-0000-0000-000000000001',
    category: 'India Fund Large-Cap',
    peer_quartile: 'Q3',
    consistency_months: 8,
    expense_ratio: '1.50',
    date: '2026-05-25',
    scheme_code: 'SC001',
    fund_name: 'HDFC Large Cap',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('getSwitchProposals', () => {
  beforeEach(() => {
    sqlMock.mockReset()
    getHeldIidSetMock.mockReset()
  })

  // -------------------------------------------------------------------------
  // Case 1: empty-portfolio — held set empty → returns [] without extra SQL
  // -------------------------------------------------------------------------
  it('returns [] immediately when portfolio is empty (v6.0 launch state)', async () => {
    getHeldIidSetMock.mockResolvedValueOnce(new Set<string>())

    const result = await getSwitchProposals()

    expect(result).toEqual([])
    // No sql calls should fire after the early return
    expect(sqlMock).not.toHaveBeenCalled()
  })

  // -------------------------------------------------------------------------
  // Case 2: empty-reco-table — held funds present but recommendation table empty
  // -------------------------------------------------------------------------
  it('returns [] when atlas_mf_recommendation_daily is empty (NAV gap)', async () => {
    getHeldIidSetMock.mockResolvedValueOnce(
      new Set(['aaaa0000-0000-0000-0000-000000000001']),
    )

    // Call 1: active switch rules
    sqlMock.mockResolvedValueOnce([makeRule()])
    // Call 2: held funds reco rows — empty (NAV gap)
    sqlMock.mockResolvedValueOnce([])

    const result = await getSwitchProposals()

    expect(result).toEqual([])
    // rules query + held-reco query
    expect(sqlMock).toHaveBeenCalledTimes(2)
  })

  // -------------------------------------------------------------------------
  // Case 3: switch fires — held fund is Q3, rule floor=Q3, Q2 target exists
  // -------------------------------------------------------------------------
  it('returns 1 proposal when held fund is Q3 and a Q2 target fund exists', async () => {
    const heldIid = 'aaaa0000-0000-0000-0000-000000000001'
    const targetIid = 'bbbb0000-0000-0000-0000-000000000002'

    getHeldIidSetMock.mockResolvedValueOnce(new Set([heldIid]))

    // Call 1: active switch rules
    sqlMock.mockResolvedValueOnce([makeRule()])

    // Call 2: held fund reco row — Q3 (meets floor)
    sqlMock.mockResolvedValueOnce([
      makeRecoRow({
        mf_instrument_id: heldIid,
        peer_quartile: 'Q3',
        category: 'India Fund Large-Cap',
        scheme_code: 'SC001',
        fund_name: 'HDFC Large Cap',
      }),
    ])

    // Call 3: target fund candidates — Q2 fund with >= 6mo consistency
    sqlMock.mockResolvedValueOnce([
      makeRecoRow({
        mf_instrument_id: targetIid,
        peer_quartile: 'Q2',
        consistency_months: 9,
        scheme_code: 'SC002',
        fund_name: 'Axis Bluechip',
      }),
    ])

    const result = await getSwitchProposals()

    expect(result).toHaveLength(1)
    const proposal = result[0]
    expect(proposal.source_iid).toBe(heldIid)
    expect(proposal.source_peer_quartile).toBe('Q3')
    expect(proposal.source_name).toBe('HDFC Large Cap')
    expect(proposal.target_iid).toBe(targetIid)
    expect(proposal.target_peer_quartile).toBe('Q2')
    expect(proposal.target_name).toBe('Axis Bluechip')
    expect(proposal.category).toBe('India Fund Large-Cap')
  })

  // -------------------------------------------------------------------------
  // Case 4: no-switch-criteria — held fund is Q2 (above floor Q3) → returns []
  // -------------------------------------------------------------------------
  it('returns [] when held fund is Q2 (above switch floor Q3)', async () => {
    const heldIid = 'aaaa0000-0000-0000-0000-000000000001'

    getHeldIidSetMock.mockResolvedValueOnce(new Set([heldIid]))

    // Call 1: active switch rules (floor = Q3)
    sqlMock.mockResolvedValueOnce([makeRule({ current_quartile_floor: 'Q3' })])

    // Call 2: held fund reco row — Q2 (does NOT meet floor)
    sqlMock.mockResolvedValueOnce([
      makeRecoRow({
        mf_instrument_id: heldIid,
        peer_quartile: 'Q2',
        scheme_code: 'SC001',
        fund_name: 'HDFC Large Cap',
      }),
    ])

    const result = await getSwitchProposals()

    // Q2 fund does NOT meet Q3 floor (quartileAtOrBelow returns false for Q2 vs Q3)
    expect(result).toEqual([])
  })
})
