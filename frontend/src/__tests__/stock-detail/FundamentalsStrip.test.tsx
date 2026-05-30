// Regression: /v1/tv/metrics serializes Decimal columns as JSON strings, so
// the strip receives string values at runtime. Calling .toFixed() on a string
// threw "toFixed is not a function" and crashed the whole stock-detail render.

import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { FundamentalsStrip } from '@/components/v6/stock-detail/FundamentalsStrip'

describe('FundamentalsStrip', () => {
  it('formats string-typed Decimal fields without crashing', () => {
    const { container } = render(
      <FundamentalsStrip pe="22.1341" ps="1.7286" pb="2.8" debtToEquity="0.4403" roe="9.2461" />,
    )
    const text = container.textContent ?? ''
    expect(text).toContain('22.1') // pe → 1 decimal
    expect(text).toContain('9.2%') // roe → percent
    expect(text).toContain('0.4') // debt/eq
  })

  it('still formats native numbers', () => {
    const { container } = render(
      <FundamentalsStrip pe={22.13} ps={1.73} pb={2.8} debtToEquity={0.44} roe={9.25} />,
    )
    expect(container.textContent ?? '').toContain('22.1')
  })

  it('renders em-dash for null / non-numeric', () => {
    const { container } = render(
      <FundamentalsStrip pe={null} ps={null} pb={null} debtToEquity={null} roe={null} />,
    )
    expect((container.textContent ?? '').includes('—')).toBe(true)
  })
})
