// Vitest tests for admin/policies/actions.ts Server Actions.
//
// Covers:
//   updateGatePolicy: empty reason, unknown state name, happy path (txn ordering + revalidatePath)
//   updateMultiplier: unknown state key, out-of-range value, non-finite value, happy path
//   getPolicyHistoryAction: delegates to getPolicyHistory

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Module-level mocks — must be hoisted before imports of the module under test.
vi.mock('@/lib/db', () => ({
  default: vi.fn(),
}))
vi.mock('@/lib/internal-api', () => ({
  triggerRecompute: vi.fn(),
}))
vi.mock('next/cache', () => ({
  revalidatePath: vi.fn(),
}))
// queries/policies is server-only — mock to avoid 'server-only' guard in Vitest (jsdom env)
vi.mock('@/lib/queries/policies', () => ({
  getPolicyHistory: vi.fn().mockResolvedValue([]),
}))
// queries/thresholds is server-only — mock to avoid guard
vi.mock('@/lib/queries/thresholds', () => ({
  getThresholdHistory: vi.fn().mockResolvedValue([]),
  getRunStatus: vi.fn().mockResolvedValue(null),
}))

import sql from '@/lib/db'
import { revalidatePath } from 'next/cache'
import { getPolicyHistory } from '@/lib/queries/policies'
import { updateGatePolicy, updateMultiplier, getPolicyHistoryAction } from '../../app/admin/policies/actions'

// ---------------------------------------------------------------------------
// Helper: build a fake transaction recorder for sql.begin.
// ---------------------------------------------------------------------------
type TxCall = { strings: TemplateStringsArray; values: unknown[] }

function makeTxMock(throws?: Error) {
  const txCalls: TxCall[] = []
  const tx = ((strings: TemplateStringsArray, ...values: unknown[]) => {
    txCalls.push({ strings, values })
    return Promise.resolve([])
  }) as unknown as typeof sql

  ;(sql as { begin?: unknown }).begin = vi.fn().mockImplementation(async (fn: (t: typeof tx) => Promise<unknown>) => {
    if (throws) throw throws
    return fn(tx)
  })

  return { txCalls }
}

// ---------------------------------------------------------------------------
// updateGatePolicy
// ---------------------------------------------------------------------------

