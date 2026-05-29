import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { SignalScorecard } from '../SignalScorecard'
import type { ScorecardData } from '../SignalScorecard'
import type { MarketRegimeRow } from '@/lib/queries/regime'

// Minimal regime row stub for tests — only the fields buildXxxTile reads.
// The tile builders gracefully handle missing fields via NaN/null checks.
const REGIME_STUB = {
  date: new Date('2026-05-28'),
  regime_state: 'Cautious',
  deployment_multiplier: '0.40',
  india_vix: '14.98',
  pct_above_ema_50: '0.66',
  pct_above_ema_200: '0.50',
  ad_ratio: '1.29',
  mcclellan_oscillator: '4.04',
  new_52w_highs: 44,
  new_52w_lows: 3,
  nifty500_above_ema_50: true,
  nifty500_above_ema_200: true,
  nifty500_ema_50_slope: '0.0006',
  nifty500_ema_200_slope: '0.0004',
  pct_in_strong_states: '0.08',
  pct_weinstein_pass: '0.36',
} as unknown as MarketRegimeRow

const SCORECARD_DATA: ScorecardData = {
  trend: {
    value: '58%',
    rawValue: 0.58,
    label: 'Trend',
    source: 'atlas_stock_state_daily: stage_2a/2b/2c on latest date',
  },
  breadth: {
    value: '52%',
    rawValue: 0.52,
    label: 'Breadth',
    source: 'atlas_market_regime_daily: pct_above_ema_50',
  },
  momentum: {
    value: '+12',
    rawValue: 12,
    label: 'Momentum',
    source: 'atlas_stock_state_daily: net stage-2 entries minus exits over 5 trading days',
  },
  participation: {
    value: '64%',
    rawValue: 0.64,
    label: 'Participation',
    source: 'atlas_sector_metrics_daily: avg(1 - leadership_concentration)',
  },
}

describe('SignalScorecard', () => {
  it('renders all 4 tile labels', () => {
    render(<SignalScorecard data={SCORECARD_DATA} regime={REGIME_STUB} />)
    expect(screen.getByText('Trend')).toBeInTheDocument()
    expect(screen.getByText('Breadth')).toBeInTheDocument()
    expect(screen.getByText('Momentum')).toBeInTheDocument()
    expect(screen.getByText('Participation')).toBeInTheDocument()
  })

  it('renders trend/breadth/participation primary values + McClellan as momentum primary', () => {
    // 2026-05-29: momentum primary is now McClellan Oscillator (from regime
    // row), not data.momentum.value. The +12 net-stage-2-flow is gone.
    render(<SignalScorecard data={SCORECARD_DATA} regime={REGIME_STUB} />)
    expect(screen.getByText('58%')).toBeInTheDocument()
    expect(screen.getByText('52%')).toBeInTheDocument()
    expect(screen.getByText('4.0')).toBeInTheDocument() // mcclellan_oscillator from stub, formatted .toFixed(1)
    expect(screen.getByText('64%')).toBeInTheDocument()
  })

  it('renders exactly 4 tooltip info buttons (one per tile)', () => {
    render(<SignalScorecard data={SCORECARD_DATA} regime={REGIME_STUB} />)
    const infoBtns = screen.getAllByRole('button', { name: /info/i })
    expect(infoBtns.length).toBe(4)
  })

  it('renders n/a for trend tile when its data value is null', () => {
    const dataWithNull: ScorecardData = {
      ...SCORECARD_DATA,
      trend: { ...SCORECARD_DATA.trend, value: null, rawValue: null },
    }
    render(<SignalScorecard data={dataWithNull} regime={REGIME_STUB} />)
    expect(screen.getByText('n/a')).toBeInTheDocument()
  })
})
