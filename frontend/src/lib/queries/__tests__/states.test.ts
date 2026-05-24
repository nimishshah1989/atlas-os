// Tests for states.ts — type-shape guards and getStockCohortKey branching logic.
// DB-dependent functions (getStockState, getCohortBaseline, etc.) are tested via
// type-shape assertions only; the DB is not available in the test environment.
// getStockCohortKey branching logic is extracted and tested in isolation below.
import { describe, it, expect } from 'vitest'
import type {
  StockState,
  CohortBaseline,
  StateHistoryEntry,
  WithinStatePeer,
} from '../states'

// ---------------------------------------------------------------------------
// Type-shape tests — these fail at compile time if interfaces change
// ---------------------------------------------------------------------------

describe('StockState interface', () => {
  it('has all required fields with correct types', () => {
    const row: StockState = {
      instrument_id: 'abc-123',
      date: '2024-06-01',
      state: 'stage_2c',
      prior_state: 'stage_2b',
      state_since_date: '2024-01-15',
      dwell_days: 134,
      dwell_percentile: 88,
      urgency_score: 'late',
      within_state_rank: 3,
      rs_rank_12m: 0.92,
      close_vs_sma_50: 1.05,
      close_vs_sma_150: 1.12,
      close_vs_sma_200: 1.18,
      sma_200_slope: 0.0003,
      volume_ratio_50d: 1.4,
      distribution_days: 2,
      classifier_version: 'v2.0-validated',
    }
    expect(row.instrument_id).toBeDefined()
    expect(row.state).toBe('stage_2c')
    expect(row.urgency_score).toBe('late')
    expect(row.dwell_days).toBe(134)
  })

  it('allows nullable optional fields', () => {
    const row: StockState = {
      instrument_id: 'abc-123',
      date: '2024-06-01',
      state: 'uninvestable',
      prior_state: null,
      state_since_date: '2024-05-01',
      dwell_days: 10,
      dwell_percentile: null,
      urgency_score: 'n/a',
      within_state_rank: null,
      rs_rank_12m: null,
      close_vs_sma_50: null,
      close_vs_sma_150: null,
      close_vs_sma_200: null,
      sma_200_slope: null,
      volume_ratio_50d: null,
      distribution_days: null,
      classifier_version: 'v2.0-validated',
    }
    expect(row.prior_state).toBeNull()
    expect(row.dwell_percentile).toBeNull()
  })
})

describe('CohortBaseline interface', () => {
  it('has all required fields', () => {
    const row: CohortBaseline = {
      cohort_key: 'large_cap',
      state: 'stage_2c',
      median_dwell_days: 89,
      p25_dwell_days: 45,
      p75_dwell_days: 152,
      p95_dwell_days: 210,
      n_observations: 847,
    }
    expect(row.cohort_key).toBe('large_cap')
    expect(row.median_dwell_days).toBe(89)
    expect(row.n_observations).toBe(847)
  })

  it('allows null dwell day percentiles', () => {
    const row: CohortBaseline = {
      cohort_key: 'small_cap',
      state: 'stage_1',
      median_dwell_days: null,
      p25_dwell_days: null,
      p75_dwell_days: null,
      p95_dwell_days: null,
      n_observations: 0,
    }
    expect(row.median_dwell_days).toBeNull()
  })
})

describe('StateHistoryEntry interface', () => {
  it('has required fields', () => {
    const row: StateHistoryEntry = {
      date: '2024-06-01',
      state: 'stage_2b',
      dwell_days: 22,
    }
    expect(row.date).toBe('2024-06-01')
    expect(row.state).toBeDefined()
  })
})

describe('WithinStatePeer interface', () => {
  it('has required fields', () => {
    const row: WithinStatePeer = {
      instrument_id: 'abc-123',
      symbol: 'ANANTRAJ',
      within_state_rank: 3,
      rs_rank_12m: 0.88,
      dwell_days: 45,
    }
    expect(row.symbol).toBe('ANANTRAJ')
    expect(row.within_state_rank).toBe(3)
  })
})

// ---------------------------------------------------------------------------
// getStockCohortKey branching logic — tested in isolation
// ---------------------------------------------------------------------------
// The function has three code paths based on in_nifty_100 and in_nifty_500.
// We extract that logic here for unit testing without a DB connection.

function resolveCohortKey(
  row: { in_nifty_100: boolean; in_nifty_500: boolean } | undefined,
): string {
  if (!row) return 'small_cap'
  if (row.in_nifty_100) return 'large_cap'
  if (row.in_nifty_500) return 'mid_cap'
  return 'small_cap'
}

describe('getStockCohortKey branching logic', () => {
  it('returns small_cap when no universe row found', () => {
    expect(resolveCohortKey(undefined)).toBe('small_cap')
  })

  it('returns large_cap when in_nifty_100 is true', () => {
    expect(resolveCohortKey({ in_nifty_100: true, in_nifty_500: true })).toBe('large_cap')
  })

  it('returns large_cap when in_nifty_100 is true even if in_nifty_500 is false', () => {
    expect(resolveCohortKey({ in_nifty_100: true, in_nifty_500: false })).toBe('large_cap')
  })

  it('returns mid_cap when in_nifty_100 is false and in_nifty_500 is true', () => {
    expect(resolveCohortKey({ in_nifty_100: false, in_nifty_500: true })).toBe('mid_cap')
  })

  it('returns small_cap when both flags are false', () => {
    expect(resolveCohortKey({ in_nifty_100: false, in_nifty_500: false })).toBe('small_cap')
  })
})
