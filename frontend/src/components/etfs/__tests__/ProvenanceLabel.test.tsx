/**
 * Task 1.8 — Honest data provenance labelling tests.
 *
 * TDD: these tests are written BEFORE the implementation.
 *
 * Three behaviours under test:
 * 1. ETFRow with data_source='legacy' renders a "Legacy" provenance marker
 *    with a tooltip explaining what legacy-sourced means.
 * 2. Commodity ETF (theme='Gold' or theme='Silver') renders engine_state as
 *    "n/a — commodity ETF" NOT a fabricated stage badge.
 * 3. ETFRow with data_source='bottom_up' renders normally with NO legacy marker.
 *
 * FundRow with data_source='legacy' renders a "Legacy" provenance marker.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ETFScreener } from '../ETFScreener'
import type { ETFRow } from '@/lib/queries/etfs'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeETFRow(overrides: Partial<ETFRow> = {}): ETFRow {
  return {
    ticker:               'NIFTYBEES',
    etf_name:             'Nifty BeES',
    theme:                'Broad',
    linked_sector:        null,
    linked_index:         'Nifty 50',
    inception_date:       '2002-01-01',
    asset_class:          'Equity',
    fund_house:           'Nippon',
    data_as_of:           '2026-05-18',
    ret_1w:               '0.01',
    ret_1m:               '0.03',
    ret_3m:               '0.08',
    ret_6m:               '0.12',
    ret_12m:              '0.18',
    rs_pctile_3m:         '0.75',
    rs_3m_benchmark:      '0.02',
    ema_10_ratio:         '1.02',
    extension_pct:        '0.05',
    vol_63:               '0.12',
    drawdown:             '-0.03',
    volume_expansion:     '1.2',
    avg_volume_20:        '1000000',
    effort_ratio_63:      '1.1',
    above_30w_ma:         true,
    ema_10_at_20d_high:   true,
    days_in_state:        null,
    rs_state:             'Strong',
    momentum_state:       'Accelerating',
    risk_state:           null,
    weinstein_gate_pass:  true,
    history_gate_pass:    true,
    liquidity_gate_pass:  true,
    is_investable:        true,
    strength_gate:        true,
    direction_gate:       true,
    risk_gate:            true,
    sector_gate:          true,
    market_gate:          true,
    position_size_pct:    null,
    breakout_trigger:     false,
    transition_trigger:   false,
    exit_market_riskoff:  null,
    exit_sector_avoid:    null,
    exit_rs_deteriorate:  null,
    exit_momentum_collapse: null,
    exit_stop_loss:       null,
    engine_state:         'stage_2b',
    mean_rs_rank_12m:     0.75,
    mean_within_state_rank: null,
    pct_stage_2:          null,
    pct_stage_4:          null,
    data_source:          'bottom_up',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// ETF provenance tests
// ---------------------------------------------------------------------------

describe('ProvenanceLabel — ETF', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('renders a legacy provenance marker when data_source is legacy', () => {
    render(
      <ETFScreener
        etfs={[makeETFRow({ data_source: 'legacy' })]}
        validations={[]}
      />
    )
    // Should find a legacy badge/marker visible in the row
    expect(screen.getByTestId('provenance-legacy-NIFTYBEES')).toBeInTheDocument()
  })

  it('legacy provenance marker has accessible aria-label explaining legacy source', () => {
    // Note: Radix Tooltip portals do not render in JSDOM (ResizeObserver not available).
    // We verify the trigger has the accessible aria-label; visual tooltip is tested manually.
    render(
      <ETFScreener
        etfs={[makeETFRow({ data_source: 'legacy' })]}
        validations={[]}
      />
    )
    const marker = screen.getByTestId('provenance-legacy-NIFTYBEES')
    // The marker itself carries an aria-label so screen-reader users know what it means
    expect(marker).toHaveAttribute('aria-label', 'Legacy-sourced data')
  })

  it('does NOT render a legacy marker when data_source is bottom_up', () => {
    render(
      <ETFScreener
        etfs={[makeETFRow({ data_source: 'bottom_up' })]}
        validations={[]}
      />
    )
    expect(screen.queryByTestId('provenance-legacy-NIFTYBEES')).not.toBeInTheDocument()
  })

  it('commodity ETF (theme=Gold) renders engine_state as n/a text NOT a stage badge', () => {
    render(
      <ETFScreener
        etfs={[makeETFRow({ theme: 'Gold', engine_state: 'stage_2a', data_source: 'legacy' })]}
        validations={[]}
      />
    )
    // Should NOT render the fabricated stage badge text
    expect(screen.queryByText('2A BREAK')).not.toBeInTheDocument()
    // Should render the honest n/a label
    expect(screen.getByTestId('commodity-etf-na-NIFTYBEES')).toBeInTheDocument()
    expect(screen.getByTestId('commodity-etf-na-NIFTYBEES')).toHaveTextContent(/n\/a/)
  })

  it('commodity ETF (theme=Silver) renders engine_state as n/a text NOT a stage badge', () => {
    render(
      <ETFScreener
        etfs={[makeETFRow({ theme: 'Silver', engine_state: 'stage_1', data_source: 'legacy' })]}
        validations={[]}
      />
    )
    expect(screen.queryByText('1 BASE')).not.toBeInTheDocument()
    expect(screen.getByTestId('commodity-etf-na-NIFTYBEES')).toBeInTheDocument()
  })

  it('non-commodity equity ETF still renders stage badge', () => {
    render(
      <ETFScreener
        etfs={[makeETFRow({ theme: 'Broad', engine_state: 'stage_2b', data_source: 'legacy' })]}
        validations={[]}
      />
    )
    // Stage badge should render for equity ETFs
    expect(screen.getByText('2B CONF')).toBeInTheDocument()
  })
})
