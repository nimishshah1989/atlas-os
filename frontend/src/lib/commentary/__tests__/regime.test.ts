// src/lib/commentary/__tests__/regime.test.ts
import { describe, it, expect } from 'vitest'
import { generateRegimeCommentary, countBullishIndicators } from '../regime'
import type { MarketRegimeRow } from '@/lib/queries/regime'

const baseRegime: Partial<MarketRegimeRow> = {
  date: new Date('2026-05-08'),
  regime_state: 'Risk-Off',
  deployment_multiplier: '0',
  dislocation_active: false,
  dislocation_started: null,
  india_vix: '22.5',
  nifty500_above_ema_50: false,
  nifty500_above_ema_200: false,
  pct_above_ema_20: '0.28',
  pct_above_ema_50: '0.32',
  pct_above_ema_200: '0.41',
  ad_ratio: '0.6',
  ad_line_slope_21: '-0.05',
  mcclellan_oscillator: '-45',
  mcclellan_summation: '-800',
  new_52w_highs: 12,
  new_52w_lows: 89,
  net_new_highs: -77,
  new_high_low_ratio: '0.13',
  pct_in_strong_states: '0.18',
  pct_weinstein_pass: '0.22',
  nifty500_ema_50_slope: '-0.3',
  nifty500_ema_200_slope: '-0.1',
}

describe('countBullishIndicators', () => {
  it('returns total of 18', () => {
    const { total } = countBullishIndicators(baseRegime as MarketRegimeRow)
    expect(total).toBe(18)
  })

  it('counts mostly bearish in risk-off regime', () => {
    const { bullish } = countBullishIndicators(baseRegime as MarketRegimeRow)
    expect(bullish).toBeLessThan(9)
  })
})

describe('generateRegimeCommentary', () => {
  it('starts with regime state', () => {
    const result = generateRegimeCommentary(baseRegime as MarketRegimeRow)
    expect(result).toMatch(/^Market is in Risk-Off\./)
  })

  it('includes deployment percentage', () => {
    const result = generateRegimeCommentary(baseRegime as MarketRegimeRow)
    expect(result).toContain('0%')
  })

  it('includes VIX reading', () => {
    const result = generateRegimeCommentary(baseRegime as MarketRegimeRow)
    expect(result).toContain('22.5')
  })

  it('includes dislocation warning when active', () => {
    const result = generateRegimeCommentary({
      ...baseRegime,
      dislocation_active: true,
    } as MarketRegimeRow)
    expect(result).toContain('Dislocation active')
  })

  it('does not include dislocation when inactive', () => {
    const result = generateRegimeCommentary(baseRegime as MarketRegimeRow)
    expect(result).not.toContain('Dislocation')
  })

  it('mentions breadth count in format "N of 18"', () => {
    const result = generateRegimeCommentary(baseRegime as MarketRegimeRow)
    expect(result).toMatch(/\d+ of 18/)
  })
})
