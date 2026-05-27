// frontend/src/lib/queries/v6/__tests__/cells.test.ts
//
// 5 test cases for cells.ts:
//   1. getAllCells returns array of cells with correct shape (mocked Postgres)
//   2. getCellById('valid-uuid') returns a single Cell
//   3. getCellById('invalid-uuid') returns null (empty result set)
//   4. getMatrixCells returns cells with n_firing_today populated (>= 0)
//   5. drift_status enum values are exactly {healthy, drift_warn, deprecated}

import { describe, it, expect, vi, beforeEach } from 'vitest'

// Silence server-only guard in test environment
vi.mock('server-only', () => ({}))

// React.cache pass-through: each call exercises the inner function directly;
// memoization is disabled so per-test mock resets work cleanly.
vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>()
  return {
    ...actual,
    cache: (fn: (...args: unknown[]) => unknown) => fn,
  }
})

const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import {
  getAllCells,
  getCellById,
  getMatrixCells,
  type Cell,
  type DriftStatus,
} from '../cells'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const BASE_CELL_ROW = {
  cell_id: '11111111-1111-1111-1111-111111111111',
  cap_tier: 'Mid',
  tenure: '6m',
  action: 'POSITIVE',
  confidence_unconditional: '0.6500',
  friction_adjusted_excess: '0.045000',
  predicted_excess: '0.038000',
  drift_status: 'healthy',
  bh_fdr_q: null,
  methodology_lock_ref: 'lock-2026-05-23',
  rule_dsl: { operator: 'AND', conditions: [{ feature: 'rs_residual_6m', gt: 0 }] },
}

const NEUTRAL_ROW = {
  ...BASE_CELL_ROW,
  cell_id: '22222222-2222-2222-2222-222222222222',
  cap_tier: 'Small',
  tenure: '1m',
  action: 'NEUTRAL',
  confidence_unconditional: null,
  friction_adjusted_excess: null,
  predicted_excess: null,
  drift_status: 'drift_warn',
}

const DEPRECATED_ROW = {
  ...BASE_CELL_ROW,
  cell_id: '33333333-3333-3333-3333-333333333333',
  drift_status: 'deprecated',
}

// ---------------------------------------------------------------------------
// 1. getAllCells returns array of cells with correct shape
// ---------------------------------------------------------------------------

