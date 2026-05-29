// Smoke test for getStockDeepdive — locks the parsed shape from
// atlas.mv_stock_deepdive (single row per symbol).

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getStockDeepdive } from '../stock-deepdive'

describe('getStockDeepdive', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns null when symbol not found', async () => {
    sqlMock.mockResolvedValueOnce([])
    const d = await getStockDeepdive('NOT_A_STOCK')
    expect(d).toBeNull()
  })

  it('parses scalars + JSONB sections for a real symbol', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        instrument_id: '11111111-1111-1111-1111-111111111111',
        symbol: 'RELIANCE',
        company_name: 'Reliance Industries Limited',
        sector: 'Energy',
        industry: 'Oil & Gas',
        tier: 'Large',
        in_nifty_50: true, in_nifty_100: true, in_nifty_500: true,
        listing_date: '1995-01-01',
        composite_score: '-3.14',
        confidence_band: 'HIGH',
        backing_ic: '0.062',
        family_trend: 'CHOPPY',
        family_volatility: 'NORMAL',
        family_volume: 'EXPANDING',
        family_path: 'WHIPSAW',
        family_sector: 'LAGGING',
        rs_residual_6m: '-0.041500',
        realized_vol_60d: '0.225000',
        formation_max_dd: '-0.095000',
        listing_age_days: 11000,
        log_price: '7.3210',
        ret_1m: '-0.0150', ret_3m: '0.0420', ret_6m: '0.0850', ret_12m: '0.1500',
        rs_1m_nifty500: '-0.0120', rs_3m_nifty500: '0.0080',
        rs_pctile_3m: '0.4200',
        realized_vol_63: '0.2210',
        atr_21: '14.5000',
        max_drawdown_252: '-0.1850',
        drawdown_ratio_252: '0.6500',
        ema_10_stock: '1490.0000', ema_20_stock: '1480.0000',
        ema_50_stock: '1450.0000', ema_200_stock: '1300.0000',
        weinstein_gate_pass: true,
        stage1_base_qualifies: false,
        volume_expansion: '1.2500',
        avg_volume_20: 12500000,
        effort_ratio_63: '0.9200',
        rs_state: 'STAGE_2',
        momentum_state: 'NEUTRAL',
        risk_state: 'NORMAL',
        volume_state: 'EXPANDING',
        history_gate_pass: true,
        liquidity_gate_pass: true,
        state_weinstein_pass: true,
        state_since_date: '2026-04-15',
        scorecard_features: { rs_z: 0.5, vol_pct: 0.42 },
        conviction_tape: { '1m': 'NEGATIVE', '3m': null, '6m': null, '12m': null },
        open_signal_calls: [
          {
            cell_id: 'cell-1',
            cell_name: 'Large 1m AVOID signal',
            tenure: '1m',
            cap_tier: 'Large',
            action: 'NEGATIVE',
            confidence: -4,
            entry_date: '2026-05-22',
            cell_explain: 'Mega-cap breakdown.',
            predicted_excess: -0.0064,
            fired_predicates: null,
          },
        ],
        composite_30d_trajectory: [
          { date: '2026-05-13', composite: -3.14, confidence: 'industry_grade' },
        ],
        macro_overlays: null,
        refreshed_at: '2026-05-23T14:30:00Z',
      },
    ])

    const d = await getStockDeepdive('RELIANCE')
    expect(d).not.toBeNull()
    if (!d) return
    expect(d.symbol).toBe('RELIANCE')
    expect(d.composite_score).toBeCloseTo(-3.14)
    expect(d.backing_ic).toBeCloseTo(0.062)
    expect(d.ret_3m).toBeCloseTo(0.042)
    expect(d.weinstein_gate_pass).toBe(true)
    expect(d.state_since_date).toBe('2026-04-15')
    expect(d.conviction_tape['1m']).toBe('NEGATIVE')
    expect(d.conviction_tape['3m']).toBeNull()
    expect(d.open_signal_calls).toHaveLength(1)
    expect(d.open_signal_calls[0].action).toBe('NEGATIVE')
    expect(d.open_signal_calls[0].predicted_excess).toBeCloseTo(-0.0064)
    expect(d.composite_30d_trajectory).toHaveLength(1)
    expect(d.composite_30d_trajectory[0].composite).toBeCloseTo(-3.14)
    expect(d.scorecard_features).toEqual({ rs_z: 0.5, vol_pct: 0.42 })
    expect(d.macro_overlays).toBeNull()
  })

  it('handles null JSONB sections (returns empty arrays / null objects)', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        instrument_id: '22222222-2222-2222-2222-222222222222',
        symbol: 'NEWCO',
        company_name: 'NewCo Ltd',
        sector: null, industry: null, tier: 'Micro',
        in_nifty_50: false, in_nifty_100: false, in_nifty_500: false,
        listing_date: '2025-01-01',
        composite_score: null, confidence_band: 'LOW', backing_ic: null,
        family_trend: null, family_volatility: null, family_volume: null,
        family_path: null, family_sector: null,
        rs_residual_6m: null, realized_vol_60d: null, formation_max_dd: null,
        listing_age_days: 100, log_price: null,
        ret_1m: null, ret_3m: null, ret_6m: null, ret_12m: null,
        rs_1m_nifty500: null, rs_3m_nifty500: null, rs_pctile_3m: null,
        realized_vol_63: null, atr_21: null, max_drawdown_252: null,
        drawdown_ratio_252: null,
        ema_10_stock: null, ema_20_stock: null, ema_50_stock: null, ema_200_stock: null,
        weinstein_gate_pass: false, stage1_base_qualifies: false,
        volume_expansion: null, avg_volume_20: 0, effort_ratio_63: null,
        rs_state: null, momentum_state: null, risk_state: null, volume_state: null,
        history_gate_pass: false, liquidity_gate_pass: false,
        state_weinstein_pass: false, state_since_date: null,
        scorecard_features: null, conviction_tape: null,
        open_signal_calls: null, composite_30d_trajectory: null,
        macro_overlays: null, refreshed_at: null,
      },
    ])
    const d = await getStockDeepdive('NEWCO')
    expect(d).not.toBeNull()
    if (!d) return
    expect(d.composite_score).toBeNull()
    expect(d.conviction_tape).toEqual({})
    expect(d.open_signal_calls).toEqual([])
    expect(d.composite_30d_trajectory).toEqual([])
    expect(d.scorecard_features).toBeNull()
  })
})
