import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ValidatedBadge } from '../ValidatedBadge'
import type { ComponentValidation } from '@/lib/queries/component_validation'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeValidation(overrides: Partial<ComponentValidation> = {}): ComponentValidation {
  return {
    component_name: 'rs',
    badge: 'Leader',
    threshold_range: '>=80',
    implied_action: 'favour_long',
    horizon_days: 63,
    mean_ic: 0.04,
    ic_ir: 0.62,
    q5_q1_spread: 0.055,
    status: 'validated',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// status === 'validated'
// ---------------------------------------------------------------------------

describe('ValidatedBadge — validated', () => {
  it('renders the label', () => {
    render(<ValidatedBadge label="Leader" validation={makeValidation()} />)
    expect(screen.getByText(/Leader/)).toBeInTheDocument()
  })

  it('applies signal-pos class when ic_ir >= 0', () => {
    const { container } = render(
      <ValidatedBadge label="Leader" validation={makeValidation({ ic_ir: 0.62 })} />,
    )
    expect(container.firstChild).toHaveClass('text-signal-pos')
  })

  it('applies signal-neg class when ic_ir < 0', () => {
    const { container } = render(
      <ValidatedBadge label="Leader" validation={makeValidation({ ic_ir: -0.1 })} />,
    )
    expect(container.firstChild).toHaveClass('text-signal-neg')
  })

  it('renders the indicator dot', () => {
    const { container } = render(<ValidatedBadge label="Leader" validation={makeValidation()} />)
    expect(container.textContent).toContain('●')
  })

  it('title attribute contains IR value and horizon', () => {
    const { container } = render(
      <ValidatedBadge label="Leader" validation={makeValidation({ ic_ir: 0.62, horizon_days: 63 })} />,
    )
    const span = container.firstChild as HTMLElement
    expect(span.title).toContain('IR 0.62')
    expect(span.title).toContain('63d')
  })
})

// ---------------------------------------------------------------------------
// status === 'validated_inverse'
// ---------------------------------------------------------------------------

describe('ValidatedBadge — validated_inverse', () => {
  const validation = makeValidation({ status: 'validated_inverse', ic_ir: -0.89, horizon_days: 63 })

  it('renders the label', () => {
    render(<ValidatedBadge label="History Gate" validation={validation} />)
    expect(screen.getByText(/History Gate/)).toBeInTheDocument()
  })

  it('applies signal-warn class', () => {
    const { container } = render(<ValidatedBadge label="History Gate" validation={validation} />)
    expect(container.firstChild).toHaveClass('text-signal-warn')
  })

  it('renders the half-circle indicator', () => {
    const { container } = render(<ValidatedBadge label="History Gate" validation={validation} />)
    expect(container.textContent).toContain('◐')
  })

  it('title contains anti-predictive text', () => {
    const { container } = render(<ValidatedBadge label="History Gate" validation={validation} />)
    const span = container.firstChild as HTMLElement
    expect(span.title).toMatch(/anti-predictive/i)
  })
})

// ---------------------------------------------------------------------------
// status === 'weak'
// ---------------------------------------------------------------------------

describe('ValidatedBadge — weak', () => {
  const validation = makeValidation({ status: 'weak', ic_ir: 0.25 })

  it('renders the label', () => {
    render(<ValidatedBadge label="Average" validation={validation} />)
    expect(screen.getByText(/Average/)).toBeInTheDocument()
  })

  it('applies ink-tertiary class', () => {
    const { container } = render(<ValidatedBadge label="Average" validation={validation} />)
    expect(container.firstChild).toHaveClass('text-ink-tertiary')
  })

  it('renders asterisk superscript', () => {
    render(<ValidatedBadge label="Average" validation={validation} />)
    expect(screen.getByText('*')).toBeInTheDocument()
  })

  it('title contains weakly predictive text', () => {
    const { container } = render(<ValidatedBadge label="Average" validation={validation} />)
    const span = container.firstChild as HTMLElement
    expect(span.title).toMatch(/weakly predictive/i)
  })
})

// ---------------------------------------------------------------------------
// status === 'decorative'
// ---------------------------------------------------------------------------

describe('ValidatedBadge — decorative', () => {
  const validation = makeValidation({ status: 'decorative', ic_ir: 0.01 })

  it('renders continuous value when provided', () => {
    render(
      <ValidatedBadge
        label="ATR Contraction"
        validation={validation}
        decorativeContinuousValue="0.85"
      />,
    )
    expect(screen.getByText('0.85')).toBeInTheDocument()
  })

  it('uses font-mono for continuous value', () => {
    const { container } = render(
      <ValidatedBadge
        label="ATR Contraction"
        validation={validation}
        decorativeContinuousValue="0.85"
      />,
    )
    expect(container.firstChild).toHaveClass('font-mono')
  })

  it('renders plain label when no continuous value provided', () => {
    render(<ValidatedBadge label="ATR Contraction" validation={validation} />)
    expect(screen.getByText('ATR Contraction')).toBeInTheDocument()
  })

  it('applies ink-tertiary when no continuous value', () => {
    const { container } = render(
      <ValidatedBadge label="ATR Contraction" validation={validation} />,
    )
    expect(container.firstChild).toHaveClass('text-ink-tertiary')
  })
})

// ---------------------------------------------------------------------------
// validation=null fallback
// ---------------------------------------------------------------------------

describe('ValidatedBadge — no validation', () => {
  it('renders label as plain ink-tertiary text when validation is null', () => {
    const { container } = render(<ValidatedBadge label="Unknown Signal" validation={null} />)
    expect(screen.getByText('Unknown Signal')).toBeInTheDocument()
    expect(container.firstChild).toHaveClass('text-ink-tertiary')
  })

  it('renders label when validation is undefined', () => {
    render(<ValidatedBadge label="Unknown Signal" validation={undefined} />)
    expect(screen.getByText('Unknown Signal')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// size prop
// ---------------------------------------------------------------------------

describe('ValidatedBadge — size variants', () => {
  it('applies text-xs class when size="md" (default)', () => {
    const { container } = render(
      <ValidatedBadge label="Leader" validation={makeValidation()} size="md" />,
    )
    expect(container.firstChild).toHaveClass('text-xs')
  })

  it('applies text-[11px] class when size="sm"', () => {
    const { container } = render(
      <ValidatedBadge label="Leader" validation={makeValidation()} size="sm" />,
    )
    expect(container.firstChild).toHaveClass('text-[11px]')
  })
})