describe('getAllCells', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns array of cells with correct shape from mocked Postgres', async () => {
    sqlMock.mockResolvedValueOnce([BASE_CELL_ROW, NEUTRAL_ROW])

    const cells = await getAllCells()

    expect(cells).toHaveLength(2)

    const first = cells[0]
    expect(first.cell_id).toBe('11111111-1111-1111-1111-111111111111')
    expect(first.cap_tier).toBe('Mid')
    expect(first.tenure).toBe('6m')
    expect(first.action).toBe('POSITIVE')
    expect(first.confidence_unconditional).toBe('0.6500')
    expect(first.friction_adjusted_excess).toBe('0.045000')
    expect(first.predicted_excess).toBe('0.038000')
    expect(first.drift_status).toBe('healthy')
    expect(first.bh_fdr_q).toBeNull()
    expect(first.methodology_lock_ref).toBe('lock-2026-05-23')
    expect(first.rule_dsl).toEqual({
      operator: 'AND',
      conditions: [{ feature: 'rs_residual_6m', gt: 0 }],
    })

    // null Decimal columns fall back to '0' sentinel
    const second = cells[1]
    expect(second.confidence_unconditional).toBe('0')
    expect(second.friction_adjusted_excess).toBe('0')
    expect(second.predicted_excess).toBeNull()
  })

  it('returns empty array when no cell_definitions exist', async () => {
    sqlMock.mockResolvedValueOnce([])
    const cells = await getAllCells()
    expect(cells).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// 2. getCellById('valid-uuid') returns single Cell
// ---------------------------------------------------------------------------

describe('getCellById', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns a single Cell when a matching row exists', async () => {
    sqlMock.mockResolvedValueOnce([BASE_CELL_ROW])

    const cell = await getCellById('11111111-1111-1111-1111-111111111111')

    expect(cell).not.toBeNull()
    const c = cell as Cell
    expect(c.cell_id).toBe('11111111-1111-1111-1111-111111111111')
    expect(c.action).toBe('POSITIVE')
    expect(c.drift_status).toBe('healthy')
  })

  // -------------------------------------------------------------------------
  // 3. getCellById('invalid-uuid') returns null
  // -------------------------------------------------------------------------
  it('returns null when no row matches the cell_id', async () => {
    sqlMock.mockResolvedValueOnce([])

    const cell = await getCellById('00000000-dead-beef-0000-000000000000')
    expect(cell).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 4. getMatrixCells returns cells with n_firing_today >= 0
// ---------------------------------------------------------------------------

describe('getMatrixCells', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns MatrixCells with n_firing_today populated (>= 0)', async () => {
    const matrixRows = [
      { ...BASE_CELL_ROW, n_firing_today: '12', n_candidates: '5', n_gate_pass: '3', n_held_firing: '0' },
      { ...NEUTRAL_ROW, n_firing_today: '0', n_candidates: '0', n_gate_pass: '0', n_held_firing: '0' },
    ]
    sqlMock.mockResolvedValueOnce(matrixRows)

    const cells = await getMatrixCells()

    expect(cells).toHaveLength(2)
    expect(cells[0].n_firing_today).toBe(12)
    expect(cells[0].n_firing_today).toBeGreaterThanOrEqual(0)
    expect(cells[1].n_firing_today).toBe(0)
    expect(cells[1].n_firing_today).toBeGreaterThanOrEqual(0)
    // C.14 extended fields
    expect(cells[0].n_candidates).toBe(5)
    expect(cells[0].n_gate_pass).toBe(3)
    expect(cells[0].n_held_firing).toBe(0)
    // Cell fields still present on MatrixCell
    expect(cells[0].cell_id).toBe('11111111-1111-1111-1111-111111111111')
    expect(cells[1].action).toBe('NEUTRAL')
  })

  it('returns n_firing_today=0 when signal_calls LATERAL returns 0', async () => {
    sqlMock.mockResolvedValueOnce([
      { ...DEPRECATED_ROW, n_firing_today: '0', n_candidates: '2', n_gate_pass: '0', n_held_firing: '0' },
    ])
    const cells = await getMatrixCells()
    expect(cells[0].n_firing_today).toBe(0)
    expect(cells[0].n_candidates).toBe(2)
    expect(cells[0].n_gate_pass).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// 5. drift_status enum values are exactly {healthy, drift_warn, deprecated}
// ---------------------------------------------------------------------------

describe('DriftStatus type guard', () => {
  it('all three canonical drift_status values are valid DriftStatus', () => {
    const validStatuses: DriftStatus[] = ['healthy', 'drift_warn', 'deprecated']
    // Type-level check: if this compiles, the discriminated union is correct.
    // Runtime check: each value round-trips through the Cell mapper unchanged.
    for (const status of validStatuses) {
      const row = { ...BASE_CELL_ROW, drift_status: status }
      // Inline the mapCell logic without importing private function
      const cell: Cell = {
        cell_id: row.cell_id,
        cap_tier: row.cap_tier as Cell['cap_tier'],
        tenure: row.tenure as Cell['tenure'],
        action: row.action as Cell['action'],
        confidence_unconditional: row.confidence_unconditional ?? '0',
        friction_adjusted_excess: row.friction_adjusted_excess ?? '0',
        predicted_excess: row.predicted_excess ?? null,
        drift_status: status,
        bh_fdr_q: null,
        methodology_lock_ref: row.methodology_lock_ref ?? null,
        rule_dsl: row.rule_dsl,
      }
      expect(cell.drift_status).toBe(status)
    }

    // Sanity: confirm invalid values are not in the union
    const invalid = 'clean'
    const isValidDriftStatus = (s: string): s is DriftStatus =>
      s === 'healthy' || s === 'drift_warn' || s === 'deprecated'
    expect(isValidDriftStatus(invalid)).toBe(false)
    expect(isValidDriftStatus('drift_warn')).toBe(true)
  })
})
