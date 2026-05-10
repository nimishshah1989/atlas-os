import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FundDeepDiveHeader } from '../FundDeepDiveHeader'
import type { FundMasterRow } from '@/lib/queries/funds'

const BASE_MASTER: FundMasterRow = {
  mstar_id: 'F1',
  scheme_name: 'Atlas Multi-Cap Growth Fund',
  amc: 'Atlas AMC',
  category_name: 'Multi Cap',
  broad_category: 'Equity',
  inception_date: new Date('2018-01-01'),
  nav_state_as_of: null,
  composition_as_of: null,
  holdings_as_of: null,
  nav_state: 'Leader NAV',
  composition_state: 'Aligned',
  holdings_state: 'Strong-Holdings',
  recommendation: 'Recommended',
  weeks_in_current_state: '12',
  performance_gate: true,
  sectors_gate: true,
  stocks_gate: true,
  market_gate: true,
  entry_trigger: false,
  exit_trigger: false,
  reduce_trigger: false,
  add_trigger: false,
  data_as_of: null,
}

describe('FundDeepDiveHeader', () => {
  it('renders scheme_name as h1', () => {
    render(<FundDeepDiveHeader master={BASE_MASTER} />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Atlas Multi-Cap Growth Fund')
  })

  it('renders breadcrumb back to /funds', () => {
    render(<FundDeepDiveHeader master={BASE_MASTER} />)
    const link = screen.getByRole('link', { name: /Funds/ })
    expect(link).toHaveAttribute('href', '/funds')
  })

  it('renders amc and category in subline', () => {
    render(<FundDeepDiveHeader master={BASE_MASTER} />)
    expect(screen.getByText(/Atlas AMC.*Multi Cap/)).toBeInTheDocument()
  })

  it('renders weeks-in-state with formatted weeks', () => {
    render(<FundDeepDiveHeader master={BASE_MASTER} />)
    expect(screen.getByText(/12w in current state/)).toBeInTheDocument()
  })

  it('handles null weeks_in_current_state via em-dash', () => {
    const m = { ...BASE_MASTER, weeks_in_current_state: null }
    render(<FundDeepDiveHeader master={m} />)
    expect(screen.getByText(/— in current state/)).toBeInTheDocument()
  })
})
