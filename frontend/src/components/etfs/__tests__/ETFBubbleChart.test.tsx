/**
 * Tests for ETFBubbleChart — verifies trend_strength X axis is non-zero
 * when pct_stage_2 ≠ pct_stage_4.
 *
 * We test the computeTrendStrength logic directly (inlined below to avoid
 * importing the component which depends on d3 + DOM).
 */
import { describe, it, expect } from 'vitest'
import type { ETFRow } from '@/lib/queries/etfs'

// Mirror of computeTrendStrength from ETFBubbleChart.tsx.
// Kept inline here so the test is self-contained and does not depend on d3/DOM.
function computeTrendStrength(pct_stage_2: number | null, pct_stage_4: number | null): number {
  if (pct_stage_2 == null && pct_stage_4 == null) return 0
  return (pct_stage_2 ?? 0) - (pct_stage_4 ?? 0)
}

function makeETFRow(overrides: Partial<ETFRow> = {}): ETFRow {
  return {
    ticker: 'NIFTYBEES',
    etf_name: 'Nifty BeES',
    theme: 'Broad',
    linked_sector: null,
    linked_index: 'Nifty 50',
    inception_date: '2002-01-01',
    asset_class: 'Equity',
    fund_house: 'Nippon',
    data_as_of: '2026-05-18',
    ret_1w: '0.01',
    ret_1m: '0.03',
    ret_3m: '0.08',
    ret_6m: '0.12',
    ret_12m: '0.18',
    rs_pctile_3m: '0.75',
    rs_3m_benchmark: '0.02',
    ema_10_ratio: '1.02',
    extension_pct: '0.05',
    vol_63: '0.12',
    drawdown: '-0.03',
    volume_expansion: '1.2',
    avg_volume_20: '1000000',
    effort_ratio_63: '1.1',
    above_30w_ma: true,
    ema_10_at_20d_high: true,
    days_in_state: null,
    rs_state: 'Strong',
    momentum_state: 'Accelerating',
    risk_state: null,
    weinstein_gate_pass: true,
    history_gate_pass: true,
    liquidity_gate_pass: true,
    is_investable: true,
    strength_gate: true,
    direction_gate: true,
    risk_gate: true,
    sector_gate: true,
    market_gate: true,
    position_size_pct: null,
    breakout_trigger: false,
    transition_trigger: false,
    exit_market_riskoff: null,
    exit_sector_avoid: null,
    exit_rs_deteriorate: null,
    exit_momentum_collapse: null,
    exit_stop_loss: null,
    mean_rs_rank_12m: 0.75,
    mean_within_state_rank: 0.8,
    pct_stage_2: null,
    pct_stage_4: null,
    ...overrides,
  }
}

describe('ETFBubbleChart — trend strength X axis', () => {
  it('returns 0 when both pct_stage_2 and pct_stage_4 are null (pre-migration fallback)', () => {
    const etf = makeETFRow({ pct_stage_2: null, pct_stage_4: null })
    expect(computeTrendStrength(etf.pct_stage_2, etf.pct_stage_4)).toBe(0)
  })

  it('returns positive x when pct_stage_2 > pct_stage_4 (stage 2 dominant)', () => {
    const etf = makeETFRow({ pct_stage_2: 0.7, pct_stage_4: 0.1 })
    const x = computeTrendStrength(etf.pct_stage_2, etf.pct_stage_4)
    expect(x).toBeGreaterThan(0)
    expect(x).toBeCloseTo(0.6)
  })

  it('returns negative x when pct_stage_4 > pct_stage_2 (stage 4 dominant)', () => {
    const etf = makeETFRow({ pct_stage_2: 0.0, pct_stage_4: 1.0 })
    const x = computeTrendStrength(etf.pct_stage_2, etf.pct_stage_4)
    expect(x).toBe(-1)
  })

  it('returns 0 when pct_stage_2 equals pct_stage_4', () => {
    const etf = makeETFRow({ pct_stage_2: 0.4, pct_stage_4: 0.4 })
    expect(computeTrendStrength(etf.pct_stage_2, etf.pct_stage_4)).toBeCloseTo(0)
  })

  it('non-zero x for multiple ETFs with real Agent-A breadth data', () => {
    const etfs: ETFRow[] = [
      makeETFRow({ ticker: 'AUTOBEES',  pct_stage_2: 1.0,  pct_stage_4: 0.0 }),
      makeETFRow({ ticker: 'BANKBEES',  pct_stage_2: 0.0,  pct_stage_4: 1.0 }),
      makeETFRow({ ticker: 'CPSEETF',   pct_stage_2: 0.0,  pct_stage_4: 0.0 }),
    ]
    const xs = etfs.map(e => computeTrendStrength(e.pct_stage_2, e.pct_stage_4))
    // AUTOBEES: all stage 2 → x = +1.0 (non-zero)
    expect(xs[0]).toBe(1.0)
    // BANKBEES: all stage 4 → x = -1.0 (non-zero)
    expect(xs[1]).toBe(-1.0)
    // CPSEETF: neither stage 2 nor 4 → x = 0 (neutral)
    expect(xs[2]).toBe(0)

    // At least two of the three have non-zero x positions
    const nonZero = xs.filter(x => x !== 0)
    expect(nonZero.length).toBeGreaterThanOrEqual(2)
  })
})
