import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import { InfoTooltip } from '../InfoTooltip'

describe('InfoTooltip', () => {
  it('renders the trigger button', () => {
    render(<InfoTooltip content="Test explanation" />)
    expect(screen.getByRole('button', { name: /info/i })).toBeInTheDocument()
  })
})
