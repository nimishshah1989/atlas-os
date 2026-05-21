import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { WithinStateRankCell } from '../WithinStateRankCell'

describe('WithinStateRankCell', () => {
  it('renders the within-state rank value to 2 decimals', () => {
    render(<WithinStateRankCell value={0.7234} />)
    expect(screen.getByText('0.72')).toBeInTheDocument()
  })

  it('renders em-dash for null', () => {
    render(<WithinStateRankCell value={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
