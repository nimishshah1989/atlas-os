import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ELI5Tooltip } from '../ELI5Tooltip'

describe('ELI5Tooltip', () => {
  it('renders the wrapped children when the registry hit exists', () => {
    render(<ELI5Tooltip term="quality_momentum">Quality momentum</ELI5Tooltip>)
    expect(screen.getByText('Quality momentum')).toBeInTheDocument()
  })

  it('falls back to children with no decoration when term is not in registry', () => {
    render(<ELI5Tooltip term="nonexistent_term_xyz">plain text</ELI5Tooltip>)
    expect(screen.getByText('plain text')).toBeInTheDocument()
  })

  it('uses the term as text when no children are provided', () => {
    render(<ELI5Tooltip term="ic_mean" />)
    expect(screen.getByText('ic_mean')).toBeInTheDocument()
  })

  it('applies dotted-underline class to registry-hit terms', () => {
    const { container } = render(<ELI5Tooltip term="quality_momentum">QM</ELI5Tooltip>)
    const wrapper = container.querySelector('span.decoration-dotted')
    expect(wrapper).not.toBeNull()
  })
})