describe('updateGatePolicy', () => {
  beforeEach(() => { vi.clearAllMocks() })
  afterEach(() => { vi.clearAllMocks() })

  it('rejects empty reason without touching DB', async () => {
    const { txCalls } = makeTxMock()

    const result = await updateGatePolicy('strength_gate_stock', ['Leader', 'Strong'], '   ')

    expect(result).toEqual({ ok: false, error: 'Change reason is required' })
    expect((sql as { begin?: unknown }).begin).not.toHaveBeenCalled()
    expect(txCalls).toHaveLength(0)
    expect(revalidatePath).not.toHaveBeenCalled()
  })

  it('rejects unknown policy key', async () => {
    makeTxMock()

    const result = await updateGatePolicy('not_a_real_gate', ['Leader'], 'testing')

    expect(result).toEqual({ ok: false, error: 'Unknown policy key' })
    expect((sql as { begin?: unknown }).begin).not.toHaveBeenCalled()
  })

  it('rejects unknown state name in allowed list', async () => {
    makeTxMock()

    const result = await updateGatePolicy('strength_gate_stock', ['Leader', 'MADE_UP_STATE'], 'test reason')

    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toContain("Unknown state 'MADE_UP_STATE'")
    expect((sql as { begin?: unknown }).begin).not.toHaveBeenCalled()
  })

  it('happy path: SET LOCAL fires before UPDATE in same tx, then revalidatePath', async () => {
    const { txCalls } = makeTxMock()

    const result = await updateGatePolicy(
      'direction_gate_stock',
      ['Accelerating', 'Improving', 'Flat'],
      'Loosen direction gate during Cautious regime',
    )

    expect(result).toEqual({ ok: true })
    expect(txCalls).toHaveLength(2)

    // First call: SET LOCAL
    const firstSql = txCalls[0].strings.join('')
    expect(firstSql).toContain('SET LOCAL atlas.change_reason')
    expect(txCalls[0].values).toContain('Loosen direction gate during Cautious regime')

    // Second call: UPDATE
    const secondSql = txCalls[1].strings.join('')
    expect(secondSql).toContain('UPDATE atlas.atlas_decision_policy')
    expect(secondSql).toContain('policy_value')

    // Order is load-bearing
    const setLocalIdx = txCalls.findIndex((c) => c.strings.join('').includes('SET LOCAL'))
    const updateIdx = txCalls.findIndex((c) => c.strings.join('').includes('UPDATE'))
    expect(setLocalIdx).toBeLessThan(updateIdx)

    expect(revalidatePath).toHaveBeenCalledWith('/admin/policies')
  })

  it('accepts empty allowed_states (FM intent to block 100%)', async () => {
    makeTxMock()

    const result = await updateGatePolicy('market_gate', [], 'Testing empty gate')

    // Empty is allowed — FM choice, UI warns but server accepts
    expect(result).toEqual({ ok: true })
    expect(revalidatePath).toHaveBeenCalledWith('/admin/policies')
  })

  it('surfaces DB error verbatim without calling revalidatePath', async () => {
    makeTxMock(new Error('connection timeout'))

    const result = await updateGatePolicy('strength_gate_stock', ['Leader'], 'test')

    expect(result).toEqual({ ok: false, error: 'connection timeout' })
    expect(revalidatePath).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// updateMultiplier
// ---------------------------------------------------------------------------

describe('updateMultiplier', () => {
  beforeEach(() => { vi.clearAllMocks() })
  afterEach(() => { vi.clearAllMocks() })

  it('rejects empty reason without touching DB', async () => {
    const { txCalls } = makeTxMock()

    const result = await updateMultiplier('risk_multipliers_stock', { Low: 1.2 }, '  ')

    expect(result).toEqual({ ok: false, error: 'Change reason is required' })
    expect((sql as { begin?: unknown }).begin).not.toHaveBeenCalled()
    expect(txCalls).toHaveLength(0)
  })

  it('rejects unknown multiplier key', async () => {
    makeTxMock()

    const result = await updateMultiplier('not_a_real_multiplier', { Low: 1.0 }, 'test')

    expect(result).toEqual({ ok: false, error: 'Unknown multiplier key' })
    expect((sql as { begin?: unknown }).begin).not.toHaveBeenCalled()
  })

  it('rejects unknown state key for multiplier', async () => {
    makeTxMock()

    const result = await updateMultiplier('risk_multipliers_stock', { NotARiskState: 1.0 }, 'test')

    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toContain("Unknown state 'NotARiskState'")
    expect((sql as { begin?: unknown }).begin).not.toHaveBeenCalled()
  })

  it('rejects out-of-range value (above max)', async () => {
    makeTxMock()

    // risk_multipliers_stock max is 2.0
    const result = await updateMultiplier('risk_multipliers_stock', { Low: 9.9 }, 'trying too high')

    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toContain("out of range")
  })

  it('rejects non-finite value (NaN)', async () => {
    makeTxMock()

    const result = await updateMultiplier('risk_multipliers_stock', { Low: NaN }, 'bad value')

    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toContain("Invalid value for")
  })

  it('happy path: SET LOCAL fires before UPDATE, revalidatePath called', async () => {
    const { txCalls } = makeTxMock()

    const result = await updateMultiplier(
      'market_multipliers',
      { 'Risk-On': 1.0, 'Constructive': 0.8, 'Cautious': 0.5, 'Risk-Off': 0.0 },
      'Adjust market deployment caps',
    )

    expect(result).toEqual({ ok: true })
    expect(txCalls).toHaveLength(2)

    const firstSql = txCalls[0].strings.join('')
    expect(firstSql).toContain('SET LOCAL atlas.change_reason')

    const secondSql = txCalls[1].strings.join('')
    expect(secondSql).toContain('UPDATE atlas.atlas_decision_policy')

    const setLocalIdx = txCalls.findIndex((c) => c.strings.join('').includes('SET LOCAL'))
    const updateIdx = txCalls.findIndex((c) => c.strings.join('').includes('UPDATE'))
    expect(setLocalIdx).toBeLessThan(updateIdx)

    expect(revalidatePath).toHaveBeenCalledWith('/admin/policies')
  })
})

// ---------------------------------------------------------------------------
// getPolicyHistoryAction
// ---------------------------------------------------------------------------

describe('getPolicyHistoryAction', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('delegates to getPolicyHistory with policyKey and limit 20', async () => {
    vi.mocked(getPolicyHistory).mockResolvedValueOnce([])

    await getPolicyHistoryAction('strength_gate_stock')

    expect(getPolicyHistory).toHaveBeenCalledWith('strength_gate_stock', 20)
  })
})
