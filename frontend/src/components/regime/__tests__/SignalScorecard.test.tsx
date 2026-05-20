import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { SignalScorecard } from '../SignalScorecard'
import type { ScorecardData } from '../SignalScorecard'

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
    render(<SignalScorecard data={SCORECARD_DATA} />)
    expect(screen.getByText('Trend')).toBeInTheDocument()
    expect(screen.getByText('Breadth')).toBeInTheDocument()
    expect(screen.getByText('Momentum')).toBeInTheDocument()
    expect(screen.getByText('Participation')).toBeInTheDocument()
  })

  it('renders all 4 tile values', () => {
    render(<SignalScorecard data={SCORECARD_DATA} />)
    expect(screen.getByText('58%')).toBeInTheDocument()
    expect(screen.getByText('52%')).toBeInTheDocument()
    expect(screen.getByText('+12')).toBeInTheDocument()
    expect(screen.getByText('64%')).toBeInTheDocument()
  })

  it('renders exactly 4 tooltip info buttons (one per tile)', () => {
    render(<SignalScorecard data={SCORECARD_DATA} />)
    const infoBtns = screen.getAllByRole('button', { name: /info/i })
    expect(infoBtns.length).toBe(4)
  })

  it('renders n/a when a tile value is null', () => {
    const dataWithNull: ScorecardData = {
      ...SCORECARD_DATA,
      momentum: { ...SCORECARD_DATA.momentum, value: null, rawValue: null },
    }
    render(<SignalScorecard data={dataWithNull} />)
    expect(screen.getByText('n/a')).toBeInTheDocument()
  })
})
