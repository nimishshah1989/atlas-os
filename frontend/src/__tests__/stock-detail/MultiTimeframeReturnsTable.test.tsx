// C1: the "Alpha vs Nifty 500" column must populate for all 5 horizons
// (1W/1M/3M/6M/12M) when the latest metric row carries alpha_* fields.

import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { MultiTimeframeReturnsTable } from '@/components/v6/stock-detail/MultiTimeframeReturnsTable'

const latest = {
  ret_1w: '-0.0210', ret_1m: '-0.0487', ret_3m: '-0.0553', ret_6m: '-0.1571', ret_12m: '-0.0719',
  alpha_1w: '-0.0213', alpha_1m: '-0.0475', alpha_3m: '-0.0200', alpha_6m: '-0.1095', alpha_12m: '-0.0746',
}

describe('MultiTimeframeReturnsTable', () => {
  it('renders a numeric alpha cell for all five horizons when alpha_* are present', () => {
    const { container } = render(<MultiTimeframeReturnsTable latest={latest} />)
    const rows = container.querySelectorAll('tbody tr')
    expect(rows.length).toBe(5)
    rows.forEach((tr) => {
      const alphaCell = tr.querySelectorAll('td')[2]
      expect(alphaCell.textContent).not.toBe('—')
      expect(alphaCell.textContent).toMatch(/%$/)
    })
  })

  it('renders "—" for alpha when the field is missing', () => {
    const { container } = render(<MultiTimeframeReturnsTable latest={{ ret_1w: '0.01' }} />)
    const firstAlpha = container.querySelectorAll('tbody tr')[0].querySelectorAll('td')[2]
    expect(firstAlpha.textContent).toBe('—')
  })
})
