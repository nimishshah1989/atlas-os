import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { RegimeHeadline } from '../RegimeHeadline'
import type { MarketRegimeRow } from '@/lib/queries/regime'

const BASE_REGIME: MarketRegimeRow = {
  date: new Date('2026-05-20'),
  nifty500_close: '25000',
  nifty500_ema_50: '24000',
  nifty500_ema_200: '23000',
  nifty500_above_ema_50: true,
  nifty500_above_ema_200: true,
  nifty500_ema_50_slope: '0.25',
  nifty500_ema_200_slope: '0.10',
  pct_above_ema_20: '0.62',
  pct_above_ema_50: '0.58',
  pct_above_ema_200: '0.54',
  advances_count: 420,
  declines_count: 80,
  unchanged_count: 0,
  ad_ratio: '5.25',
  ad_line: '15000',
  ad_line_slope_21: '0.45',
  mcclellan_oscillator: '32.5',
  mcclellan_summation: '120',
  new_52w_highs: 45,
  new_52w_lows: 3,
  net_new_highs: 42,
  new_high_low_ratio: '15',
  pct_in_strong_states: '0.48',
  pct_weinstein_pass: '0.52',
  india_vix: '14.5',
  realized_vol_5d_nifty500: '0.012',
  vol_252_median_nifty500: '0.010',
  regime_state: 'Constructive',
  deployment_multiplier: '0.80',
  dislocation_active: false,
  dislocation_started: null,
}

describe('RegimeHeadline', () => {
  it('renders the regime state heading', () => {
    render(<RegimeHeadline regime={BASE_REGIME} />)
    // The h1 element contains the current regime state
    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading.textContent).toMatch(/Constructive/)
  })

  it('renders the VIX value', () => {
    render(<RegimeHeadline regime={BASE_REGIME} />)
    expect(screen.getByText(/14\.5/)).toBeInTheDocument()
  })

  it('renders a tooltip (info button) for the VIX stat', () => {
    render(<RegimeHeadline regime={BASE_REGIME} />)
    // There should be at least one info button near the VIX display
    const infoBtns = screen.getAllByRole('button', { name: /info/i })
    expect(infoBtns.length).toBeGreaterThanOrEqual(1)
  })

  it('does not render VIX tooltip when india_vix is null', () => {
    const { container } = render(<RegimeHeadline regime={{ ...BASE_REGIME, india_vix: null }} />)
    // The VIX data-validator-id span should not be present when vix is null
    const vixSpan = container.querySelector('[data-validator-id*="india_vix"]')
    expect(vixSpan).toBeNull()
  })
})
