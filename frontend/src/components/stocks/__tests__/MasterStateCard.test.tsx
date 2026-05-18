import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { MasterStateCard } from '../MasterStateCard'
import type { StockState, CohortBaseline } from '@/lib/queries/states'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeState(overrides: Partial<StockState> = {}): StockState {
  return {
    instrument_id:      'abc123',
    date:               '2026-05-18',
    state:              'stage_2a',
    prior_state:        null,
    state_since_date:   '2026-04-01',
    dwell_days:         15,
    dwell_percentile:   0.42,
    urgency_score:      'urgent',
    within_state_rank:  0.72,
    rs_rank_12m:        0.85,
    close_vs_sma_50:    1.08,
    close_vs_sma_150:   1.15,
    close_vs_sma_200:   1.22,
    sma_200_slope:      0.003,
    volume_ratio_50d:   1.4,
    distribution_days:  0,
    classifier_version: 'v2.0-validated',
    ...overrides,
  }
}

function makeBaseline(overrides: Partial<CohortBaseline> = {}): CohortBaseline {
  return {
    cohort_key:         'large_cap',
    state:              'stage_2a',
    median_dwell_days:  28,
    p25_dwell_days:     14,
    p75_dwell_days:     45,
    p95_dwell_days:     80,
    n_observations:     120,
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Test 1: stage_2a + urgent — action text and state label
// ---------------------------------------------------------------------------

describe('MasterStateCard — stage_2a urgent (happy path)', () => {
  it('renders the state label in uppercase', () => {
    render(
      <MasterStateCard
        symbol="RELIANCE"
        state={makeState()}
        cohortBaseline={makeBaseline()}
        peerRank={3}
        peerTotal={27}
      />,
    )
    expect(screen.getByTestId('state-label')).toHaveTextContent('STAGE 2A FRESH BREAKOUT')
  })

  it('renders the urgent action text', () => {
    render(
      <MasterStateCard
        symbol="RELIANCE"
        state={makeState({ urgency_score: 'urgent' })}
        cohortBaseline={makeBaseline()}
        peerRank={3}
        peerTotal={27}
      />,
    )
    expect(screen.getByText(/Act today — fresh breakout window open/)).toBeInTheDocument()
  })

  it('renders the symbol', () => {
    render(
      <MasterStateCard
        symbol="RELIANCE"
        state={makeState()}
        cohortBaseline={makeBaseline()}
        peerRank={3}
        peerTotal={27}
      />,
    )
    expect(screen.getByText('RELIANCE')).toBeInTheDocument()
  })

  it('renders dwell line with cohort details', () => {
    render(
      <MasterStateCard
        symbol="RELIANCE"
        state={makeState({ dwell_days: 15 })}
        cohortBaseline={makeBaseline({ median_dwell_days: 28, p75_dwell_days: 45 })}
        peerRank={3}
        peerTotal={27}
      />,
    )
    expect(screen.getByText(/Day 15 of 28/)).toBeInTheDocument()
    expect(screen.getByText(/p75=45/)).toBeInTheDocument()
  })

  it('renders peer rank line', () => {
    render(
      <MasterStateCard
        symbol="RELIANCE"
        state={makeState()}
        cohortBaseline={makeBaseline()}
        peerRank={3}
        peerTotal={27}
      />,
    )
    expect(screen.getByText(/Ranked #3 of 27 today/)).toBeInTheDocument()
  })

  it('renders within-state rank value', () => {
    render(
      <MasterStateCard
        symbol="RELIANCE"
        state={makeState({ within_state_rank: 0.72 })}
        cohortBaseline={makeBaseline()}
        peerRank={3}
        peerTotal={27}
      />,
    )
    expect(screen.getByText(/0\.72/)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 2: no cohort baseline — fallback text
// ---------------------------------------------------------------------------

describe('MasterStateCard — no cohort baseline', () => {
  it('renders fallback dwell text when cohortBaseline is null', () => {
    render(
      <MasterStateCard
        symbol="INFY"
        state={makeState({ dwell_days: 8, state: 'stage_2b', urgency_score: 'normal' })}
        cohortBaseline={null}
        peerRank={null}
        peerTotal={12}
      />,
    )
    expect(screen.getByText(/no cohort baseline yet/)).toBeInTheDocument()
  })

  it('still renders state label and symbol', () => {
    render(
      <MasterStateCard
        symbol="INFY"
        state={makeState({ state: 'stage_2b', urgency_score: 'normal' })}
        cohortBaseline={null}
        peerRank={null}
        peerTotal={12}
      />,
    )
    expect(screen.getByText('INFY')).toBeInTheDocument()
    expect(screen.getByTestId('state-label')).toHaveTextContent('STAGE 2B CONFIRMED')
  })

  it('renders peer total without rank when peerRank is null', () => {
    render(
      <MasterStateCard
        symbol="INFY"
        state={makeState({ state: 'stage_2b', urgency_score: 'normal' })}
        cohortBaseline={null}
        peerRank={null}
        peerTotal={12}
      />,
    )
    expect(screen.getByText(/12 peers in this state today/)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 3: stage_4 — styling and avoid action text
// ---------------------------------------------------------------------------

describe('MasterStateCard — stage_4', () => {
  it('renders STAGE 4 DECLINE label', () => {
    render(
      <MasterStateCard
        symbol="ZOMATO"
        state={makeState({ state: 'stage_4', urgency_score: 'n/a', within_state_rank: null })}
        cohortBaseline={makeBaseline({ state: 'stage_4', median_dwell_days: 55, p75_dwell_days: 90 })}
        peerRank={null}
        peerTotal={5}
      />,
    )
    expect(screen.getByTestId('state-label')).toHaveTextContent('STAGE 4 DECLINE')
  })

  it('renders the avoid action text', () => {
    render(
      <MasterStateCard
        symbol="ZOMATO"
        state={makeState({ state: 'stage_4', urgency_score: 'n/a', within_state_rank: null })}
        cohortBaseline={null}
        peerRank={null}
        peerTotal={5}
      />,
    )
    expect(screen.getByText(/Avoid; exit if held/)).toBeInTheDocument()
  })

  it('does not render within-state rank breakdown when null', () => {
    render(
      <MasterStateCard
        symbol="ZOMATO"
        state={makeState({ state: 'stage_4', urgency_score: 'n/a', within_state_rank: null })}
        cohortBaseline={null}
        peerRank={null}
        peerTotal={5}
      />,
    )
    // freshness · rs · vol line should not appear
    expect(screen.queryByText(/freshness/)).not.toBeInTheDocument()
  })
})
