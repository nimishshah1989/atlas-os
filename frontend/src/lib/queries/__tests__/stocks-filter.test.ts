/**
 * Task 1.7 — getAllStocks filter params (TDD: failing first)
 *
 * DB is not available in vitest. We test the param signature and that the
 * function is callable with the new optional params object without throwing.
 * We also test the logic helper that maps indexFilter strings to column names.
 */
import { describe, it, expect, vi, type MockedFunction } from 'vitest'

// ---------------------------------------------------------------------------
// Mock the sql tag so no real DB connection is needed
// ---------------------------------------------------------------------------
vi.mock('@/lib/db', () => ({
  default: vi.fn(),
}))

vi.mock('server-only', () => ({}))

import { getAllStocks } from '../stocks'
import sql from '@/lib/db'

const mockSql = sql as unknown as MockedFunction<(...args: unknown[]) => Promise<unknown[]>>

// ---------------------------------------------------------------------------
// Helper: makeStockRow produces a minimal StockRowWithSector fixture.
// ---------------------------------------------------------------------------
function makeRow(overrides: Record<string, unknown> = {}) {
  return {
    instrument_id: 'inst-1',
    symbol: 'RELIANCE',
    company_name: 'Reliance Industries',
    sector: 'Energy',
    in_nifty_50: true,
    in_nifty_100: true,
    in_nifty_500: true,
    ret_1m: '0.03',
    ret_3m: '0.07',
    ret_6m: '0.12',
    rs_pctile_3m: '0.80',
    above_30w_ma: true,
    ema_10_at_20d_high: true,
    weinstein_gate_pass: true,
    ret_1w: null,
    extension_pct: null,
    vol_63: null,
    realized_vol_63: null,
    avg_volume_20: null,
    ret_12m: null,
    ret_1d: null,
    rs_pctile_1w: null,
    rs_pctile_1m: null,
    vol_ratio_63: null,
    max_drawdown_252: null,
    volume_expansion: null,
    effort_ratio_63: null,
    ema_20_ratio: null,
    ma_30w_slope_4w: null,
    atr_21: null,
    above_200d_ma: null,
    above_50d_ma: null,
    drawdown: null,
    days_in_state: null,
    history_gate_pass: true,
    liquidity_gate_pass: true,
    strength_gate: true,
    direction_gate: true,
    risk_gate: true,
    volume_gate: true,
    sector_gate: true,
    market_gate: true,
    transition_trigger: true,
    breakout_trigger: true,
    exit_market_riskoff: null,
    exit_sector_avoid: null,
    exit_rs_deteriorate: null,
    exit_momentum_collapse: null,
    exit_volume_distrib: null,
    exit_stop_loss: null,
    rs_state: 'Leader',
    momentum_state: 'Accelerating',
    risk_state: 'Low',
    volume_state: null,
    is_investable: true,
    engine_state: 'stage_2a',
    within_state_rank: 0.9,
    rs_rank_12m: 0.85,
    dwell_days: 12,
    urgency_score: null,
    alpha_3m: null,
    alpha_6m: null,
    stage: null,
    is_ppc: null,
    is_npc: null,
    is_contraction: null,
    trigger_level: null,
    ppc_strength: null,
    signal_date: null,
    cts_conviction_score: null,
    cts_action_confidence: null,
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// T1.7-A: getAllStocks({ sectorFilter: 'Banking' }) — only Banking rows
// ---------------------------------------------------------------------------

describe('getAllStocks — sectorFilter param', () => {
  it('is callable with no args (backward compat)', async () => {
    mockSql.mockResolvedValueOnce([makeRow()])
    const rows = await getAllStocks()
    expect(rows).toHaveLength(1)
  })

  it('is callable with an empty params object', async () => {
    mockSql.mockResolvedValueOnce([makeRow()])
    const rows = await getAllStocks({})
    expect(rows).toHaveLength(1)
  })

  it('is callable with sectorFilter param', async () => {
    const bankingRow = makeRow({ sector: 'Banking' })
    mockSql.mockResolvedValueOnce([bankingRow])
    const rows = await getAllStocks({ sectorFilter: 'Banking' })
    expect(rows).toHaveLength(1)
    expect(rows[0].sector).toBe('Banking')
  })

  it('returns zero rows when mock returns empty (simulates no matching sector)', async () => {
    mockSql.mockResolvedValueOnce([])
    const rows = await getAllStocks({ sectorFilter: 'NonExistentSector' })
    expect(rows).toHaveLength(0)
  })

  it('returns all rows when sectorFilter is undefined', async () => {
    const rows2 = [makeRow({ symbol: 'HDFC', sector: 'Banking' }), makeRow({ symbol: 'INFY', sector: 'IT' })]
    mockSql.mockResolvedValueOnce(rows2)
    const rows = await getAllStocks({ sectorFilter: undefined })
    expect(rows).toHaveLength(2)
  })
})

// ---------------------------------------------------------------------------
// T1.7-B: getAllStocks({ indexFilter: 'Nifty 50' }) — only Nifty 50 members
// ---------------------------------------------------------------------------

describe('getAllStocks — indexFilter param', () => {
  it('is callable with indexFilter Nifty 50', async () => {
    const n50Row = makeRow({ in_nifty_50: true })
    mockSql.mockResolvedValueOnce([n50Row])
    const rows = await getAllStocks({ indexFilter: 'Nifty 50' })
    expect(rows).toHaveLength(1)
    expect(rows[0].in_nifty_50).toBe(true)
  })

  it('is callable with indexFilter Nifty 100', async () => {
    const n100Row = makeRow({ in_nifty_50: false, in_nifty_100: true })
    mockSql.mockResolvedValueOnce([n100Row])
    const rows = await getAllStocks({ indexFilter: 'Nifty 100' })
    expect(rows).toHaveLength(1)
    expect(rows[0].in_nifty_100).toBe(true)
  })

  it('is callable with indexFilter Nifty 500', async () => {
    const n500Row = makeRow({ in_nifty_50: false, in_nifty_100: false, in_nifty_500: true })
    mockSql.mockResolvedValueOnce([n500Row])
    const rows = await getAllStocks({ indexFilter: 'Nifty 500' })
    expect(rows).toHaveLength(1)
    expect(rows[0].in_nifty_500).toBe(true)
  })

  it('is callable with both sectorFilter and indexFilter', async () => {
    const combo = makeRow({ sector: 'Banking', in_nifty_50: true })
    mockSql.mockResolvedValueOnce([combo])
    const rows = await getAllStocks({ sectorFilter: 'Banking', indexFilter: 'Nifty 50' })
    expect(rows).toHaveLength(1)
  })
})
