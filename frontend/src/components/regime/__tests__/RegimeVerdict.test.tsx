import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { RegimeVerdict } from '../RegimeVerdict'

const BASE_PROPS = {
  regimeState: 'Cautious',
  deploymentPct: 60,
  leadingSectors: ['Banking', 'Technology'],
}

describe('RegimeVerdict', () => {
  it('renders a single sentence element (not null/empty)', () => {
    render(<RegimeVerdict {...BASE_PROPS} />)
    // Should render some visible text
    const el = screen.getByTestId('regime-verdict')
    expect(el).toBeInTheDocument()
    expect(el.textContent).not.toBe('')
  })

  it('includes the regime state in the rendered verdict', () => {
    render(<RegimeVerdict {...BASE_PROPS} />)
    const el = screen.getByTestId('regime-verdict')
    expect(el.textContent).toMatch(/Cautious/i)
  })

  it('includes the deployment percentage in the verdict', () => {
    render(<RegimeVerdict {...BASE_PROPS} />)
    const el = screen.getByTestId('regime-verdict')
    expect(el.textContent).toMatch(/60%/)
  })

  it('includes leading sector name when provided', () => {
    render(<RegimeVerdict {...BASE_PROPS} />)
    const el = screen.getByTestId('regime-verdict')
    expect(el.textContent).toMatch(/Banking/)
  })

  it('leading sectors are rendered as LinkedSector anchors pointing to /sectors/[name]', () => {
    render(<RegimeVerdict {...BASE_PROPS} />)
    const bankingLink = screen.getByRole('link', { name: /Banking/ })
    expect(bankingLink).toHaveAttribute('href', '/sectors/Banking')
    const techLink = screen.getByRole('link', { name: /Technology/ })
    expect(techLink).toHaveAttribute('href', '/sectors/Technology')
  })

  it('renders Risk-On verdict with 100% deployment', () => {
    render(<RegimeVerdict regimeState="Risk-On" deploymentPct={100} leadingSectors={['IT', 'Pharma']} />)
    const el = screen.getByTestId('regime-verdict')
    expect(el.textContent).toMatch(/Risk-On/)
    expect(el.textContent).toMatch(/100%/)
  })

  it('renders gracefully with empty leading sectors array', () => {
    render(<RegimeVerdict regimeState="Risk-Off" deploymentPct={40} leadingSectors={[]} />)
    const el = screen.getByTestId('regime-verdict')
    expect(el).toBeInTheDocument()
    expect(el.textContent).toMatch(/Risk-Off/)
  })
})
