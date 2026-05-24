import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ComponentScorecard } from '../ComponentScorecard'
import type { StockState } from '@/lib/queries/states'
import type { ComponentValidation } from '@/lib/queries/component_validation'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeState(overrides: Partial<StockState> = {}): StockState {
  return {
    instrument_id:      'xyz789',
    date:               '2026-05-18',
    state:              'stage_2b',
    prior_state:        'stage_2a',
    state_since_date:   '2026-04-15',
    dwell_days:         33,
    dwell_percentile:   0.55,
    urgency_score:      'normal',
    within_state_rank:  0.65,
    rs_rank_12m:        0.87,
    close_vs_sma_50:    1.05,
    close_vs_sma_150:   1.12,
    close_vs_sma_200:   1.18,
    sma_200_slope:      0.002,
    volume_ratio_50d:   1.2,
    distribution_days:  1,
    classifier_version: 'v2.0-validated',
    ...overrides,
  }
}

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
// Test 1: RS Leader stock — RS row + dwell row present
// ---------------------------------------------------------------------------

describe('ComponentScorecard — RS Leader stock', () => {
  const rsValidation = makeValidation({ component_name: 'rs', badge: 'Leader' })
  const validations  = [rsValidation]

  it('renders the scorecard section', () => {
    render(
      <ComponentScorecard
        state={makeState({ rs_rank_12m: 0.87 })}
        validations={validations}
      />,
    )
    expect(screen.getByTestId('component-scorecard')).toBeInTheDocument()
  })

  it('renders "Signal scorecard" heading', () => {
    render(
      <ComponentScorecard
        state={makeState({ rs_rank_12m: 0.87 })}
        validations={validations}
      />,
    )
    expect(screen.getByText('Signal scorecard')).toBeInTheDocument()
  })

  it('renders Relative strength row with Leader badge', () => {
    render(
      <ComponentScorecard
        state={makeState({ rs_rank_12m: 0.87 })}
        validations={validations}
      />,
    )
    expect(screen.getByText('Relative strength')).toBeInTheDocument()
    expect(screen.getByText(/Leader/)).toBeInTheDocument()
  })

  it('renders 12-month RS rank context line', () => {
    render(
      <ComponentScorecard
        state={makeState({ rs_rank_12m: 0.87 })}
        validations={validations}
      />,
    )
    expect(screen.getByText(/12-month RS rank: 0\.87/)).toBeInTheDocument()
  })

  it('renders Dwell timing row with day count', () => {
    render(
      <ComponentScorecard
        state={makeState({ dwell_days: 33 })}
        validations={validations}
      />,
    )
    expect(screen.getByText('Dwell timing')).toBeInTheDocument()
    expect(screen.getByText(/Day 33/)).toBeInTheDocument()
  })

  it('renders Phase 5b placeholder rows', () => {
    render(
      <ComponentScorecard
        state={makeState()}
        validations={validations}
      />,
    )
    expect(screen.getByText('OBV slope')).toBeInTheDocument()
    expect(screen.getByText('ATR contraction')).toBeInTheDocument()
    expect(screen.getByText('Realized vol tier')).toBeInTheDocument()
  })

  it('renders "computed continuously" when obvSlope is null (no raw field name or dev jargon)', () => {
    render(
      <ComponentScorecard
        state={makeState()}
        validations={validations}
        obvSlope={null}
      />,
    )
    // Both OBV slope and ATR contraction show this placeholder when values are null
    const placeholders = screen.getAllByText('computed continuously')
    expect(placeholders.length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByText(/not yet stored/)).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 2: stage_1 stock — watch state renders correctly
// ---------------------------------------------------------------------------

describe('ComponentScorecard — stage_1 stock', () => {
  it('renders Stage 1 Base in the master state row', () => {
    render(
      <ComponentScorecard
        state={makeState({ state: 'stage_1', urgency_score: 'n/a', rs_rank_12m: 0.35 })}
        validations={[]}
      />,
    )
    expect(screen.getByText('Stage 1 Base')).toBeInTheDocument()
  })

  it('renders Weak RS tier for rs_rank_12m 0.35', () => {
    render(
      <ComponentScorecard
        state={makeState({ state: 'stage_1', urgency_score: 'n/a', rs_rank_12m: 0.35 })}
        validations={[]}
      />,
    )
    // RS tier = Weak (0.35 falls in [0.2, 0.4))
    expect(screen.getByText(/Weak/)).toBeInTheDocument()
  })

  it('renders urgency context line in dwell row', () => {
    render(
      <ComponentScorecard
        state={makeState({ state: 'stage_1', urgency_score: 'n/a', rs_rank_12m: 0.35 })}
        validations={[]}
      />,
    )
    expect(screen.getByText(/urgency: n\/a/)).toBeInTheDocument()
  })
})
