// Vitest tests for admin/thresholds/actions.ts Server Actions.
//
// Covers all branches:
//   updateThreshold: empty reason, non-numeric value, happy path (txn ordering),
//                    CHECK constraint violation, unexpected DB error.
//   triggerRecompute: happy path, 409 with existing_run_id, network/config error.

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

import sql from '@/lib/db'
import { triggerRecompute as mockedInternalCall } from '@/lib/internal-api'
import { revalidatePath } from 'next/cache'
import { updateThreshold, triggerRecompute } from '../../app/admin/thresholds/actions'

// ---------------------------------------------------------------------------
// Helper: build a fake transaction recorder for sql.begin.
// Returns { begin: mock, txCalls: array-of-recorded-calls }.
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
// updateThreshold
// ---------------------------------------------------------------------------

describe('updateThreshold', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('rejects empty reason without touching DB', async () => {
    const { txCalls } = makeTxMock()

    const result = await updateThreshold('rs_threshold_min', '0.5', '   ')

    expect(result).toEqual({ ok: false, error: 'Change reason is required' })
    expect((sql as { begin?: unknown }).begin).not.toHaveBeenCalled()
    expect(txCalls).toHaveLength(0)
    expect(revalidatePath).not.toHaveBeenCalled()
  })

  it('rejects non-numeric value', async () => {
    const { txCalls } = makeTxMock()

    const result = await updateThreshold('rs_threshold_min', 'not-a-number', 'valid reason')

    expect(result).toEqual({ ok: false, error: 'Value must be a number' })
    expect((sql as { begin?: unknown }).begin).not.toHaveBeenCalled()
    expect(txCalls).toHaveLength(0)
    expect(revalidatePath).not.toHaveBeenCalled()
  })

  it('happy path: SET LOCAL fires before UPDATE inside the same transaction, then revalidatePath', async () => {
    const { txCalls } = makeTxMock()

    const result = await updateThreshold('rs_threshold_min', '0.75', 'Raising RS floor after backtest')

    expect(result).toEqual({ ok: true })

    // Both SQL calls must have happened on the same tx object.
    expect(txCalls).toHaveLength(2)

    // First call must be SET LOCAL atlas.change_reason (audit trigger reads this GUC).
    const firstSql = txCalls[0].strings.join('')
    expect(firstSql).toContain('SET LOCAL atlas.change_reason')
    // The reason value must be passed as a parameterised value, not interpolated.
    expect(txCalls[0].values).toContain('Raising RS floor after backtest')

    // Second call must be the UPDATE.
    const secondSql = txCalls[1].strings.join('')
    expect(secondSql).toContain('UPDATE atlas.atlas_thresholds')
    expect(secondSql).toContain('threshold_value')

    // Ordering is load-bearing: SET LOCAL must come before UPDATE.
    const setLocalIdx = txCalls.findIndex((c) => c.strings.join('').includes('SET LOCAL'))
    const updateIdx = txCalls.findIndex((c) => c.strings.join('').includes('UPDATE'))
    expect(setLocalIdx).toBeLessThan(updateIdx)

    expect(revalidatePath).toHaveBeenCalledWith('/admin/thresholds')
  })

  it('surfaces CHECK constraint violation as a friendly error', async () => {
    makeTxMock(new Error('new row for relation violates check constraint "chk_threshold_in_range"'))

    const result = await updateThreshold('rs_threshold_min', '999', 'trying an out-of-range value')

    expect(result).toEqual({ ok: false, error: 'Value is outside the allowed [min, max] range' })
    expect(revalidatePath).not.toHaveBeenCalled()
  })

  it('surfaces unexpected DB errors verbatim', async () => {
    makeTxMock(new Error('connection timeout'))

    const result = await updateThreshold('rs_threshold_min', '0.5', 'routine adjustment')

    expect(result).toEqual({ ok: false, error: 'connection timeout' })
    expect(revalidatePath).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// triggerRecompute
// ---------------------------------------------------------------------------

describe('triggerRecompute', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('happy path: returns compute_run_id and milestone, calls revalidatePath', async () => {
    vi.mocked(mockedInternalCall).mockResolvedValueOnce({
      ok: true,
      compute_run_id: 'abc-123',
      milestone: 'm3',
      log_file: '/var/log/atlas/recompute-m3-abc-123.log',
    })

    const result = await triggerRecompute('m3')

    expect(result).toEqual({ ok: true, compute_run_id: 'abc-123', milestone: 'm3' })
    expect(revalidatePath).toHaveBeenCalledWith('/admin/thresholds')
  })

  it('surfaces internal-api 409 with existing_run_id', async () => {
    vi.mocked(mockedInternalCall).mockResolvedValueOnce({
      ok: false,
      error_code: 'already_running',
      message: 'A recompute is already in progress',
      existing_run_id: 'existing-run-999',
    })

    const result = await triggerRecompute('m4')

    expect(result).toEqual({
      ok: false,
      error: 'A recompute is already in progress',
      existing_run_id: 'existing-run-999',
    })
    expect(revalidatePath).not.toHaveBeenCalled()
  })

  it('surfaces network/config errors from internal-api without calling revalidatePath', async () => {
    vi.mocked(mockedInternalCall).mockResolvedValueOnce({
      ok: false,
      error_code: 'config_missing',
      message: 'ATLAS_INTERNAL_SECRET not set on server',
    })

    const result = await triggerRecompute('all')

    expect(result).toEqual({
      ok: false,
      error: 'ATLAS_INTERNAL_SECRET not set on server',
      existing_run_id: undefined,
    })
    expect(revalidatePath).not.toHaveBeenCalled()
  })
})
