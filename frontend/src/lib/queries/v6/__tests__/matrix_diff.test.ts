// frontend/src/lib/queries/v6/__tests__/matrix_diff.test.ts
//
// 4 required test cases + 2 guard cases for getMatrixDiff():
//   1. Typical day  — D has new cell, D-1 didn't → new_cells_firing populated
//   2. Weekend rollover — 3-day gap, still compares D vs last populated D-1
//   3. No flips — D and D-1 identical → all arrays empty
//   4. First snapshot — no prior date → new_cells_firing filled, cells_dormant []

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getMatrixDiff, deriveGrade } from '../matrix_diff'

// ---------------------------------------------------------------------------
// deriveGrade unit tests
// ---------------------------------------------------------------------------

describe('deriveGrade', () => {
  it('maps >= 0.90 → AAA', () => expect(deriveGrade('0.92')).toBe('AAA'))
  it('maps >= 0.80 → AA',  () => expect(deriveGrade('0.82')).toBe('AA'))
  it('maps >= 0.70 → A',   () => expect(deriveGrade('0.73')).toBe('A'))
  it('maps >= 0.60 → BBB', () => expect(deriveGrade('0.65')).toBe('BBB'))
  it('maps >= 0.50 → BB',  () => expect(deriveGrade('0.55')).toBe('BB'))
  it('maps < 0.50  → B',   () => expect(deriveGrade('0.30')).toBe('B'))
  it('null → B (default)', () => expect(deriveGrade(null)).toBe('B'))
})

// ---------------------------------------------------------------------------
// Raw row fixtures (no grade — grade is derived in TypeScript)
// ---------------------------------------------------------------------------

const RAW_CELL_NEW = {
  cell_id: 'cell-new',
  cap_tier: 'Large',
  tenure: '3m',
  action: 'POSITIVE',
  confidence_unconditional: '0.82',
  date_changed: '2026-05-26',
}

const RAW_CELL_COMMON = {
  cell_id: 'cell-common',
  cap_tier: 'Mid',
  tenure: '6m',
  action: 'NEUTRAL',
  confidence_unconditional: '0.45',
  date_changed: '2026-05-26',
}

const RAW_CELL_DORMANT = {
  cell_id: 'cell-dormant',
  cap_tier: 'Small',
  tenure: '12m',
  action: 'NEGATIVE',
  confidence_unconditional: '0.63',
  date_changed: '2026-05-23',
}

// ---------------------------------------------------------------------------
// getMatrixDiff integration tests
// ---------------------------------------------------------------------------

