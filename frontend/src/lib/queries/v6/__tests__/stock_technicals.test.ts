// Tests for getStockTechnicals.
//
// Four cases per spec:
//   1. Valid iid + latest date  → returns full StockTechnicals with stringified numbers
//   2. Valid iid + specific historical date → returns that exact snapshot
//   3. iid not in scorecard → returns null
//   4. JSONB missing keys → StockTechnicals has nulls for missing keys

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getStockTechnicals } from '../stock_technicals'
import type { StockTechnicals } from '../stock_technicals'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const FULL_ROW: StockTechnicals = {
  iid: 'abc-123',
  date: '2026-05-23',
  ema_distance_20: '0.042',
  ema_distance_50: '0.042',
  ema_distance_200: '0.087',
  rsi_14: '62.3',
  rs_pct_nifty500: '0.114',
  vol_252d: '0.281',
  obv_20d: '0.0023',
  atr_14: '0.019',
  pct_from_52w_high: '0.041',
  pct_from_52w_low: '0.38',
  log_med_tv_60d: '18.42',
  drawdown_from_peak: '0.056',
}

const PARTIAL_ROW: StockTechnicals = {
  iid: 'abc-123',
  date: '2026-01-10',
  // dist_above_sma50 / dist_above_sma200 missing from JSONB (new listing)
  ema_distance_20: null,
  ema_distance_50: null,
  ema_distance_200: null,
  rsi_14: null,
  rs_pct_nifty500: null,
  vol_252d: null,
  obv_20d: null,
  atr_14: null,
  pct_from_52w_high: null,
  pct_from_52w_low: null,
  log_med_tv_60d: null,
  drawdown_from_peak: null,
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('getStockTechnicals', () => {
  beforeEach(() => sqlMock.mockReset())

  // Case 1 — valid iid, omit date → SQL returns latest snapshot row
  it('returns full StockTechnicals with stringified numbers when date omitted', async () => {
    sqlMock.mockResolvedValueOnce([FULL_ROW])

    const result = await getStockTechnicals('abc-123')

    expect(result).not.toBeNull()
    expect(result!.iid).toBe('abc-123')
    expect(result!.date).toBe('2026-05-23')

    // All numeric values are strings, not floats
    expect(typeof result!.ema_distance_20).toBe('string')
    expect(result!.ema_distance_20).toBe('0.042')

    expect(typeof result!.rsi_14).toBe('string')
    expect(result!.rsi_14).toBe('62.3')

    expect(result!.rs_pct_nifty500).toBe('0.114')
    expect(result!.vol_252d).toBe('0.281')
    expect(result!.obv_20d).toBe('0.0023')
    expect(result!.atr_14).toBe('0.019')
    expect(result!.pct_from_52w_high).toBe('0.041')
    expect(result!.pct_from_52w_low).toBe('0.38')
    expect(result!.log_med_tv_60d).toBe('18.42')
    expect(result!.drawdown_from_peak).toBe('0.056')

    // sql was called once
    expect(sqlMock).toHaveBeenCalledTimes(1)
  })

  // Case 2 — valid iid + specific historical date
  it('returns the snapshot for a specific historical date when date is provided', async () => {
    const historicalRow: StockTechnicals = {
      ...FULL_ROW,
      date: '2026-03-15',
      rsi_14: '44.1',
      rs_pct_nifty500: '-0.022',
      ema_distance_20: '-0.018',
      ema_distance_50: '-0.018',
    }
    sqlMock.mockResolvedValueOnce([historicalRow])

    const result = await getStockTechnicals('abc-123', '2026-03-15')

    expect(result).not.toBeNull()
    expect(result!.date).toBe('2026-03-15')
    expect(result!.rsi_14).toBe('44.1')
    expect(result!.rs_pct_nifty500).toBe('-0.022')
    // Negative EMA distance returned as a string (not coerced to positive)
    expect(result!.ema_distance_20).toBe('-0.018')

    expect(sqlMock).toHaveBeenCalledTimes(1)
  })

  // Case 3 — iid not in scorecard → null
  it('returns null when iid has no rows in atlas_scorecard_daily', async () => {
    sqlMock.mockResolvedValueOnce([]) // empty result set

    const result = await getStockTechnicals('00000000-0000-0000-0000-000000000000')

    expect(result).toBeNull()
    expect(sqlMock).toHaveBeenCalledTimes(1)
  })

  // Case 4 — JSONB missing keys (new listing / insufficient history)
  it('returns nulls for all JSONB-sourced fields when features dict is empty', async () => {
    sqlMock.mockResolvedValueOnce([PARTIAL_ROW])

    const result = await getStockTechnicals('abc-123', '2026-01-10')

    expect(result).not.toBeNull()
    expect(result!.iid).toBe('abc-123')
    expect(result!.date).toBe('2026-01-10')

    // Every JSONB-sourced field must be null — caller renders em-dash
    expect(result!.ema_distance_20).toBeNull()
    expect(result!.ema_distance_50).toBeNull()
    expect(result!.ema_distance_200).toBeNull()
    expect(result!.rsi_14).toBeNull()
    expect(result!.vol_252d).toBeNull()
    expect(result!.obv_20d).toBeNull()
    expect(result!.atr_14).toBeNull()
    expect(result!.pct_from_52w_high).toBeNull()
    expect(result!.pct_from_52w_low).toBeNull()

    // First-class columns (log_med_tv_60d, rs_pct_nifty500, drawdown_from_peak)
    // are also null here because the new listing has no 60d history yet
    expect(result!.log_med_tv_60d).toBeNull()
    expect(result!.rs_pct_nifty500).toBeNull()
    expect(result!.drawdown_from_peak).toBeNull()
  })
})
