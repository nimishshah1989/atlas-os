// Tests for src/app/strategies/[id]/actions.ts
// Covers: rerunBacktest (UUID validation, date validation, capital min, 202 happy path,
//         409 already_running, network error), getBacktestRunStatus (invalid UUID, not found, found).

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))

vi.mock('@/lib/internal-api', () => ({
  callInternalApi: vi.fn(),
}))

// Mock postgres.js default export — inline factory to avoid hoisting issues.
vi.mock('@/lib/db', () => ({
  default: vi.fn().mockResolvedValue([]),
}))

import sql from '@/lib/db'
import { revalidatePath } from 'next/cache'
import { callInternalApi } from '@/lib/internal-api'
import { rerunBacktest, getBacktestRunStatus } from '@/app/strategies/[id]/actions'

const mockApi = callInternalApi as ReturnType<typeof vi.fn>
// vitest mocks @/lib/db as a vi.fn() — cast through unknown for TypeScript
const mockSql = sql as unknown as ReturnType<typeof vi.fn>
const VALID_UUID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'

beforeEach(() => {
  vi.clearAllMocks()
})

// ---------------------------------------------------------------------------
// rerunBacktest
// ---------------------------------------------------------------------------

describe('rerunBacktest', () => {
  it('rejects invalid UUID without calling API', async () => {
    const result = await rerunBacktest('not-a-uuid', '2020-01-01', '2024-12-31', 1_000_000)
    expect(result).toEqual({ ok: false, error: 'Invalid strategy ID' })
    expect(mockApi).not.toHaveBeenCalled()
  })

  it('rejects when endDate <= startDate', async () => {
    const result = await rerunBacktest(VALID_UUID, '2024-01-01', '2020-01-01', 1_000_000)
    expect(result).toEqual({ ok: false, error: 'End date must be after start date' })
    expect(mockApi).not.toHaveBeenCalled()
  })

  it('rejects when endDate === startDate', async () => {
    const result = await rerunBacktest(VALID_UUID, '2023-06-15', '2023-06-15', 1_000_000)
    expect(result.ok).toBe(false)
    expect(mockApi).not.toHaveBeenCalled()
  })

  it('rejects initial capital below 100_000', async () => {
    const result = await rerunBacktest(VALID_UUID, '2020-01-01', '2024-12-31', 50_000)
    expect(result).toEqual({ ok: false, error: 'Initial capital must be at least ₹1,00,000' })
    expect(mockApi).not.toHaveBeenCalled()
  })

  it('happy path: 202 response returns compute_run_id and calls revalidatePath', async () => {
    mockApi.mockResolvedValueOnce({
      ok: true,
      data: { compute_run_id: 'run-abc-123', strategy_id: VALID_UUID, status: 'running' },
      status: 202,
    })
    const result = await rerunBacktest(VALID_UUID, '2020-01-01', '2024-12-31', 1_000_000)
    expect(result).toEqual({ ok: true, compute_run_id: 'run-abc-123' })
    expect(mockApi).toHaveBeenCalledWith(
      `/api/strategies/${VALID_UUID}/backtest`,
      expect.objectContaining({
        method: 'POST',
        body: expect.objectContaining({
          start_date: '2020-01-01',
          end_date: '2024-12-31',
          initial_capital: 1_000_000,
        }),
      }),
    )
    expect(revalidatePath).toHaveBeenCalledWith(`/strategies/${VALID_UUID}`)
  })

  it('409 already_running: returns ok=false with error_code and does not revalidate', async () => {
    mockApi.mockResolvedValueOnce({
      ok: false,
      error_code: 'already_running',
      message: 'A backtest is already in progress',
      status: 409,
    })
    const result = await rerunBacktest(VALID_UUID, '2020-01-01', '2024-12-31', 1_000_000)
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.error_code).toBe('already_running')
      expect(result.error).toContain('already in progress')
    }
    expect(revalidatePath).not.toHaveBeenCalled()
  })

  it('surfaces network/config errors without calling revalidatePath', async () => {
    mockApi.mockResolvedValueOnce({
      ok: false,
      error_code: 'network_error',
      message: 'fetch failed',
      status: 0,
    })
    const result = await rerunBacktest(VALID_UUID, '2020-01-01', '2024-12-31', 1_000_000)
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toBe('fetch failed')
    expect(revalidatePath).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// getBacktestRunStatus
// ---------------------------------------------------------------------------

describe('getBacktestRunStatus', () => {
  it('returns null for invalid UUID without querying DB', async () => {
    const result = await getBacktestRunStatus('not-a-uuid')
    expect(result).toBeNull()
    expect(mockSql).not.toHaveBeenCalled()
  })

  it('returns null when row not found in DB', async () => {
    mockSql.mockResolvedValueOnce([])
    const result = await getBacktestRunStatus(VALID_UUID)
    expect(result).toBeNull()
  })

  it('returns status and finished_at when row found (running)', async () => {
    mockSql.mockResolvedValueOnce([{ status: 'running', finished_at: null }])
    const result = await getBacktestRunStatus(VALID_UUID)
    expect(result).toEqual({ status: 'running', finished_at: null })
  })

  it('returns status and finished_at as ISO string when row found (success)', async () => {
    const finishedDate = new Date('2024-06-15T10:30:00Z')
    mockSql.mockResolvedValueOnce([{ status: 'success', finished_at: finishedDate }])
    const result = await getBacktestRunStatus(VALID_UUID)
    expect(result).toEqual({
      status: 'success',
      finished_at: finishedDate.toISOString(),
    })
  })
})