describe('getMatrixDiff', () => {
  beforeEach(() => sqlMock.mockReset())

  // -------------------------------------------------------------------------
  // Case 1: Typical day
  // D has a new cell; D-1 has no matching cell; no dormant; no drift warns.
  // -------------------------------------------------------------------------
  it('typical day: new cell fires, none dormant, no drift warns', async () => {
    sqlMock
      // Call 1 — date resolution
      .mockResolvedValueOnce([{ d: '2026-05-26', d_prev: '2026-05-23' }])
      // Call 2 — _queryNewFiring (prevDate not null path)
      .mockResolvedValueOnce([RAW_CELL_NEW])
      // Call 3 — _queryDormant: empty
      .mockResolvedValueOnce([])
      // Call 4 — _queryDriftWarns: empty (no drift cron at v6.0)
      .mockResolvedValueOnce([])

    const result = await getMatrixDiff()

    expect(result.new_cells_firing).toHaveLength(1)
    const cell = result.new_cells_firing[0]
    expect(cell.cell_id).toBe('cell-new')
    expect(cell.cap_tier).toBe('Large')
    expect(cell.tenure).toBe('3m')
    expect(cell.action).toBe('POSITIVE')
    expect(cell.grade).toBe('AA')                 // 0.82 → AA
    expect(cell.confidence_unconditional).toBe('0.82')
    expect(cell.date_changed).toBe('2026-05-26')

    expect(result.cells_dormant).toHaveLength(0)
    expect(result.new_drift_warns).toHaveLength(0)
    expect(sqlMock).toHaveBeenCalledTimes(4)
  })

  // -------------------------------------------------------------------------
  // Case 2: Weekend rollover
  // Most-recent populated date is Friday (3 days back); prior date is Thursday.
  // Function still compares those two dates correctly.
  // -------------------------------------------------------------------------
  it('weekend rollover: 3-day gap resolves D vs last populated D-1', async () => {
    sqlMock
      // Call 1 — D=2026-05-22 (Friday), D-1=2026-05-21 (Thursday)
      .mockResolvedValueOnce([{ d: '2026-05-22', d_prev: '2026-05-21' }])
      // Call 2 — new cell on Friday
      .mockResolvedValueOnce([{ ...RAW_CELL_COMMON, date_changed: '2026-05-22' }])
      // Call 3 — dormant cell (was on Thursday, not on Friday)
      .mockResolvedValueOnce([{ ...RAW_CELL_DORMANT, date_changed: '2026-05-21' }])
      // Call 4 — drift: empty
      .mockResolvedValueOnce([])

    const result = await getMatrixDiff()

    expect(result.new_cells_firing).toHaveLength(1)
    expect(result.new_cells_firing[0].date_changed).toBe('2026-05-22')
    expect(result.new_cells_firing[0].grade).toBe('B')     // 0.45 → B

    expect(result.cells_dormant).toHaveLength(1)
    expect(result.cells_dormant[0].cell_id).toBe('cell-dormant')
    expect(result.cells_dormant[0].date_changed).toBe('2026-05-21')
    expect(result.cells_dormant[0].grade).toBe('BBB')      // 0.63 → BBB

    expect(result.new_drift_warns).toHaveLength(0)
    expect(sqlMock).toHaveBeenCalledTimes(4)
  })

  // -------------------------------------------------------------------------
  // Case 3: No flips
  // D and D-1 both return the same cells → all three arrays empty.
  // -------------------------------------------------------------------------
  it('no flips: D and D-1 identical → all arrays empty', async () => {
    sqlMock
      .mockResolvedValueOnce([{ d: '2026-05-26', d_prev: '2026-05-23' }])
      .mockResolvedValueOnce([])   // no new firing
      .mockResolvedValueOnce([])   // no dormant
      .mockResolvedValueOnce([])   // no drift warns

    const result = await getMatrixDiff()

    expect(result.new_cells_firing).toHaveLength(0)
    expect(result.cells_dormant).toHaveLength(0)
    expect(result.new_drift_warns).toHaveLength(0)
    expect(sqlMock).toHaveBeenCalledTimes(4)
  })

  // -------------------------------------------------------------------------
  // Case 4: First snapshot — no prior date
  // new_cells_firing populated (all today's cells are new), cells_dormant [].
  // -------------------------------------------------------------------------
  it('first snapshot: no prior date → new_cells_firing filled, cells_dormant []', async () => {
    sqlMock
      // D exists, D-1 is null (first ever snapshot)
      .mockResolvedValueOnce([{ d: '2026-05-26', d_prev: null }])
      // Call 2 — _queryNewFiring (null-prevDate branch — simpler query)
      .mockResolvedValueOnce([RAW_CELL_NEW, RAW_CELL_COMMON])
      // NO _queryDormant call — skipped when prevDate is null
      // Call 3 — _queryDriftWarns
      .mockResolvedValueOnce([])

    const result = await getMatrixDiff()

    expect(result.new_cells_firing).toHaveLength(2)
    expect(result.new_cells_firing[0].cell_id).toBe('cell-new')
    expect(result.new_cells_firing[1].cell_id).toBe('cell-common')

    // cells_dormant must be [] — not null, not undefined
    expect(Array.isArray(result.cells_dormant)).toBe(true)
    expect(result.cells_dormant).toEqual([])

    expect(result.new_drift_warns).toHaveLength(0)

    // Only 3 DB calls: date-resolution + new-firing + drift-warns
    expect(sqlMock).toHaveBeenCalledTimes(3)
  })

  // -------------------------------------------------------------------------
  // Guard: no signal_calls at all → empty diff, early exit after 1 DB call
  // -------------------------------------------------------------------------
  it('no signal_calls at all → all arrays empty, only date query runs', async () => {
    sqlMock.mockResolvedValueOnce([{ d: null, d_prev: null }])

    const result = await getMatrixDiff()

    expect(result.new_cells_firing).toEqual([])
    expect(result.cells_dormant).toEqual([])
    expect(result.new_drift_warns).toEqual([])
    expect(sqlMock).toHaveBeenCalledTimes(1)
  })

  // -------------------------------------------------------------------------
  // Guard: null confidence_unconditional → defaults to '0', grade = 'B'
  // -------------------------------------------------------------------------
  it('null confidence_unconditional defaults to "0" and grade "B"', async () => {
    sqlMock
      .mockResolvedValueOnce([{ d: '2026-05-26', d_prev: null }])
      .mockResolvedValueOnce([{
        cell_id: 'cell-null-conf',
        cap_tier: 'Large',
        tenure: '1m',
        action: 'POSITIVE',
        confidence_unconditional: null,
        date_changed: '2026-05-26',
      }])
      .mockResolvedValueOnce([])

    const result = await getMatrixDiff()

    expect(result.new_cells_firing[0].confidence_unconditional).toBe('0')
    expect(result.new_cells_firing[0].grade).toBe('B')
  })
})
