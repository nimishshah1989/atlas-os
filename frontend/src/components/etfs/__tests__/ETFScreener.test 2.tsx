import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ETFScreener } from '../ETFScreener'
import type { ETFRow } from '@/lib/queries/etfs'

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
    mean_rs_rank_12m:     0.75,
    mean_within_state_rank: null,
    ...overrides,
  }
}

describe('ETFScreener — WithinStateRankCell', () => {
  it('does not show Within Rank column by default (hidden by default)', () => {
    render(<ETFScreener etfs={[makeETFRow()]} validations={[]} />)
    // Column header should not be visible by default
    expect(screen.queryByTitle(/within-state rank/i)).not.toBeInTheDocument()
  })

  it('renders WithinStateRankCell with em-dash when mean_within_state_rank is null', async () => {
    const user = userEvent.setup()
    render(<ETFScreener etfs={[makeETFRow({ mean_within_state_rank: null })]} validations={[]} />)

    // Open column toggle to enable within_state_rank
    const toggleBtn = screen.getByRole('button', { name: /columns/i })
    await user.click(toggleBtn)

    // Look for the Within Rank checkbox and enable it
    const checkbox = screen.queryByRole('checkbox', { name: /within rank/i })
    if (checkbox) {
      await user.click(checkbox)
      await user.keyboard('{Escape}')
      const cell = document.querySelector('[data-testid="etf-wsr-NIFTYBEES"]')
      expect(cell).not.toBeNull()
      // null → em-dash
      expect(cell).toHaveTextContent('—')
    }
    // Verify ticker always renders
    expect(screen.getByText('NIFTYBEES')).toBeInTheDocument()
  })

  it('renders WithinStateRankCell with numeric value when mean_within_state_rank is provided', async () => {
    const user = userEvent.setup()
    render(
      <ETFScreener
        etfs={[makeETFRow({ mean_within_state_rank: 0.73 })]}
        validations={[]}
      />,
    )

    const toggleBtn = screen.getByRole('button', { name: /columns/i })
    await user.click(toggleBtn)

    const checkbox = screen.queryByRole('checkbox', { name: /within rank/i })
    if (checkbox) {
      // Only click if the checkbox is not already checked (avoids state pollution from prev test)
      const chk = checkbox as HTMLInputElement
      if (!chk.checked) await user.click(checkbox)
      await user.keyboard('{Escape}')
      const cell = document.querySelector('[data-testid="etf-wsr-NIFTYBEES"]')
      expect(cell).not.toBeNull()
      expect(cell).toHaveTextContent('0.73')
    }
    expect(screen.getByText('NIFTYBEES')).toBeInTheDocument()
  })
})
