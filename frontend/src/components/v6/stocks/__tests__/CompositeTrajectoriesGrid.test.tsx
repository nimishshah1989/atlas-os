// frontend/src/components/v6/stocks/__tests__/CompositeTrajectoriesGrid.test.tsx
import { describe, it, expect } from 'vitest'
import type { LandscapeRow } from '@/lib/queries/v6/stocks-landscape'
import { pickSixStocks } from '../helpers'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeRow(
  symbol: string,
  action: 'BUY' | 'AVOID' | 'WATCH',
  composite: string,
  trajLength: number,
): LandscapeRow {
  return {
    instrument_id: symbol,
    symbol,
    company_name: null,
    sector: 'Test',
    industry: null,
    cap_tier: 'Large',
    ret_1m: null, ret_3m: null, ret_6m: null, ret_12m: null,
    rs_1m_nifty500: null, rs_3m_nifty500: null,
    composite_score: composite,
    conviction_tier: null, confidence_label: null,
    action,
    bubble_quadrant: null, liquidity_proxy_cr: null, close_price: null,
    matrix_tenure_dominant: null, matrix_action_sign: null,
    cell_id: null, cell_ic: null, cell_tenure: null, cell_action: null,
    cell_fire_date: null,
    composite_trajectory_30d:
      trajLength >= 2
        ? Array.from({ length: trajLength }, (_, i) => ({
            date: `2026-05-${(i + 1).toString().padStart(2, '0')}`,
            score: parseFloat(composite) + i * 0.1,
          }))
        : trajLength === 1
        ? [{ date: '2026-05-01', score: parseFloat(composite) }]
        : null,
    refreshed_at: null,
  }
}

// ---------------------------------------------------------------------------
// Tests — requireTrajectory: true (default / CompositeTrajectoriesGrid usage)
// ---------------------------------------------------------------------------

describe('pickSixStocks (requireTrajectory: true)', () => {
  it('returns empty array when no data', () => {
    expect(pickSixStocks([], { requireTrajectory: true })).toHaveLength(0)
  })

  it('returns up to 3 BUYs + 3 AVOIDs with trajectory', () => {
    const data = [
      makeRow('A', 'BUY', '8.0', 5),
      makeRow('B', 'BUY', '7.0', 5),
      makeRow('C', 'BUY', '6.0', 5),
      makeRow('D', 'BUY', '5.0', 5),
      makeRow('E', 'AVOID', '-8.0', 5),
      makeRow('F', 'AVOID', '-7.0', 5),
      makeRow('G', 'AVOID', '-6.0', 5),
      makeRow('H', 'AVOID', '-5.0', 5),
    ]
    const picks = pickSixStocks(data, { requireTrajectory: true })
    expect(picks).toHaveLength(6)
    const buys = picks.filter(p => p.action === 'BUY')
    const avoids = picks.filter(p => p.action === 'AVOID')
    expect(buys).toHaveLength(3)
    expect(avoids).toHaveLength(3)
  })

  it('BUYs are sorted descending by composite (highest first)', () => {
    const data = [
      makeRow('X', 'BUY', '5.0', 5),
      makeRow('Y', 'BUY', '9.0', 5),
      makeRow('Z', 'BUY', '7.0', 5),
    ]
    const picks = pickSixStocks(data, { requireTrajectory: true })
    const buys = picks.filter(p => p.action === 'BUY')
    expect(buys[0].symbol).toBe('Y')
    expect(buys[1].symbol).toBe('Z')
    expect(buys[2].symbol).toBe('X')
  })

  it('AVOIDs are sorted ascending by composite (worst first)', () => {
    const data = [
      makeRow('X', 'AVOID', '-5.0', 5),
      makeRow('Y', 'AVOID', '-9.0', 5),
      makeRow('Z', 'AVOID', '-7.0', 5),
    ]
    const picks = pickSixStocks(data, { requireTrajectory: true })
    const avoids = picks.filter(p => p.action === 'AVOID')
    expect(avoids[0].symbol).toBe('Y')
    expect(avoids[1].symbol).toBe('Z')
    expect(avoids[2].symbol).toBe('X')
  })

  it('excludes stocks with null trajectory', () => {
    const data = [
      makeRow('A', 'BUY', '8.0', 0),   // null trajectory
      makeRow('B', 'BUY', '7.0', 5),
    ]
    const picks = pickSixStocks(data, { requireTrajectory: true })
    expect(picks.map(p => p.symbol)).not.toContain('A')
  })

  it('excludes stocks with only 1 trajectory point', () => {
    const data = [
      makeRow('A', 'BUY', '8.0', 1),   // single point — not sparkline-able
      makeRow('B', 'BUY', '7.0', 5),
    ]
    const picks = pickSixStocks(data, { requireTrajectory: true })
    expect(picks.map(p => p.symbol)).not.toContain('A')
  })

  it('handles fewer than 3 BUYs gracefully', () => {
    const data = [
      makeRow('A', 'BUY', '8.0', 5),
      makeRow('B', 'AVOID', '-8.0', 5),
      makeRow('C', 'AVOID', '-7.0', 5),
    ]
    const picks = pickSixStocks(data, { requireTrajectory: true })
    expect(picks).toHaveLength(3)
    expect(picks.filter(p => p.action === 'BUY')).toHaveLength(1)
    expect(picks.filter(p => p.action === 'AVOID')).toHaveLength(2)
  })

  it('excludes WATCH stocks', () => {
    const data = [
      makeRow('W', 'WATCH', '1.0', 5),
      makeRow('B', 'BUY', '8.0', 5),
    ]
    const picks = pickSixStocks(data, { requireTrajectory: true })
    expect(picks.map(p => p.symbol)).not.toContain('W')
  })
})

// ---------------------------------------------------------------------------
// Tests — requireTrajectory: false (SixPicksWorthClick usage)
// ---------------------------------------------------------------------------

describe('pickSixStocks (requireTrajectory: false)', () => {
  it('includes stocks with no trajectory when requireTrajectory is false', () => {
    const data = [
      makeRow('A', 'BUY', '8.0', 0),   // no trajectory
      makeRow('B', 'BUY', '7.0', 5),
    ]
    const picks = pickSixStocks(data, { requireTrajectory: false })
    expect(picks.map(p => p.symbol)).toContain('A')
    expect(picks.map(p => p.symbol)).toContain('B')
  })

  it('still excludes null composite_score rows', () => {
    const data: LandscapeRow[] = [
      { ...makeRow('A', 'BUY', '8.0', 0), composite_score: null },
      makeRow('B', 'BUY', '7.0', 5),
    ]
    const picks = pickSixStocks(data, { requireTrajectory: false })
    expect(picks.map(p => p.symbol)).not.toContain('A')
  })
})
