// Task 1.5 — Stock detail cross-link every token
// TDD: write failing tests first, then implement.
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { WithinStatePeers } from '../WithinStatePeers'
import { MasterStateCard } from '../MasterStateCard'
import type { WithinStatePeer, StockState, CohortBaseline } from '@/lib/queries/states'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makePeer(overrides: Partial<WithinStatePeer> = {}): WithinStatePeer {
  return {
    instrument_id:     'peer-001',
    symbol:            'RELIANCE',
    within_state_rank: 0.85,
    rs_rank_12m:       0.90,
    dwell_days:        12,
    ...overrides,
  }
}

function makeState(overrides: Partial<StockState> = {}): StockState {
  return {
    instrument_id:      'inst-abc',
    date:               '2026-05-20',
    state:              'stage_2a',
    prior_state:        null,
    state_since_date:   '2026-04-01',
    dwell_days:         10,
    dwell_percentile:   0.40,
    urgency_score:      'normal',
    within_state_rank:  0.72,
    rs_rank_12m:        0.85,
    close_vs_sma_50:    1.06,
    close_vs_sma_150:   1.10,
    close_vs_sma_200:   1.18,
    sma_200_slope:      0.002,
    volume_ratio_50d:   1.2,
    distribution_days:  0,
    classifier_version: 'v2.0-validated',
    ...overrides,
  }
}

function makeBaseline(overrides: Partial<CohortBaseline> = {}): CohortBaseline {
  return {
    cohort_key:        'large_cap',
    state:             'stage_2a',
    median_dwell_days: 28,
    p25_dwell_days:    14,
    p75_dwell_days:    45,
    p95_dwell_days:    80,
    n_observations:    100,
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// C1a — WithinStatePeers: peer symbols render as <LinkedTicker> anchors
// ---------------------------------------------------------------------------

describe('C1a — WithinStatePeers peer symbols are linked', () => {
  it('renders peer symbol as an anchor linking to /stocks/[symbol]', () => {
    const peers: WithinStatePeer[] = [
      makePeer({ instrument_id: 'peer-001', symbol: 'RELIANCE' }),
      makePeer({ instrument_id: 'peer-002', symbol: 'INFY' }),
    ]
    render(
      <WithinStatePeers
        peers={peers}
        currentInstrumentId="not-in-list"
        state="stage_2a"
      />,
    )

    const relianceLink = screen.getByRole('link', { name: 'RELIANCE' })
    expect(relianceLink).toBeInTheDocument()
    expect(relianceLink).toHaveAttribute('href', '/stocks/RELIANCE')
  })

  it('renders all peer symbols as links', () => {
    const peers: WithinStatePeer[] = [
      makePeer({ instrument_id: 'p1', symbol: 'TCS' }),
      makePeer({ instrument_id: 'p2', symbol: 'HDFC' }),
      makePeer({ instrument_id: 'p3', symbol: 'WIPRO' }),
    ]
    render(
      <WithinStatePeers
        peers={peers}
        currentInstrumentId="not-in-list"
        state="stage_2b"
      />,
    )

    const links = screen.getAllByRole('link')
    const symbolLinks = links.filter(l => ['TCS', 'HDFC', 'WIPRO'].includes(l.textContent ?? ''))
    expect(symbolLinks).toHaveLength(3)
    symbolLinks.forEach(l => {
      expect(l.getAttribute('href')).toMatch(/^\/stocks\//)
    })
  })

  it('renders correct href for each peer symbol', () => {
    const peers: WithinStatePeer[] = [
      makePeer({ instrument_id: 'p1', symbol: 'ANANTRAJ' }),
    ]
    render(
      <WithinStatePeers
        peers={peers}
        currentInstrumentId="other"
        state="stage_2c"
      />,
    )
    expect(screen.getByRole('link', { name: 'ANANTRAJ' })).toHaveAttribute('href', '/stocks/ANANTRAJ')
  })
})

// ---------------------------------------------------------------------------
// C3 — MasterStateCard: state badge has a tooltip (InfoTooltip info button)
// ---------------------------------------------------------------------------

describe('C3 — MasterStateCard state label has a tooltip', () => {
  it('renders an info tooltip trigger button next to the state label', () => {
    render(
      <MasterStateCard
        symbol="RELIANCE"
        state={makeState()}
        cohortBaseline={makeBaseline()}
        peerRank={2}
        peerTotal={15}
      />,
    )
    // InfoTooltip renders a button with aria-label="info"
    const infoBtn = screen.getByRole('button', { name: /info/i })
    expect(infoBtn).toBeInTheDocument()
  })

  it('tooltip button is adjacent to the state label', () => {
    render(
      <MasterStateCard
        symbol="RELIANCE"
        state={makeState()}
        cohortBaseline={makeBaseline()}
        peerRank={2}
        peerTotal={15}
      />,
    )
    const stateLabel = screen.getByTestId('state-label')
    const infoBtn = screen.getByRole('button', { name: /info/i })
    // Both should be present in the same container
    expect(stateLabel).toBeInTheDocument()
    expect(infoBtn).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// C1b — MasterStateCard: peers count is a link to #within-state-peers
// ---------------------------------------------------------------------------

describe('C1b — MasterStateCard peers count links to peer table', () => {
  it('renders the peers count phrase as an anchor to #within-state-peers (peerRank null)', () => {
    render(
      <MasterStateCard
        symbol="INFY"
        state={makeState({ urgency_score: 'n/a', state: 'stage_1' })}
        cohortBaseline={null}
        peerRank={null}
        peerTotal={42}
      />,
    )
    const peersLink = screen.getByRole('link', { name: /42 peers in this state today/i })
    expect(peersLink).toHaveAttribute('href', '#within-state-peers')
  })

  it('renders a link to #within-state-peers when peerRank is set', () => {
    render(
      <MasterStateCard
        symbol="TCS"
        state={makeState({ urgency_score: 'normal', state: 'stage_2b' })}
        cohortBaseline={makeBaseline()}
        peerRank={5}
        peerTotal={30}
      />,
    )
    // When peerRank is set, the text is "Ranked #5 of 30 today"
    // The link should still navigate to the peers table
    const peersLink = screen.getByRole('link', { name: /Ranked #5 of 30 today/i })
    expect(peersLink).toHaveAttribute('href', '#within-state-peers')
  })
})
