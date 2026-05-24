import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ConvictionTape } from '../ConvictionTape'
import type { ConvictionTape as Tape } from '@/lib/api/v1'

const allPosTape: Tape = {
  '1m':  { direction: 'POSITIVE', ic: 0.041, rule_count: 2, top_rule_id: 'A' },
  '3m':  { direction: 'POSITIVE', ic: 0.058, rule_count: 3, top_rule_id: 'B' },
  '6m':  { direction: 'POSITIVE', ic: 0.064, rule_count: 2, top_rule_id: 'C' },
  '12m': { direction: 'POSITIVE', ic: 0.052, rule_count: 1, top_rule_id: 'D' },
}

const mixedTape: Tape = {
  '1m':  { direction: 'NEUTRAL',  ic: 0.0,    rule_count: 0, top_rule_id: null },
  '3m':  { direction: 'POSITIVE', ic: 0.058,  rule_count: 3, top_rule_id: 'B' },
  '6m':  { direction: 'NEUTRAL',  ic: 0.0,    rule_count: 0, top_rule_id: null },
  '12m': { direction: 'NEGATIVE', ic: -0.041, rule_count: 1, top_rule_id: 'X' },
}

describe('ConvictionTape', () => {
  it('renders all 4 segments', () => {
    render(<ConvictionTape tape={allPosTape} />)
    expect(screen.getByText('1m')).toBeInTheDocument()
    expect(screen.getByText('3m')).toBeInTheDocument()
    expect(screen.getByText('6m')).toBeInTheDocument()
    expect(screen.getByText('12m')).toBeInTheDocument()
  })

  it('applies signal-pos background for POSITIVE segments', () => {
    const { container } = render(<ConvictionTape tape={allPosTape} />)
    const segments = container.querySelectorAll('button')
    segments.forEach(btn => {
      expect(btn.className).toContain('bg-signal-pos')
    })
  })

  it('applies signal-neg for NEGATIVE and ink-tertiary for NEUTRAL', () => {
    const { container } = render(<ConvictionTape tape={mixedTape} />)
    const segments = container.querySelectorAll('button')
    // Verify at least one of each color is present
    const allClasses = Array.from(segments).map(b => b.className).join(' ')
    expect(allClasses).toContain('bg-signal-pos')
    expect(allClasses).toContain('bg-signal-neg')
    expect(allClasses).toContain('bg-ink-tertiary')
  })

  it('calls onSegmentClick with the tenure when clicked', () => {
    const handler = vi.fn()
    render(<ConvictionTape tape={allPosTape} onSegmentClick={handler} />)
    fireEvent.click(screen.getByText('3m'))
    expect(handler).toHaveBeenCalledWith('3m')
  })

  it('disables click when no handler is passed', () => {
    const { container } = render(<ConvictionTape tape={allPosTape} />)
    container.querySelectorAll('button').forEach(btn => {
      expect(btn).toBeDisabled()
    })
  })
})
