import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ComponentValidationRow } from '../ComponentValidationRow'
import type { ComponentValidation } from '@/lib/queries/component_validation'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeValidation(overrides: Partial<ComponentValidation> = {}): ComponentValidation {
  return {
    component_name: 'rs',
    badge:          'Leader',
    threshold_range:'>=80',
    implied_action: 'favour_long',
    horizon_days:   63,
    mean_ic:        0.04,
    ic_ir:          0.62,
    q5_q1_spread:   0.055,
    status:         'validated',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Test 1: validated status — IC stats visible
// ---------------------------------------------------------------------------

describe('ComponentValidationRow — validated status', () => {
  it('renders the component label in uppercase', () => {
    render(
      <ComponentValidationRow
        componentLabel="Relative strength"
        badge="Leader"
        validation={makeValidation()}
      />,
    )
    expect(screen.getByText('Relative strength')).toBeInTheDocument()
  })

  it('renders the badge label', () => {
    render(
      <ComponentValidationRow
        componentLabel="Relative strength"
        badge="Leader"
        validation={makeValidation()}
      />,
    )
    expect(screen.getByText(/Leader/)).toBeInTheDocument()
  })

  it('renders IC stats (IR and Q5-Q1) when validation is validated', () => {
    render(
      <ComponentValidationRow
        componentLabel="Relative strength"
        badge="Leader"
        validation={makeValidation({ ic_ir: 0.62, q5_q1_spread: 0.055 })}
      />,
    )
    expect(screen.getByText(/IR \+0\.62/)).toBeInTheDocument()
    expect(screen.getByText(/Q5-Q1 \+5\.5%/)).toBeInTheDocument()
  })

  it('renders contextLine when provided', () => {
    render(
      <ComponentValidationRow
        componentLabel="Relative strength"
        badge="Leader"
        validation={makeValidation()}
        contextLine="rs_rank_12m 0.92"
      />,
    )
    expect(screen.getByText('rs_rank_12m 0.92')).toBeInTheDocument()
  })

  it('renders the component-validation-row test id', () => {
    render(
      <ComponentValidationRow
        componentLabel="Relative strength"
        badge="Leader"
        validation={makeValidation()}
      />,
    )
    expect(screen.getByTestId('component-validation-row')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 2: decorative status + continuous value
// ---------------------------------------------------------------------------

describe('ComponentValidationRow — decorative with continuous value', () => {
  const decorativeValidation = makeValidation({
    status:        'decorative',
    ic_ir:         0.01,
    q5_q1_spread:  0.002,
    component_name:'atr',
    badge:         'Contracting',
  })

  it('renders continuous value instead of binary badge label', () => {
    render(
      <ComponentValidationRow
        componentLabel="ATR contraction"
        badge="Contracting"
        validation={decorativeValidation}
        decorativeContinuousValue="0.85"
      />,
    )
    expect(screen.getByText('0.85')).toBeInTheDocument()
  })

  it('does not render IC stats for decorative status', () => {
    const { container } = render(
      <ComponentValidationRow
        componentLabel="ATR contraction"
        badge="Contracting"
        validation={decorativeValidation}
        decorativeContinuousValue="0.85"
      />,
    )
    // The IC stats div should be empty (no IR text)
    const cells = container.querySelectorAll('[data-testid="component-validation-row"] > div')
    const rightCell = cells[cells.length - 1]
    expect(rightCell.textContent).toBe('')
  })

  it('renders contextLine below badge when provided', () => {
    render(
      <ComponentValidationRow
        componentLabel="ATR contraction"
        badge="Contracting"
        validation={decorativeValidation}
        decorativeContinuousValue="0.85"
        contextLine="atr_ratio 0.85"
      />,
    )
    expect(screen.getByText('atr_ratio 0.85')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 3: null validation — no IC backing
// ---------------------------------------------------------------------------

describe('ComponentValidationRow — null validation', () => {
  it('renders badge as plain text when validation is null', () => {
    render(
      <ComponentValidationRow
        componentLabel="OBV slope"
        badge="Continuous"
        validation={null}
      />,
    )
    expect(screen.getByText('Continuous')).toBeInTheDocument()
  })

  it('renders contextLine even without validation', () => {
    render(
      <ComponentValidationRow
        componentLabel="OBV slope"
        badge="Continuous"
        validation={null}
        contextLine="Phase 5b — chart below"
      />,
    )
    expect(screen.getByText('Phase 5b — chart below')).toBeInTheDocument()
  })
})
