import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { CommentaryBlock } from '../CommentaryBlock'

describe('CommentaryBlock', () => {
  it('renders the narrative text', () => {
    render(<CommentaryBlock narrative="Market breadth is improving." />)
    expect(screen.getByText('Market breadth is improving.')).toBeInTheDocument()
  })

  it('renders context cards when provided', () => {
    render(
      <CommentaryBlock
        narrative="Strong regime."
        contextCards={[
          { label: 'Investable', value: '42 stocks' },
          { label: 'Leaders', value: '18' },
        ]}
      />
    )
    expect(screen.getByText('Investable')).toBeInTheDocument()
    expect(screen.getByText('42 stocks')).toBeInTheDocument()
    expect(screen.getByText('Leaders')).toBeInTheDocument()
    expect(screen.getByText('18')).toBeInTheDocument()
  })

  it('renders without context cards', () => {
    render(<CommentaryBlock narrative="No cards here." />)
    expect(screen.getByText('No cards here.')).toBeInTheDocument()
  })

  it('renders data_as_of when provided', () => {
    render(<CommentaryBlock narrative="Latest." dataAsOf="2026-05-09" />)
    expect(screen.getByText(/2026-05-09/)).toBeInTheDocument()
  })

  it('renders delta badge when delta is provided', () => {
    render(
      <CommentaryBlock
        narrative="Test."
        contextCards={[{ label: 'Leaders', value: '30', delta: '+5', deltaPositive: true }]}
      />
    )
    expect(screen.getByText('+5')).toBeInTheDocument()
  })
})
