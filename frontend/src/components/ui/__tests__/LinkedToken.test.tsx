import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { LinkedTicker, LinkedSector } from '../LinkedToken'

describe('LinkedToken', () => {
  it('LinkedTicker renders an anchor to the stock detail route', () => {
    render(<LinkedTicker symbol="ANANTRAJ" />)
    const a = screen.getByRole('link', { name: /ANANTRAJ/ })
    expect(a).toHaveAttribute('href', '/stocks/ANANTRAJ')
  })
  it('LinkedSector renders an anchor to the sector route', () => {
    render(<LinkedSector sector="Banking" />)
    expect(screen.getByRole('link', { name: /Banking/ })).toHaveAttribute('href', '/sectors/Banking')
  })
  it('LinkedTicker with null symbol renders an em-dash, not a broken link', () => {
    render(<LinkedTicker symbol={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.queryByRole('link')).toBeNull()
  })
})
