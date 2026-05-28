// frontend/src/components/v6/stocks/__tests__/ConvictionBubbleChart.test.tsx
import { describe, it, expect } from 'vitest'
import type { LandscapeRow } from '@/lib/queries/v6/stocks-landscape'
import { mapAction, quadrant, buildDatum } from '../ConvictionBubbleChart'

// ---------------------------------------------------------------------------
// Unit tests for bubble chart data transformations
// (Component rendering tested separately via dev server — Recharts requires canvas)
// ---------------------------------------------------------------------------

// Minimal LandscapeRow fixture
function makeRow(
  overrides: Partial<LandscapeRow> & { rs_3m_nifty500: string; composite_score: string; action: 'BUY' | 'AVOID' | 'WATCH' },
): LandscapeRow {
  return {
    instrument_id: 'TEST',
    symbol: 'TEST',
    company_name: null,
    sector: null,
    industry: null,
    cap_tier: 'Large',
    ret_1m: null, ret_3m: null, ret_6m: null, ret_12m: null,
    rs_1m_nifty500: null,
    conviction_tier: null, confidence_label: null,
    bubble_quadrant: null, liquidity_proxy_cr: null, close_price: null,
    matrix_tenure_dominant: null, matrix_action_sign: null,
    cell_id: null, cell_ic: null, cell_tenure: null, cell_action: null,
    cell_fire_date: null,
    composite_trajectory_30d: null,
    refreshed_at: null,
    ...overrides,
  }
}

// Sample data
const sample = makeRow({
  action: 'BUY',
  rs_3m_nifty500: '0.092',   // +9.2pp
  composite_score: '8.4',
})

describe('mapAction', () => {
  it('maps BUY action to signal-pos CSS var', () => {
    expect(mapAction('BUY')).toBe('var(--color-signal-pos)')
  })

  it('maps AVOID action to signal-neg CSS var', () => {
    expect(mapAction('AVOID')).toBe('var(--color-signal-neg)')
  })

  it('maps WATCH action to signal-warn CSS var', () => {
    expect(mapAction('WATCH')).toBe('var(--color-signal-warn)')
  })

  it('maps null action to ink-4 CSS var (neutral)', () => {
    expect(mapAction(null)).toBe('var(--color-ink-4)')
  })
})

describe('quadrant', () => {
  it('classifies clean_buy (positive RS + positive composite)', () => {
    expect(quadrant(9.2, 8.4)).toBe('clean_buy')
  })

  it('classifies contrarian_buy (negative RS + positive composite)', () => {
    expect(quadrant(-5, 3)).toBe('contrarian_buy')
  })

  it('classifies clean_avoid (negative RS + negative composite)', () => {
    expect(quadrant(-6, -5)).toBe('clean_avoid')
  })

  it('classifies rs_holding_composite_down (positive RS + negative composite)', () => {
    expect(quadrant(5, -2)).toBe('rs_holding_composite_down')
  })

  it('composite = 0 with positive RS → clean_buy (boundary)', () => {
    expect(quadrant(5, 0)).toBe('clean_buy')
  })

  it('composite = 0 with negative RS → contrarian_buy (boundary)', () => {
    expect(quadrant(-5, 0)).toBe('contrarian_buy')
  })
})

describe('buildDatum', () => {
  it('returns null when rs_3m_nifty500 is null', () => {
    const row = makeRow({ action: 'BUY', rs_3m_nifty500: '0.1', composite_score: '5.0' })
    row.rs_3m_nifty500 = null
    expect(buildDatum(row)).toBeNull()
  })

  it('returns null when composite_score is null', () => {
    const row = makeRow({ action: 'BUY', rs_3m_nifty500: '0.1', composite_score: '5.0' })
    row.composite_score = null
    expect(buildDatum(row)).toBeNull()
  })

  it('converts rs_3m_nifty500 from ratio to pp on x axis', () => {
    const d = buildDatum(sample)
    expect(d).not.toBeNull()
    expect(d!.x).toBeCloseTo(9.2, 1)
  })

  it('parses composite_score correctly on y axis', () => {
    const d = buildDatum(sample)
    expect(d).not.toBeNull()
    expect(d!.y).toBe(8.4)
  })

  it('BUY stock in clean_buy quadrant: positive RS + positive composite', () => {
    const d = buildDatum(sample)
    expect(d).not.toBeNull()
    expect(d!.x).toBeGreaterThan(0)
    expect(d!.y).toBeGreaterThan(0)
  })

  it('assigns correct action color from mapAction', () => {
    const d = buildDatum(sample)
    expect(d).not.toBeNull()
    expect(d!.color).toBe(mapAction('BUY'))
  })

  it('z is always >= 1 (minimum clamp)', () => {
    // z = raw liquidity_proxy_cr clamped to [1, 1_000_000]; null liq → 1
    const d = buildDatum(sample)
    expect(d).not.toBeNull()
    expect(d!.z).toBeGreaterThanOrEqual(1)
  })

  it('z reflects actual liquidity when provided', () => {
    const row = makeRow({
      action: 'BUY',
      rs_3m_nifty500: '0.092',
      composite_score: '8.4',
      liquidity_proxy_cr: '5000',
    })
    const d = buildDatum(row)
    expect(d).not.toBeNull()
    expect(d!.z).toBe(5000)
  })

  it('z is clamped to 1_000_000 max', () => {
    const row = makeRow({
      action: 'BUY',
      rs_3m_nifty500: '0.092',
      composite_score: '8.4',
      liquidity_proxy_cr: '9999999',
    })
    const d = buildDatum(row)
    expect(d).not.toBeNull()
    expect(d!.z).toBe(1_000_000)
  })
})
