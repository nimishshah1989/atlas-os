import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FundScreener } from '../FundScreener'
import type { FundRow } from '@/lib/queries/funds'

function makeFundRow(overrides: Partial<FundRow> = {}): FundRow {
  return {
    mstar_id:                   'F00000XXXX',
    scheme_name:                'Test Fund - Regular Plan',
    amc:                        'Test AMC',
    category_name:              'Large Cap',
    broad_category:             'Equity',
    data_as_of:                 '2026-05-18',
    ret_1m:                     '0.02',
    ret_3m:                     '0.07',
    ret_6m:                     '0.11',
    ret_12m:                    '0.19',
    rs_1m_category:             '0.01',
    rs_3m_category:             '0.04',
    rs_6m_category:             '0.06',
    rs_pctile_1m:               '0.55',
    rs_pctile_3m:               '0.65',
    rs_pctile_6m:               '0.70',
    realized_vol_63:            '0.14',
    drawdown_ratio_252:         '-0.08',
    nav_date:                   null,
    nav_state:                  'Uptrend',
    composition_state:          'Aligned',
    holdings_state:             'Strong',
    recommendation:             'Recommended',
    weeks_in_current_state:     '4',
    performance_gate:           true,
    sectors_gate:               true,
    stocks_gate:                true,
    market_gate:                true,
    entry_trigger:              null,
    exit_trigger:               null,
    reduce_trigger:             null,
    mean_within_state_rank:     null,
    aum_cr:                     '5000',
    aum_as_of:                  '2026-04-30',
    aligned_aum_pct:            '60',
    avoid_aum_pct:              '15',
    neutral_aum_pct:            '25',
    strong_aum_pct:             '55',
    weak_aum_pct:               '20',
    unknown_aum_pct:            '25',
    lens_as_of_date:            null,
    ...overrides,
  }
}

describe('FundScreener — WithinStateRankCell', () => {
  const noop = () => {}

  it('renders the fund screener without error', () => {
    render(
      <FundScreener
        funds={[makeFundRow()]}
        period="3M"
        activeFilter="all"
        onFilterChange={noop}
      />,
    )
    expect(screen.getByText('Test Fund - Regular Plan')).toBeInTheDocument()
  })

  it('renders WithinStateRankCell with em-dash when mean_within_state_rank is null', async () => {
    const user = userEvent.setup()
    render(
      <FundScreener
        funds={[makeFundRow({ mean_within_state_rank: null })]}
        period="3M"
        activeFilter="all"
        onFilterChange={noop}
      />,
    )

    // Open column toggle
    const toggleBtn = screen.getByRole('button', { name: /columns/i })
    await user.click(toggleBtn)

    const checkbox = screen.queryByRole('checkbox', { name: /within rank/i })
    if (checkbox) {
      await user.click(checkbox)
      await user.keyboard('{Escape}')
      const cell = document.querySelector('[data-testid="fund-wsr-F00000XXXX"]')
      expect(cell).not.toBeNull()
      expect(cell).toHaveTextContent('—')
    }
    expect(screen.getByText('Test Fund - Regular Plan')).toBeInTheDocument()
  })

  it('renders WithinStateRankCell with numeric value when mean_within_state_rank is provided', async () => {
    const user = userEvent.setup()
    render(
      <FundScreener
        funds={[makeFundRow({ mean_within_state_rank: 0.81 })]}
        period="3M"
        activeFilter="all"
        onFilterChange={noop}
      />,
    )

    const toggleBtn = screen.getByRole('button', { name: /columns/i })
    await user.click(toggleBtn)

    const checkbox = screen.queryByRole('checkbox', { name: /within rank/i })
    if (checkbox) {
      await user.click(checkbox)
      await user.keyboard('{Escape}')
      const cell = document.querySelector('[data-testid="fund-wsr-F00000XXXX"]')
      expect(cell).not.toBeNull()
      expect(cell).toHaveTextContent('0.81')
    }
    expect(screen.getByText('Test Fund - Regular Plan')).toBeInTheDocument()
  })
})
